#!/usr/bin/env python3
"""
Caravan resource-sending automation via ADB - pinned-location approach.

Flow (per user spec):
  ONE-TIME SETUP:
    1. Tap the pin/saved-locations icon
    2. Tap the first saved location in that list -> map centers on target city
       (only done once; after this the city stays visible on screen)

  PER-CAPTAIN CYCLE (repeated for each of num_captains captains):
    3. Tap the city (map_mid) -> popup opens. Wait 2s.
    4. Tap "Caravan" option. On the first time we need travel-time data
       (globally) or per-captain sent-amount data, take ONE screenshot
       here and OCR it.
       Then swipe the configured resource's slider to max.
    5. Tap "Start march".
    6. Wait 3-4s, tap the ETA display, wait 1-2s, then tap the
       accelerator button 5 times, paced ~0.6-0.8s apart.
    7. Tap "back" to return to the map. Wait 1s.

  After all captains have been sent in a round, wait the computed
  "captain cycle time" (derived once from OCR'd travel time, halved
  up to 5 times for the 5 accelerators, floored at 10s) before
  starting the next round. Continue until quota_total is reached
  (if set) or the user hits Ctrl+C.

Screenshots are only taken when we still need OCR data (once globally
for travel time, once per captain for its carried amount) - not on
every single cycle, to keep the loop fast.
"""

import json
import re
import subprocess
import time
import sys
from pathlib import Path

import pytesseract
from PIL import Image

CONFIG_PATH = Path(__file__).parent / "config.json"
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
ACTION_DELAY = 0.4  # overridden by config "action_delay_sec"


