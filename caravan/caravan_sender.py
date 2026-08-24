#!/usr/bin/env python3
"""
Caravan resource-sending automation via ADB - OOP refactored and Orchestrator ready.
"""

import sys
import os
import time
import json
import re
import random
import argparse
from pathlib import Path
import cv2
import numpy as np
import pytesseract
from PIL import Image

# Ensure we can import from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adb import ADBController
from core.vision import VisionEngine

class CaravanSender:
    DEFAULT_COORDS = {
        "caravan_pin_icon": [430, 2170],
        "caravan_first_saved_location": [530, 344],
        "caravan_map_mid": [540, 1230],
        "caravan_caravan_option": [780, 1425],
        "caravan_resource_rows": {
            "silver": 860,
            "wood": 1100,
            "iron": 1360,
            "stone": 1608,
            "food": 1852
        },
        "caravan_slider_x_start": 340,
        "caravan_slider_x_max": 1000,
        "caravan_start_march_button": [540, 2387],
        "caravan_eta_display": [685, 345],
        "caravan_accelerator_button": [817, 617],
        "caravan_back_button": [80, 183],
        "caravan_ocr_region": [0, 2140, 1080, 2360]
    }

    def __init__(self, device_name="moto-g51"):
        self.device_name = device_name
        self.adb = ADBController()
        self.images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
        self.vision = VisionEngine(self.images_dir)
        
        self.config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, f"{self.device_name}-config.json")
        self.config = self._load_config()
        self.action_delay = self.config.get("action_delay_sec", 0.4)

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def _sleep(self, base_time):
        """Sleep using a Log-Normal curve for human-like delay."""
        extra = random.lognormvariate(-0.5, 0.8)
        actual_time = (base_time * 0.95) + extra
        time.sleep(max(0.1, actual_time))

    def _get_or_find_location(self, key, template_name, screen_img=None, threshold=0.7, tap=False, delay=0.7, short_press=False):
        if key in self.config:
            loc = tuple(self.config[key])
            if tap:
                # Use standard jitter if template isn't read
                self.adb.tap(loc[0], loc[1], short_press=short_press)
                self._sleep(delay)
            return loc
            
        template_path = os.path.join(self.images_dir, template_name)
        template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        box_dims = None
        if template_img is not None:
            box_dims = (template_img.shape[1], template_img.shape[0])
        
        print(f"Finding location for '{key}' using template '{template_name}'...")
        if screen_img is None:
            screen_img = self.adb.capture_screen()
            
        if screen_img is None:
            print(f"Error: Failed to capture screen when looking for '{key}'.")
            # Fallback to default coordinate if template matching screen capture fails
            if key in self.DEFAULT_COORDS:
                loc = self.DEFAULT_COORDS[key]
                self.config[key] = loc
                self._save_config()
                if tap:
                    self.adb.tap(loc[0], loc[1], short_press=short_press)
                    self._sleep(delay)
                return loc
            return None
            
        if template_img is None:
            print(f"Error: Template '{template_path}' not found.")
            if key in self.DEFAULT_COORDS:
                loc = self.DEFAULT_COORDS[key]
                self.config[key] = loc
                self._save_config()
                if tap:
                    self.adb.tap(loc[0], loc[1], short_press=short_press)
                    self._sleep(delay)
                return loc
            return None
            
        h, w = template_img.shape[:2]
        res = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        loc_match = np.where(res >= threshold)
        points = list(zip(*loc_match[::-1]))
        
        if points:
            pt = points[0]
            center = (int(pt[0] + w // 2), int(pt[1] + h // 2))
            self.config[key] = center
            self._save_config()
            print(f"Saved '{key}' at {center}")
            if tap:
                self.adb.tap(center[0], center[1], short_press=short_press, box_dims=box_dims)
                self._sleep(delay)
            return center
            
        print(f"Could not find '{key}' on screen. Falling back to default.")
        if key in self.DEFAULT_COORDS:
            loc = self.DEFAULT_COORDS[key]
            self.config[key] = loc
            self._save_config()
            if tap:
                self.adb.tap(loc[0], loc[1], short_press=short_press)
                self._sleep(delay)
            return loc
        return None

    def one_time_setup(self):
        """Step 1-2: Open saved-locations list and jump to the target city."""
        print("[info] Running one-time setup: centering map on city...")
        self._get_or_find_location("caravan_pin_icon", "location-pin.png", tap=True, delay=1.0)
        self._get_or_find_location("caravan_first_saved_location", "location-pin-list.png", tap=True, delay=1.5)

    def refresh_captain_bonuses(self, num_captains):
        """Refreshes captain bonuses by tapping slots and returning."""
        print("[info] Refreshing captain bonuses...")
        map_mid = self.config.get("caravan_map_mid", self.DEFAULT_COORDS["caravan_map_mid"])
        self.adb.tap(map_mid[0], map_mid[1])
        self._sleep(2.0)

        self._get_or_find_location("caravan_caravan_option", "caravan-button.png", tap=True, delay=1.0)

        captain_slots = [
            (280, 350),
            (535, 350),
            (812, 350)
        ]
        back_btn = self.config.get("caravan_back_button", self.DEFAULT_COORDS["caravan_back_button"])
        for idx in range(min(num_captains, len(captain_slots))):
            slot_x, slot_y = captain_slots[idx]
            print(f"[info] Refreshing captain {idx + 1} at ({slot_x}, {slot_y})")
            self.adb.tap(slot_x, slot_y)
            self._sleep(1.0)
            self.adb.tap(back_btn[0], back_btn[1])
            self._sleep(1.0)

        self.adb.tap(back_btn[0], back_btn[1])
        self._sleep(1.0)

    def set_resource_max(self, resource):
        """Swipes the configured resource's slider to max."""
        rows = self.config.get("caravan_resource_rows", self.DEFAULT_COORDS["caravan_resource_rows"])
        row_y = rows.get(resource)
        if row_y is None:
            print(f"[error] unknown resource '{resource}'")
            return False
        
        slider_x_start = self.config.get("caravan_slider_x_start", self.DEFAULT_COORDS["caravan_slider_x_start"])
        slider_x_max = self.config.get("caravan_slider_x_max", self.DEFAULT_COORDS["caravan_slider_x_max"])
        self.adb.swipe(slider_x_start, row_y, slider_x_max, row_y, duration_ms=300)
        return True

    def ocr_march_screen(self, image_path, region):
        im = Image.open(image_path)
        crop = im.crop(tuple(region))
        text = pytesseract.image_to_string(crop)

        will_be_sent = None
        travel_seconds = None

        wbs_match = re.search(r"Will be sent:?\s*([\d.,]+\s*[KMB]?)", text, re.IGNORECASE)
        if wbs_match:
            will_be_sent = self.parse_amount(wbs_match.group(1))

        tt_match = re.search(r"Travel time\s*(.+)", text, re.IGNORECASE)
        if tt_match:
            travel_seconds = self.parse_travel_time_seconds(tt_match.group(1))

        return will_be_sent, travel_seconds, text

    def parse_amount(self, text):
        SUFFIX_MULT = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        m = re.search(r"([\d.,]+)\s*([KMB])?", text)
        if not m:
            return None
        number = float(m.group(1).replace(",", ""))
        suffix = m.group(2)
        if suffix:
            number *= SUFFIX_MULT[suffix.upper()]
        return number

    def parse_travel_time_seconds(self, text):
        h = re.search(r"(\d+)\s*h", text)
        m = re.search(r"(\d+)\s*m(?!s)", text)
        s = re.search(r"(\d+)\s*s", text)
        total = 0
        if h:
            total += int(h.group(1)) * 3600
        if m:
            total += int(m.group(1)) * 60
        if s:
            total += int(s.group(1))
        return total if total > 0 else None

    def compute_cycle_time(self, travel_seconds, max_halvings=5, floor_seconds=10.0):
        t = float(travel_seconds)
        for _ in range(max_halvings):
            nxt = t / 2
            if nxt < floor_seconds:
                break
            t = nxt
        return t

    def send_one_captain(self, resource, need_screenshot, cached_travel_time=None):
        """Steps 3-7 for a single captain."""
        map_mid = self.config.get("caravan_map_mid", self.DEFAULT_COORDS["caravan_map_mid"])
        self.adb.tap(map_mid[0], map_mid[1], pure_tap=True)
        self._sleep(2.0)

        self._get_or_find_location("caravan_caravan_option", "caravan-button.png", tap=True, delay=1.0)

        self.set_resource_max(resource)

        will_be_sent = None
        travel_seconds = None
        current_travel_time = cached_travel_time
        if need_screenshot:
            self._sleep(0.5)
            img_path = os.path.join(self.images_dir, "_march_screen.png")
            # Capture using fast exec-out
            screen_bgr = self.adb.capture_screen()
            if screen_bgr is not None:
                cv2.imwrite(img_path, screen_bgr)
                ocr_region = self.config.get("caravan_ocr_region", self.DEFAULT_COORDS["caravan_ocr_region"])
                will_be_sent, travel_seconds, raw_text = self.ocr_march_screen(img_path, ocr_region)
                print(f"[ocr] raw: {raw_text!r}")
                print(f"[ocr] will_be_sent={will_be_sent} travel_seconds={travel_seconds}")
                current_travel_time = travel_seconds

        start_btn = self.config.get("caravan_start_march_button", self.DEFAULT_COORDS["caravan_start_march_button"])
        self.adb.tap(start_btn[0], start_btn[1])
        self._sleep(3.5)

        # Acceleration/Speedup logic
        # If travel time is very short (< 15 seconds), speedups might click random UI elements because the march finishes too fast.
        if current_travel_time is not None and current_travel_time <= 15:
            print(f"[info] Travel time is very short ({current_travel_time}s). Skipping speedup sequence to avoid misclicks.")
        else:
            eta_display = self.config.get("caravan_eta_display", self.DEFAULT_COORDS["caravan_eta_display"])
            self.adb.tap(eta_display[0], eta_display[1])
            self._sleep(1.5)

            use_btn_loc = self._get_or_find_location("caravan_use_button", "use-button.png", threshold=0.7)
            if not use_btn_loc:
                use_btn_loc = self.config.get("caravan_accelerator_button", self.DEFAULT_COORDS["caravan_accelerator_button"])

            for _ in range(5):
                self.adb.tap(use_btn_loc[0], use_btn_loc[1], short_press=True, pure_tap=True)
                # Override universal setting for faster taps
                time.sleep(random.uniform(0.1, 0.2))

            back_btn = self.config.get("caravan_back_button", self.DEFAULT_COORDS["caravan_back_button"])
            self.adb.tap(back_btn[0], back_btn[1])
            self._sleep(1.0)

        return will_be_sent, travel_seconds

    def run_loop(self, resource, target_amount=None, num_captains=3):
        """Main execution loop called by Orchestrator or run directly."""
        print(f"Starting Caravan Sender... Resource: {resource}, Quota: {target_amount}, Captains: {num_captains}")
        self.one_time_setup()
        # self.refresh_captain_bonuses(num_captains)

        cycle_time = None          # derived once from first-ever travel time OCR
        base_travel = None         # raw travel seconds from first captain
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
                    will_be_sent, travel_seconds = self.send_one_captain(resource, need_screenshot, cached_travel_time=base_travel)

                    if need_baseline and travel_seconds:
                        base_travel = travel_seconds
                        cycle_time = self.compute_cycle_time(travel_seconds)
                        print(f"[info] captain cycle time estimated at {cycle_time:.1f}s (from travel_time={travel_seconds}s)")

                    if need_amount and will_be_sent:
                        captain_amounts[idx] = will_be_sent
                        print(f"[info] captain {idx + 1} carries ~{will_be_sent:,.0f} {resource}")

                    if captain_amounts[idx]:
                        total_sent += captain_amounts[idx]

                    print(f"[progress] total sent so far: {total_sent:,.0f}" + (f" / {target_amount:,.0f}" if target_amount else ""))

                    if target_amount and total_sent >= target_amount:
                        print("Quota reached. Stopping.")
                        return total_sent

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
            return total_sent

def parse_cli_args():
    parser = argparse.ArgumentParser(description="Caravan Resource Sender")
    parser.add_argument("--resource", type=str, choices=["silver", "wood", "iron", "stone", "food"], help="Resource type to send")
    parser.add_argument("--amount", type=str, help="Amount to send (e.g. 5M, 10M, 500K, or numeric)")
    parser.add_argument("--captains", type=int, default=3, help="Number of captains to send")
    parser.add_argument("--device", type=str, default="moto-g51", help="Device name configuration")
    return parser.parse_args()

def main():
    args = parse_cli_args()
    
    resource = args.resource
    amount_str = args.amount
    
    # Prompt for resource if not provided
    if not resource:
        try:
            print("Select resource to send:")
            print("1) silver")
            print("2) wood")
            print("3) iron")
            print("4) stone")
            print("5) food")
            choice = input("Enter choice (1-5): ").strip()
            mapping = {"1": "silver", "2": "wood", "3": "iron", "4": "stone", "5": "food"}
            resource = mapping.get(choice)
            if not resource:
                print("Invalid selection. Defaulting to wood.")
                resource = "wood"
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

    # Prompt for amount if not provided
    if not amount_str:
        try:
            amount_str = input("Enter amount to send (e.g., 5M, 500K, or enter to run unlimited): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

    sender = CaravanSender(device_name=args.device)
    
    amount = None
    if amount_str:
        amount = sender.parse_amount(amount_str)
        if amount is None:
            try:
                amount = float(amount_str)
            except ValueError:
                print(f"Could not parse amount '{amount_str}'. Running with unlimited quota.")
                amount = None

    sender.run_loop(resource=resource, target_amount=amount, num_captains=args.captains)

if __name__ == "__main__":
    main()
