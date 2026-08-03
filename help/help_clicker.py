#!/usr/bin/env python3
"""
Help module automation for Total Battle.
Randomly clicks the help button via two different methods.
Follows OOP and SOLID principles.
"""

import sys
import os
import time
import json
import random
import cv2
import numpy as np

# Ensure we can import from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adb import ADBController
from core.vision import VisionEngine

class HelpClicker:
    def __init__(self, device_name="moto-g51"):
        self.device_name = device_name
        self.adb = ADBController()
        
        # Path to help images
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.images_dir = os.path.join(base_dir, "resource", "images", "help")
        self.vision = VisionEngine(self.images_dir)
        
        # Path to config
        self.config_dir = os.path.join(base_dir, "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, f"{self.device_name}-config.json")
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
        """Sleep using a Log-Normal curve for human-like delay."""
        extra = random.lognormvariate(-0.5, 0.8)
        actual_time = (base_time * 0.95) + extra
        time.sleep(max(0.1, actual_time))

    def _get_or_find_location(self, key, template_name, screen_img=None, threshold=0.7, tap=False, delay=0.7):
        """Find a template on screen and save its center coordinates in config."""
        if key in self.config:
            loc = tuple(self.config[key])
            if tap:
                self.adb.tap(loc[0], loc[1])
                self._sleep(delay)
            return loc
            
        template_path = os.path.join(self.images_dir, template_name)
        template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        box_dims = None
        if template_img is not None:
            box_dims = (template_img.shape[1], template_img.shape[0])
        else:
            print(f"Error: Template '{template_path}' not found.")
            return None
        
        print(f"Finding location for '{key}' using template '{template_name}'...")
        if screen_img is None:
            screen_img = self.adb.capture_screen()
            
        if screen_img is None:
            print(f"Error: Failed to capture screen when looking for '{key}'.")
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

    def execute(self):
        """Randomly choose between two methods to press help."""
        method = random.choice([1, 2])
        print(f"Executing Help module using Method {method}")
        
        if method == 1:
            self._method_1_direct_help()
        else:
            self._method_2_via_clan_menu()

    def _method_1_direct_help(self):
        """Method 1: Scan for help-logo, save config, and click it."""
        print("[Method 1] Looking for direct help logo...")
        loc = self._get_or_find_location("help_logo", "help-logo.png", tap=True, delay=1.0, threshold=0.5)
        if loc:
            print(f"[Method 1] Clicked direct help logo at {loc}")
        else:
            print("[Method 1] Failed to find direct help logo.")

    def _method_2_via_clan_menu(self):
        """Method 2: Clan logo -> Clan help section -> Help all button -> Back 2x."""
        print("[Method 2] Accessing help via clan menu...")
        
        # 1. Click clan logo
        clan_loc = self._get_or_find_location("clan_logo", "clan-logo.png", tap=True, delay=2.0)
        if not clan_loc:
            print("[Method 2] Failed to find clan logo.")
            return
            
        # 2. Click clan help section
        help_section_loc = self._get_or_find_location("clan_help_section", "clan-help-section.png", tap=True, delay=2.0)
        if not help_section_loc:
            print("[Method 2] Failed to find clan help section.")
            self.adb.back()
            return
            
        # 3. Click help button
        help_btn_loc = self._get_or_find_location("help_all_button", "help-button.png", tap=True, delay=1.5)
        if not help_btn_loc:
            print("[Method 2] Failed to find help all button.")
        else:
            print("[Method 2] Clicked help all button successfully.")
            
        # 4. Press back 2 times
        print("[Method 2] Pressing back button 2 times...")
        back_btn = self.config.get("back_button", [73, 184]) # standard back button location
        self.adb.back(back_btn_loc=back_btn)
        self._sleep(1.0)
        self.adb.back(back_btn_loc=back_btn)
        self._sleep(1.0)
        print("[Method 2] Finished sequence.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Help Clicker Automation")
    parser.add_argument("--device", type=str, default="moto-g51", help="Device name configuration")
    args = parser.parse_args()
    
    clicker = HelpClicker(device_name=args.device)
    clicker.execute()

if __name__ == "__main__":
    main()