def adb(*args):
    result = subprocess.run(["adb", "shell", *args], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[warn] adb command failed: {args} -> {result.stderr.strip()}")
    return result.stdout


def tap(x, y):
    adb("input", "tap", str(x), str(y))
    time.sleep(ACTION_DELAY)


def swipe(x1, y1, x2, y2, duration_ms=300):
    adb("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))
    time.sleep(ACTION_DELAY)


def screenshot(local_path):
    """Direct pull via exec-out, matches `adb exec-out screencap -p > file.png`."""
    with open(local_path, "wb") as f:
        result = subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f)
    if result.returncode != 0:
        print(f"[warn] screenshot failed")
    return local_path


# ---------------------------------------------------------------------
# OCR parsing
# ---------------------------------------------------------------------

SUFFIX_MULT = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def parse_amount(text):
    """'2.66M' -> 2660000.0"""
    m = re.search(r"([\d.,]+)\s*([KMB])?", text)
    if not m:
        return None
    number = float(m.group(1).replace(",", ""))
    suffix = m.group(2)
    if suffix:
        number *= SUFFIX_MULT[suffix.upper()]
    return number


def parse_travel_time_seconds(text):
    """'9m 25s' or '1h 2m 3s' -> total seconds"""
    h = re.search(r"(\d+)\s*h", text)
    m = re.search(r"(\d+)\s*m(?!s)", text)  # avoid matching 'ms' if it ever appears
    s = re.search(r"(\d+)\s*s", text)
    total = 0
    if h:
        total += int(h.group(1)) * 3600
    if m:
        total += int(m.group(1)) * 60
    if s:
        total += int(s.group(1))
    return total if total > 0 else None


def ocr_march_screen(image_path, region):
    im = Image.open(image_path)
    crop = im.crop(tuple(region))
    text = pytesseract.image_to_string(crop)

    will_be_sent = None
    travel_seconds = None

    wbs_match = re.search(r"Will be sent:?\s*([\d.,]+\s*[KMB]?)", text, re.IGNORECASE)
    if wbs_match:
        will_be_sent = parse_amount(wbs_match.group(1))

    tt_match = re.search(r"Travel time\s*(.+)", text, re.IGNORECASE)
    if tt_match:
        travel_seconds = parse_travel_time_seconds(tt_match.group(1))

    return will_be_sent, travel_seconds, text


def compute_cycle_time(travel_seconds, max_halvings=5, floor_seconds=10.0):
    """
    Simulate applying up to 5 accelerators (each halves remaining time),
    stopping early if the next halving would drop below floor_seconds.
    This estimates how long a captain is actually tied up for.
    """
    t = float(travel_seconds)
    for _ in range(max_halvings):
        nxt = t / 2
        if nxt < floor_seconds:
            break
        t = nxt
    return t


# ---------------------------------------------------------------------
# Flow steps
# ---------------------------------------------------------------------

def one_time_setup(coords):
    """Steps 1-2: open saved-locations list and jump to the target city."""
    tap(*coords["pin_icon"])
    tap(*coords["first_saved_location"])
    time.sleep(1.5)  # let map center/settle


def refresh_captain_bonuses(coords, num_captains):
    """
    Refreshes captain equipment/bonuses by tapping each captain slot once
    and exiting back to map, ensuring the game registers their gear.
    """
    print("[info] Refreshing captain bonuses...")
    # Step 0: Tap city (mid)
    tap(*coords["map_mid"])
    time.sleep(2.0)

    # Step 1: Tap Caravan
    tap(*coords["caravan_option"])
    time.sleep(1.0)

    # Tap each captain slot based on num_captains (up to 3 slots)
    captain_slots = [
        (280, 350),
        (535, 350),
        (812, 350)
    ]
    for idx in range(min(num_captains, len(captain_slots))):
        slot_x, slot_y = captain_slots[idx]
        print(f"[info] Refreshing captain {idx + 1} at ({slot_x}, {slot_y})")
        tap(slot_x, slot_y)
        time.sleep(1.0)
        tap(*coords["back_button"])
        time.sleep(1.0)

    # Steps 5 & 6: Return to map
    tap(*coords["back_button"])
    time.sleep(1.0)
    # tap(*coords["back_button"])
    # time.sleep(1.0)


def set_resource_max(resource, coords):
    """Swipes the given resource's slider to max (fixed row per
    resource, same x-track for all - no image recognition needed)."""
    row_y = coords["resource_rows"].get(resource)
    if row_y is None:
        print(f"[error] unknown resource '{resource}'")
        return False
    swipe(coords["slider_x_start"], row_y, coords["slider_x_max"], row_y, duration_ms=300)
    return True


def send_one_captain(coords, resource, need_screenshot):
    """Steps 3-7 for a single captain. Returns (will_be_sent, travel_seconds) or (None, None)."""
    # Step 3
    tap(*coords["map_mid"])
    time.sleep(2.0)

    # Step 4
    tap(*coords["caravan_option"])

    set_resource_max(resource, coords)

    will_be_sent = None
    travel_seconds = None
    if need_screenshot:
        time.sleep(0.5)  # let the slider update and march screen fully render/stabilize
        img_path = str(IMAGES_DIR / "_march_screen.png")
        screenshot(img_path)
        will_be_sent, travel_seconds, raw_text = ocr_march_screen(img_path, coords["ocr_region"])
        print(f"[ocr] raw: {raw_text!r}")
        print(f"[ocr] will_be_sent={will_be_sent} travel_seconds={travel_seconds}")

    # Step 5
    tap(*coords["start_march_button"])

    # Step 6
    time.sleep(3.5)
    tap(*coords["eta_display"])
    time.sleep(1.5)
    for _ in range(5):
        tap(*coords["accelerator_button"])
        time.sleep(0.65)

    # Step 7
    tap(*coords["back_button"])
    time.sleep(1.0)

    return will_be_sent, travel_seconds


# ---------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------

def main():
    global ACTION_DELAY
    cfg = json.loads(CONFIG_PATH.read_text())
    ACTION_DELAY = cfg.get("action_delay_sec", ACTION_DELAY)

    coords = cfg["coordinates"]
    resource = cfg["resource"]
    num_captains = cfg.get("num_captains", 3)
    quota_total = cfg.get("quota_total")  # None = unlimited

    one_time_setup(coords)
    refresh_captain_bonuses(coords, num_captains)

    cycle_time = None          # derived once from first-ever travel time OCR
    captain_amounts = [None] * num_captains  # per-captain "will be sent", cached after first read
    total_sent = 0.0
    round_num = 0

    try:
        while True:
            round_num += 1
            print(f"=== Round {round_num} ===")

            round_start_time = time.time()

            for idx in range(num_captains):
                need_amount = captain_amounts[idx] is None
                need_baseline = cycle_time is None
                need_screenshot = need_amount or need_baseline

                print(f"--- captain {idx + 1}/{num_captains} ---")
                will_be_sent, travel_seconds = send_one_captain(coords, resource, need_screenshot)

                if need_baseline and travel_seconds:
                    cycle_time = compute_cycle_time(travel_seconds)
                    print(f"[info] captain cycle time estimated at {cycle_time:.1f}s "
                          f"(from travel_time={travel_seconds}s)")

                if need_amount and will_be_sent:
                    captain_amounts[idx] = will_be_sent
                    print(f"[info] captain {idx + 1} carries ~{will_be_sent:,.0f} {resource}")

                if captain_amounts[idx]:
                    total_sent += captain_amounts[idx]

                print(f"[progress] total sent so far: {total_sent:,.0f}"
                      + (f" / {quota_total:,.0f}" if quota_total else ""))

                if quota_total and total_sent >= quota_total:
                    print("Quota reached. Stopping.")
                    return

            elapsed = time.time() - round_start_time
            if cycle_time:
                wait_time = max(0.0, cycle_time - elapsed)
                if wait_time > 0:
                    print(f"[info] round complete, elapsed={elapsed:.1f}s, waiting {wait_time:.1f}s for Captain 1 to return")
                    time.sleep(wait_time)
                else:
                    print(f"[info] round complete, elapsed={elapsed:.1f}s, Captain 1 already returned (cycle_time={cycle_time:.1f}s)")
            else:
                print(f"[info] round complete, no cycle time calculated yet, waiting 60.0s")
                time.sleep(60.0)

    except KeyboardInterrupt:
        print(f"\nStopped by user. Total sent: {total_sent:,.0f} {resource}.")
        sys.exit(0)


if __name__ == "__main__":
    main()