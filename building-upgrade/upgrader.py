import sys
import os
import time
import json
import cv2
import numpy as np
import random
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.adb import ADBController
from core.vision import VisionEngine
from time_parser import parse_march_time_seconds

SPEEDUPS = [
    ("7-day-speedup.png", 7 * 86400),
    ("3-day-speedup.png", 3 * 86400),
    ("1-day-speedup.png", 86400),
    ("15-hour-speedup.png", 15 * 3600),
    ("8-hour-speedup.png", 8 * 3600),
    ("3-hour-speedup.png", 3 * 3600),
    ("1-hour-speedup.png", 3600),
    ("15-min-speedup.png", 15 * 60),
    ("1-min-speedup.png", 60)
]

class BuildingUpgrader:
    def __init__(self, device_name="moto-g51"):
        self.adb = ADBController()
        self.images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resource", "images", "building-upgrade")
        self.vision = VisionEngine(self.images_dir)
        self.device_name = device_name
        
        self.config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, f"{self.device_name}-upgrade-config.json")
        self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def _sleep(self, base_time):
        extra = random.lognormvariate(-0.5, 0.8)
        actual_time = (base_time * 0.95) + extra
        time.sleep(actual_time)

    def _get_or_find_location(self, key, template_name, screen_img=None, threshold=0.7, tap=False, delay=0.7):
        template_path = os.path.join(self.images_dir, template_name)
        template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        box_dims = None
        if template_img is not None:
            box_dims = (template_img.shape[1], template_img.shape[0])
            
        if key in self.config:
            loc = tuple(self.config[key])
            if tap:
                self.adb.tap(loc[0], loc[1], box_dims=box_dims)
                self._sleep(delay)
            return loc
        
        print(f"Finding location for '{key}' using template '{template_name}'...")
        if screen_img is None:
            screen_img = self.adb.capture_screen()
            if screen_img is None:
                return None
            
        if template_img is None:
            print(f"Error: Template '{template_name}' not found.")
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
                self.adb.tap(center[0], center[1], box_dims=box_dims)
                self._sleep(delay)
            return center
            
        print(f"Could not find '{key}' on screen.")
        return None

    def read_eta(self, screen_img):
        print("Reading ETA...")
        template_path = os.path.join(self.images_dir, "upgrade-button.png")
        template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        centers = self.vision.find_template_image(screen_img, template_img, threshold=0.7)
        if not centers:
            print("Upgrade button not found, cannot read ETA.")
            return None
            
        h, w = template_img.shape[:2]
        btn_x, btn_y = centers[0]
        btn_x = btn_x - w // 2
        btn_y = btn_y - h // 2
        
        crop_x1 = max(0, btn_x - 400)
        crop_y1 = max(0, btn_y - 20)
        crop_x2 = btn_x
        crop_y2 = btn_y + h + 20
        
        crop_img = screen_img[crop_y1:crop_y2, crop_x1:crop_x2]
        text = self.vision.extract_text(crop_img)
        print(f"Extracted ETA text: '{text}'")
        return parse_march_time_seconds(text)

    def use_speedups(self, required_seconds):
        print(f"Need to speedup {required_seconds} seconds.")
        remaining = required_seconds
        
        print("Swiping UP once to reach largest speedups...")
        self.adb.swipe(524, 2000, 524, 1000, 500)
        self._sleep(1.5)
        
        consecutive_swipes = 0
        while remaining > 0:
            screen_img = self.adb.capture_screen()
            if screen_img is None:
                self._sleep(2)
                continue
                
            use_btn_path = os.path.join(self.images_dir, "use-button.png")
            use_btn_img = cv2.imread(use_btn_path, cv2.IMREAD_COLOR)
            res_use = cv2.matchTemplate(screen_img, use_btn_img, cv2.TM_CCOEFF_NORMED)
            use_points = list(zip(*np.where(res_use >= 0.85)[::-1]))
            
            visible_speedups = []
            
            for speedup_img_name, amount in SPEEDUPS:
                template_path = os.path.join(self.images_dir, speedup_img_name)
                template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
                if template_img is None: continue
                
                res = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
                loc_match = np.where(res >= 0.925)
                points = list(zip(*loc_match[::-1]))
                
                if points:
                    pt = points[0]
                    speedup_y = pt[1] + template_img.shape[0] // 2
                    
                    closest_use_pt = None
                    if use_points:
                        for u_pt in use_points:
                            u_center_y = u_pt[1] + use_btn_img.shape[0] // 2
                            if abs(u_center_y - speedup_y) < 50:
                                closest_use_pt = u_pt
                                break
                    
                    if closest_use_pt:
                        use_loc = (int(closest_use_pt[0] + use_btn_img.shape[1] // 2), int(closest_use_pt[1] + use_btn_img.shape[0] // 2))
                        visible_speedups.append({
                            'name': speedup_img_name,
                            'amount': amount,
                            'use_loc': use_loc,
                            'img_shape': use_btn_img.shape
                        })
                        print(f"Found {speedup_img_name} ({amount}s) with Use button.")
            
            visible_speedups.sort(key=lambda x: x['amount'], reverse=True)
            tapped_any = False
            
            for sp in visible_speedups:
                if remaining >= sp['amount']:
                    uses = int(remaining // sp['amount'])
                    print(f"Decided to use {sp['name']} ({sp['amount']}s) {uses} times.")
                    
                    for _ in range(uses):
                        self.adb.simple_tap(sp['use_loc'][0], sp['use_loc'][1], custom_delay=0.2)
                        
                    remaining %= sp['amount']
                    print(f"Remaining time: {remaining}s")
                    tapped_any = True
                    if remaining <= 0:
                        break
                        
            if remaining <= 0:
                break
                
            if not tapped_any:
                if consecutive_swipes >= 3 and visible_speedups:
                    smallest_sp = visible_speedups[-1]
                    print(f"Stuck at top of list. Using {smallest_sp['name']} to finish {remaining}s.")
                    self.adb.tap(smallest_sp['use_loc'][0], smallest_sp['use_loc'][1], short_press=True, box_dims=(smallest_sp['img_shape'][1], smallest_sp['img_shape'][0]))
                    remaining -= smallest_sp['amount']
                    break
                    
                print("No suitable speedup <= remaining found. Swiping DOWN to find smaller speedups...")
                self.adb.swipe(524, 1000, 524, 2000, 500)
                self._sleep(1.5)
                consecutive_swipes += 1
            else:
                consecutive_swipes = 0
                
    def wait_for_completion(self):
        print("Waiting for completion screen...")
        # Actually, when speedup exceeds ETA, we automatically return to 5-after-completion
        completion_template = cv2.imread(os.path.join(self.images_dir, "5-after-completion.png"), cv2.IMREAD_COLOR)
        # We might not have a reliable template for completion, but the user says we return to 5-after-completion.
        # Let's wait until we see it, or just return since we've used enough speedups.
        self._sleep(2.0)
        return True

    def run_upgrade_loop(self):
        print("Starting Building Upgrade Loop. Waiting for user to tap a building...")
        while True:
            screen_img = self.adb.capture_screen()
            if screen_img is None:
                self._sleep(2)
                continue
                
            # Check if 1-upgrade-card is present by looking for the upgrade button
            upgrade_btn_loc = self._get_or_find_location('upgrade_button', 'upgrade-button.png', screen_img, threshold=0.7)
            if not upgrade_btn_loc:
                self._sleep(2)
                continue
                
            print("Upgrade card detected.")
            eta_seconds = self.read_eta(screen_img)
            if eta_seconds is None:
                print("Failed to read ETA. Assuming a default of 0 and letting user manually handle or skipping.")
                # We can't proceed safely without ETA, but let's try to just upgrade if we can't parse it?
                # For safety, let's wait a bit and retry.
                self._sleep(2)
                continue
                
            print(f"Total ETA in seconds: {eta_seconds}")
            
            # 2. Tap Upgrade button
            print("Tapping Upgrade...")
            self._get_or_find_location('upgrade_button', 'upgrade-button.png', screen_img, threshold=0.7, tap=True, delay=2.0)
            
            # 3. Tap Help button
            print("Waiting for Help button...")
            for _ in range(10):
                screen_img = self.adb.capture_screen()
                help_loc = self._get_or_find_location('help_button', 'help-button.png', screen_img, threshold=0.7, tap=True, delay=2.0)
                if help_loc:
                    break
                self._sleep(1)
            else:
                print("Help button not found. Proceeding anyway...")
                
            # 4. Tap Speedup button
            print("Waiting for Speedup button...")
            for _ in range(10):
                screen_img = self.adb.capture_screen()
                speedup_loc = self._get_or_find_location('speedup_button', 'speedup-button.png', screen_img, threshold=0.7, tap=True, delay=2.0)
                if speedup_loc:
                    break
                self._sleep(1)
            else:
                print("Speedup button not found. Aborting this upgrade cycle.")
                continue
                
            # 5-8. Use Speedups
            print("Entering Speedup Menu...")
            self._sleep(2.0) # Wait for speedup menu to load
            
            self.use_speedups(eta_seconds)
            
            self.wait_for_completion()
            print("Upgrade cycle completed. Returning to idle state...")
            self._sleep(3.0)

if __name__ == "__main__":
    upgrader = BuildingUpgrader()
    upgrader.run_upgrade_loop()
