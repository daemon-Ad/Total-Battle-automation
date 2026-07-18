import sys
import os
import time
import json
import cv2
import numpy as np

# Ensure we can import from core (sys.path hack since script is in a subdirectory)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adb import ADBController
from core.vision import VisionEngine
from crypting.time_math import parse_march_time_seconds, parse_tar_amount, compute_reduced_time

class Crypter:
    def __init__(self, device_name="moto-g51"):
        self.adb = ADBController()
        # Initialize VisionEngine with crypting images directory
        self.images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
        self.vision = VisionEngine(self.images_dir)
        self.device_name = device_name
        
        self.config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, f"{self.device_name}-config.json")
        self.config = self._load_config()
        self.tar_available = None
        self.tar_carrying = None
        self.initial_seconds = 120

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def _get_or_find_location(self, key, template_name, screen_img=None, threshold=0.7, tap=False, delay=0.7):
        if key in self.config:
            loc = tuple(self.config[key])
            if tap:
                self.adb.tap(loc[0], loc[1])
                time.sleep(delay) # Small gap for UI to load
            return loc
        
        print(f"Finding location for '{key}' using template '{template_name}'...")
        if screen_img is None:
            screen_img = self.adb.capture_screen()
            
        if screen_img is None:
            print(f"Error: Failed to capture screen when looking for '{key}'.")
            return None
            
        template_path = os.path.join(self.images_dir, template_name)
        template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        
        if template_img is None:
            print(f"Error: Template '{template_path}' not found.")
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
                self.adb.tap(center[0], center[1])
                time.sleep(delay)
            return center
            
        print(f"Could not find '{key}' on screen.")
        return None

    def _get_nth_template_match(self, template_name, screen_img, n=1, threshold=0.7):
        template_path = os.path.join(self.images_dir, template_name)
        template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template_img is None: return None
        
        h, w = template_img.shape[:2]
        res = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        loc_match = np.where(res >= threshold)
        points = list(zip(*loc_match[::-1]))
        
        if not points: return None
        
        # Cluster points (group by y-coordinate proximity)
        clusters = []
        for pt in points:
            found = False
            for cluster in clusters:
                if abs(cluster[0][1] - pt[1]) < h: # Within full height of each other
                    cluster.append(pt)
                    found = True
                    break
            if not found:
                clusters.append([pt])
                
        # Sort clusters by y coordinate (top to bottom)
        clusters.sort(key=lambda c: c[0][1])
        
        if n <= len(clusters):
            pt = clusters[n-1][0] # take first point of cluster
            return (int(pt[0] + w // 2), int(pt[1] + h // 2))
        return None

    def _get_center_screen(self, screen_img):
        if 'center_screen' in self.config:
            return tuple(self.config['center_screen'])
        h, w = screen_img.shape[:2]
        center = (w // 2, h // 2)
        self.config['center_screen'] = center
        self._save_config()
        return center

    def _extract_text_clean(self, crop_img):
        """Uses EasyOCR directly as it performs best on the raw game fonts."""
        if not hasattr(self, 'reader'):
            import easyocr
            self.reader = easyocr.Reader(['en'], gpu=False)
        
        rgb = cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB)
        res = self.reader.readtext(rgb, detail=0)
        return " ".join(res).strip()

    def _check_carter_and_tar(self):
        """Step 10: Check Carter and Tar limits"""
        
        # 10.1 Verify Carter is ready and selected
        print("Verifying Carter's availability...")
        carter_is_ready = False
        wait_start = time.time()
        
        img_checked = cv2.imread(os.path.join(self.images_dir, 'green-checkmark-tight.png'), cv2.IMREAD_COLOR)
        img_empty = cv2.imread(os.path.join(self.images_dir, 'empty-checkbox-tight.png'), cv2.IMREAD_COLOR)
        
        while time.time() - wait_start < 60: # Wait up to 60s for Carter
            screen_img = self.adb.capture_screen()
            if screen_img is None:
                time.sleep(1)
                continue
                
            carter_loc = self._get_or_find_location('carter_slot', 'Carter.png', screen_img, threshold=0.7)
            if not carter_loc:
                print("ERROR: Could not find Carter.")
                return False
                
            c_x, c_y = carter_loc
            H, W = screen_img.shape[:2]
            h_empty, w_empty = img_empty.shape[:2]
            
            # Box directly under Carter. Width is tightly bound to his column to avoid seeing other captains.
            # Height goes down 400px to ensure the checkbox is fully included.
            box_width_half = (w_empty // 2) + 20
            carter_box = screen_img[c_y:min(H, c_y+400), max(0, c_x - box_width_half):min(W, c_x + box_width_half)]
            
            # Is Carter ticked?
            if self.vision.find_template_image(carter_box, img_checked, threshold=0.7):
                print("Carter is ready and ticked!")
                carter_is_ready = True
                break
                
            # Is Carter unticked?
            if self.vision.find_template_image(carter_box, img_empty, threshold=0.8):
                print("Carter is returned but unticked. Unticking others...")
                # Find any green checkmark on the whole screen and click it
                res = cv2.matchTemplate(screen_img, img_checked, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= 0.75:
                    h, w = img_checked.shape[:2]
                    self.adb.tap(max_loc[0] + w//2, max_loc[1] + h//2)
                    time.sleep(0.7)
                    screen_img = self.adb.capture_screen() # update screen
                    
                # Now tap Carter's empty box
                print("Ticking Carter...")
                res_box_empty = cv2.matchTemplate(carter_box, img_empty, cv2.TM_CCOEFF_NORMED)
                _, e_max_val, _, e_max_loc = cv2.minMaxLoc(res_box_empty)
                if e_max_val >= 0.75:
                    h, w = img_empty.shape[:2]
                    tap_x = max(0, c_x - box_width_half) + e_max_loc[0] + w//2
                    tap_y = c_y + e_max_loc[1] + h//2
                    self.adb.tap(tap_x, tap_y)
                    time.sleep(0.7)
                continue
                
            print("Carter is busy (On a march)... waiting.")
            time.sleep(2)
            
        if not carter_is_ready:
            print("ERROR: Carter did not become ready within the timeout.")
            return False

        # 10.2 Check Tar
        if self.tar_available is None:
            # We need to find "remaining-tar" and "tar-carrying" icons/text
            rem_tar_loc = self._get_or_find_location('remaining_tar', 'remaining-tar.png', screen_img, threshold=0.7)
            car_tar_loc = self._get_or_find_location('tar_carrying', 'tar-carrying.png', screen_img, threshold=0.7)
            
            if not rem_tar_loc or not car_tar_loc:
                print("WARNING: Could not find Tar locations to verify. Skipping tar check (unsafe).")
            else:
                H, W = screen_img.shape[:2]
                rem_crop = screen_img[max(0, rem_tar_loc[1]-30):min(H, rem_tar_loc[1]+30), rem_tar_loc[0]:min(W, rem_tar_loc[0]+200)]
                rem_text = self._extract_text_clean(rem_crop)
                self.tar_available = parse_tar_amount(rem_text)
                
                car_crop = screen_img[max(0, car_tar_loc[1]-30):min(H, car_tar_loc[1]+30), car_tar_loc[0]:min(W, car_tar_loc[0]+200)]
                car_text = self._extract_text_clean(car_crop)
                self.tar_carrying = parse_tar_amount(car_text)
                print(f"Initial Tar Parsed - Available: {self.tar_available} (raw: {rem_text}), Carrying: {self.tar_carrying} (raw: {car_text})")
        else:
            if self.tar_carrying:
                self.tar_available -= self.tar_carrying
                
        print(f"Current Tar Available: {self.tar_available}, Tar Carrying: {self.tar_carrying}")
        
        if self.tar_available is not None and self.tar_carrying is not None:
            if self.tar_available < self.tar_carrying:
                print("ERROR: Not enough Tar available. Stopping.")
                return False
                
        # 10.3 Find Explore button and OCR the time beside it before tapping
        print("Finding Explore (Launch) Button and reading time...")
        launch_loc = self._get_or_find_location('explore_launch_button', 'explore-button.png', screen_img, threshold=0.7, tap=False)
        if not launch_loc: 
            return False
            
        H, W = screen_img.shape[:2]
        # Crop area strictly to the left of the launch button for the hourglass time to avoid 'Explore' text
        time_crop = screen_img[max(0, launch_loc[1]-40):min(H, launch_loc[1]+40), max(0, launch_loc[0]-400):max(0, launch_loc[0]-150)]
        
        time_text = self._extract_text_clean(time_crop)
        print(f"OCR Explore Time Text: {time_text}")
        
        self.initial_seconds = parse_march_time_seconds(time_text)
        if not self.initial_seconds:
            print("WARNING: Could not parse march time from explore screen. Defaulting to 120s.")
            self.initial_seconds = 120
        else:
            print(f"Parsed initial march time: {self.initial_seconds}s")
            
        self.adb.tap(launch_loc[0], launch_loc[1])
        time.sleep(0.7)

        return True

    def _speedup_sequence(self, is_last_iteration):
        """Steps 11-12: Handle march time and speedups"""
        print("Waiting for taskbar to appear...")
        time.sleep(1) # Wait for task bar
        
        screen_img = self.adb.capture_screen()
        if screen_img is None: return False
        speedup_loc = self._get_or_find_location('speedup_button', 'speedup-button.png', screen_img, threshold=0.7, tap=True, delay=0.7)
        if not speedup_loc:
            print("ERROR: Could not find speedup button.")
            return False
            
        time.sleep(1) # Wait for Use button to appear
        
        screen_img = self.adb.capture_screen()
        if screen_img is None: return False
        
        use_btn_loc = self._get_or_find_location('use_button', 'use-button.png', screen_img, threshold=0.7)
        if not use_btn_loc:
            print("ERROR: Could not find Use button.")
            return False
            
        final_seconds, uses = compute_reduced_time(self.initial_seconds)
        print(f"Will tap Use button {uses} times. Final expected time: {final_seconds}s")
        
        for _ in range(uses):
            self.adb.tap(use_btn_loc[0], use_btn_loc[1])
            time.sleep(0.35)
            
        if is_last_iteration:
            print("Last iteration reached. Terminating without wait time.")
            return True
            
        print("Waiting 20s before closing taskbar...")
        time.sleep(20)
        
        # Tap back button to return to home screen map
        print("Pressing back button to return to homescreen.")
        self._get_or_find_location('back_button', 'back-button.png', tap=True, delay=2.0)
            
        return True

    def run_loop(self, iterations=10):
        print("Starting Crypting Automation...")
        for i in range(1, iterations + 1):
            print(f"\n--- Iteration {i}/{iterations} ---")
            
            # Step 1: Watchtower
            print("Step 1: Finding Watchtower...")
            if not self._get_or_find_location('watchtower_icon', 'watchtower-icon.png', tap=True):
                break
                
            # Step 2 & 3: Crypts tab
            if i == 1:
                print("Step 2: Finding Crypts Tab...")
                if not self._get_or_find_location('crypts_tab', 'crypts-tab.png', tap=True):
                    break
            
            # Step 4: Go button (Second crypt)
            print("Step 4: Finding 2nd Go Button...")
            screen_img = self.adb.capture_screen()
            if screen_img is None: 
                print("Screen capture failed, aborting.")
                break
                
            go_loc = self._get_nth_template_match('go-button.png', screen_img, n=2, threshold=0.7)
            if go_loc:
                self.adb.tap(go_loc[0], go_loc[1])
                time.sleep(1.5)
            else:
                print("Could not find 2nd Go button. Attempting 1st Go button fallback.")
                go_loc = self._get_nth_template_match('go-button.png', screen_img, n=1, threshold=0.7)
                if go_loc:
                    self.adb.tap(go_loc[0], go_loc[1])
                    time.sleep(1.5)
                else:
                    print("ERROR: No Go buttons found.")
                    break
            
            # Step 5 & 6: Center tap (skipping redline check)
            print("Step 6: Tapping Center of Screen...")
            screen_img = self.adb.capture_screen()
            if screen_img is None: 
                print("Screen capture failed, aborting iteration.")
                break
            center_loc = self._get_center_screen(screen_img)
            self.adb.tap(center_loc[0], center_loc[1])
            time.sleep(0.7)
            
            # Step 7: Explore button
            print("Step 7: Finding Explore Button...")
            if not self._get_or_find_location('explore_button', 'explore-button.png', tap=True):
                # Sometimes the map tap doesn't register if it was still moving, tap again
                self.adb.tap(center_loc[0], center_loc[1])
                time.sleep(0.7)
                if not self._get_or_find_location('explore_button', 'explore-button.png', tap=True):
                    print("Could not enter explore menu.")
                    break
            
            # Step 8 & 9 & 10: Check Carter, Tar, and Read time
            print("Step 10: Verifying Carter and Tar...")
            if not self._check_carter_and_tar():
                break
            
            # Step 11 & 12: Speedup and Wait
            print("Step 11: Handling Speedups...")
            is_last_iteration = (i == iterations)
            if not self._speedup_sequence(is_last_iteration):
                break
                
            print(f"Iteration {i} complete.")
            
        print("Crypting Automation Finished.")

if __name__ == "__main__":
    crypter = Crypter("moto-g51")
    # Take number of iterations from user if provided via CLI
    iters = 10
    if len(sys.argv) > 1:
        iters = int(sys.argv[1])
    crypter.run_loop(iters)
