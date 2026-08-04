import sys
import os
import time
import json
import cv2
import numpy as np
import random

# Ensure we can import from core (sys.path hack since script is in a subdirectory)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adb import ADBController
from core.vision import VisionEngine

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
        self.smart_crypting = False
        self.dynamic_crypt_img = None

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def _sleep(self, base_time):
        """Sleep using a Log-Normal curve to guarantee safe minimum times with human-like long tails."""
        # Log-Normal distribution perfectly mimics human delay/distraction patterns.
        # mu=-0.5, sigma=0.8 means median extra delay is ~0.6s, but frequently hits 1-3s, and rarely 5-8s.
        extra = random.lognormvariate(-0.5, 0.8)
        actual_time = (base_time * 0.95) + extra
        time.sleep(actual_time)

    def _get_or_find_location(self, key, template_name, screen_img=None, threshold=0.7, tap=False, delay=0.7, short_press=False):
        template_path = os.path.join(self.images_dir, template_name)
        template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        box_dims = None
        if template_img is not None:
            box_dims = (template_img.shape[1], template_img.shape[0])
            
        if key in self.config:
            loc = tuple(self.config[key])
            if tap:
                self.adb.tap(loc[0], loc[1], short_press=short_press, box_dims=box_dims)
                self._sleep(delay) # Small gap for UI to load
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
                self.adb.tap(center[0], center[1], short_press=short_press, box_dims=box_dims)
                self._sleep(delay)
            return center
            
        print(f"Could not find '{key}' on screen.")
        return None

    def _get_center_screen(self, screen_img):
        if 'center_screen' in self.config:
            return tuple(self.config['center_screen'])
        h, w = screen_img.shape[:2]
        center = (w // 2, h // 2)
        self.config['center_screen'] = center
        return center
    def _recover_via_city_icon(self):
        """Perform UI recovery by tapping the city/map icon to close popups and return to the map."""
        print("Recovering UI by pressing the City/Map icon to clear popups...")
        if 'city_icon' in self.config:
            loc = self.config['city_icon']
            self.adb.tap(loc[0], loc[1])
            time.sleep(2.0)
            return
            
        # If not in config, find it visually and save it
        city_icon_path = os.path.abspath(os.path.join(self.images_dir, "..", "..", "resource", "images", "city-icon.png"))
        screen_img = self.adb.capture_screen()
        if screen_img is not None:
            template_img = cv2.imread(city_icon_path, cv2.IMREAD_COLOR)
            if template_img is not None:
                h, w = template_img.shape[:2]
                res = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= 0.6:
                    center = (max_loc[0] + w // 2, max_loc[1] + h // 2)
                    self.config['city_icon'] = center
                    self._save_config()
                    print(f"Saved 'city_icon' at {center}")
                    self.adb.tap(center[0], center[1])
                    self._sleep(2.0)
                    return
                    
        print("WARNING: Could not find city/map icon for recovery.")

    def _find_and_tap_dynamic(self, template_name, retries=3, wait=1.0, threshold=0.85, delay=0.7):
        """Dynamically find a template on screen without using the config cache. Ideal for lagging UI."""
        print(f"Dynamically looking for '{template_name}' (bypassing config cache)...")
        for attempt in range(retries):
            screen_img = self.adb.capture_screen()
            if screen_img is None: 
                self._sleep(wait)
                continue
                
            template_path = os.path.join(self.images_dir, template_name)
            template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if template_img is None: return None
            
            h, w = template_img.shape[:2]
            res = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val >= threshold:
                center = (max_loc[0] + w // 2, max_loc[1] + h // 2)
                print(f"Found {template_name} with confidence {max_val:.2f}")
                self.adb.tap(center[0], center[1], box_dims=(w, h))
                self._sleep(delay)
                return center
                
            print(f"Attempt {attempt+1}/{retries}: Could not find {template_name} (Best match: {max_val:.2f}). Waiting {wait}s...")
            self._sleep(wait)
            
        return None

    def _perform_random_distraction(self):
        """Simulate a user performing other in-game tasks while waiting for a march to finish."""
        print("--- Initiating Interleaved Distraction Task ---")
        # In the future, this will block and call Clan Chests, Help All, etc. from other scripts.
        # For now, we simulate this by tapping the city icon, waiting, and returning.
        
        print("Distraction: Navigating to City/Clan view...")
        if 'city_icon' in self.config:
            loc = self.config['city_icon']
            self.adb.tap(loc[0], loc[1])
        else:
            # Fallback to recovery logic which will find and tap it
            self._recover_via_city_icon()
            
        # Simulate time spent doing tasks in another menu (e.g. 5 to 20 seconds)
        distraction_time = random.uniform(5.0, 20.0)
        print(f"Distraction: Simulating task for {distraction_time:.1f}s...")
        time.sleep(distraction_time) # We use raw sleep here because it's already highly randomized
        
        # We use the robust recovery method to guarantee we return to the map safely
        print("Distraction complete. Returning to map...")
        self._recover_via_city_icon()
        print("--- Resuming Crypting Wait Loop ---")

    def _acquire_dynamic_crypt_image(self, go_loc):
        """Dynamically crop the crypt icon from the watchtower list based on the Go button's location."""
        screen_img = self.adb.capture_screen()
        if screen_img is None: return
        go_x, go_y = go_loc
        # Ensure crop is within bounds
        try:
            # Tighter 80x80 crop to avoid purple level banners and blue list background
            # Centered on the original 185x180 region
            crop = screen_img[max(0, go_y - 265) : min(screen_img.shape[0], go_y - 185), 
                              max(0, go_x - 575) : min(screen_img.shape[1], go_x - 495)]
            if crop.shape[0] > 0 and crop.shape[1] > 0:
                self.dynamic_crypt_img = crop
                print(f"Captured dynamic crypt image of shape {crop.shape}")
        except Exception as e:
            print(f"Failed to capture dynamic crypt image: {e}")

    def _speedup_sequence(self, is_last_iteration):
        """Steps 11-12: Handle march time and speedups"""
        print("Waiting for taskbar to appear...")
        self._sleep(1) # Wait for task bar
        
        screen_img = self.adb.capture_screen()
        if screen_img is None: return False
        speedup_loc = self._get_or_find_location('crypter_speedup_button', 'speedup-button.png', screen_img, threshold=0.7, tap=True, delay=0.7)
        if not speedup_loc:
            print("ERROR: Could not find speedup button.")
            return False
            
        self._sleep(1) # Wait for Use button to appear
        
        screen_img = self.adb.capture_screen()
        if screen_img is None: return False
        
        use_btn_loc = self._get_or_find_location('crypter_use_button', 'use-button.png', screen_img, threshold=0.7)
        if not use_btn_loc:
            print("ERROR: Could not find Use button.")
            return False
            
        uses = 5
        print(f"Tapping Use button {uses} times.")
        
        use_template_path = os.path.join(self.images_dir, 'use-button.png')
        use_template = cv2.imread(use_template_path, cv2.IMREAD_COLOR)
        box_dims = None
        if use_template is not None:
            box_dims = (use_template.shape[1], use_template.shape[0])
        
        for _ in range(uses):
            self.adb.tap(use_btn_loc[0], use_btn_loc[1], short_press=True, box_dims=box_dims)
            self._sleep(0.35)
            
        if is_last_iteration:
            print("Last iteration reached. Terminating without wait time.")
            return True
            
        wait_taskbar = self.config.get('crypter_taskbar_close_wait', 1.5)
        print(f"Waiting {wait_taskbar}s before closing taskbar...")
        self._sleep(wait_taskbar)
        
        # Tap back button to return to home screen map
        print("Pressing back button to return to homescreen.")
        self._get_or_find_location('back_button', 'back-button.png', tap=True, delay=2.0)
        
        # Visual Wait Loop: Wait until speedup button disappears from homescreen
        print("Waiting on homescreen for march to complete...")
        speedup_img = cv2.imread(os.path.join(self.images_dir, 'speedup-button.png'), cv2.IMREAD_COLOR)
        wait_speedup = self.config.get('crypter_speedup_loop_wait', 5.0)
        
        while True:
            screen_img = self.adb.capture_screen()
            if screen_img is None:
                self._sleep(2)
                continue
            
            # Check if speedup button is visible on screen
            res = cv2.matchTemplate(screen_img, speedup_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val < 0.7:
                print("Speedup banner disappeared. March is complete!")
                break
                
            print(f"Carter is still marching... waiting {wait_speedup}s.")
            
            # 20% chance to perform a distraction instead of just waiting
            if random.random() < 0.20:
                self._perform_random_distraction()
            else:
                self._sleep(wait_speedup)
            
        return True

    def run_loop(self, iterations=10):
        print("Starting Crypting Automation...")
        for i in range(1, iterations + 1):
            print(f"\n--- Iteration {i}/{iterations} ---")
            
            wait_watchtower = self.config.get('crypter_watchtower_load_wait', 2.0)
            wait_center = self.config.get('crypter_go_to_center_wait', 2.0)
            
            # Step 1: Watchtower
            print("Step 1: Finding Watchtower...")
            if not self._get_or_find_location('crypter_watchtower_icon', 'watchtower-icon.png', tap=True):
                break
                
            # Step 2 & 3: Crypts tab
            if i == 1:
                print("Step 2: Finding Crypts Tab...")
                if not self._get_or_find_location('crypter_crypts_tab', 'crypts-tab.png', tap=True):
                    break
                    
            print(f"Waiting {wait_watchtower}s for Watchtower list to fully refresh and stabilize...")
            self._sleep(wait_watchtower)
            
            # Step 4: Go button (First crypt)
            print("Step 4: Finding Go Button...")
            go_loc = self._get_or_find_location('crypter_go_button', 'go-button.png', tap=False)
            if not go_loc:
                self._recover_via_city_icon()
                continue
                
            if self.smart_crypting:
                self._acquire_dynamic_crypt_image(go_loc)
                
            # Tap it
            self.adb.tap(go_loc[0], go_loc[1], box_dims=(400, 102))
            self._sleep(0.7)
            
            # Increased time to let the UI map center smoothly
            self._sleep(wait_center)
            
            # Step 5 & 6: Center tap (skipping redline check)
            print("Step 6: Tapping Crypt...")
            screen_img = self.adb.capture_screen()
            if screen_img is None: 
                print("Screen capture failed, aborting iteration.")
                self._recover_via_city_icon()
                continue
                
            if self.smart_crypting and self.dynamic_crypt_img is not None:
                print("Smart Crypting: Scanning screen for the crypt...")
                # Constrain search to 5%-95% X, 20%-75% Y to avoid UI and focus on map
                h, w = screen_img.shape[:2]
                search_region = screen_img[int(h*0.20):int(h*0.75), int(w*0.05):int(w*0.95)]
                res = cv2.matchTemplate(search_region, self.dynamic_crypt_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                
                # Adjust back to full screen coordinates
                match_x = max_loc[0] + int(w*0.05) + self.dynamic_crypt_img.shape[1] // 2
                match_y = max_loc[1] + int(h*0.20) + self.dynamic_crypt_img.shape[0] // 2
                print(f"Smart Crypting: Found best crypt match at ({match_x}, {match_y}) with confidence {max_val:.2f}")
                self.adb.tap(match_x, match_y)
            else:
                center_loc = self._get_center_screen(screen_img)
                self.adb.tap(center_loc[0], center_loc[1])
                
            self._sleep(1.0)
            
            # Step 7: Explore button
            print("Step 7: Visually Finding Explore Button...")
            explore_loc = self._find_and_tap_dynamic('explore-button.png', retries=3, wait=1.0)
            
            if not explore_loc:
                print("Could not enter explore menu (explore button not found).")
                if not self.smart_crypting:
                    print("Game likely offset the crypt. Enabling Smart Crypting for subsequent iterations!")
                    self.smart_crypting = True
                print("Attempting UI recovery via city icon...")
                self._recover_via_city_icon()
                continue
            
            # Step 10: Explore (Launch) Button
            print("Step 10: Tapping Explore (Launch) Button...")
            launch_loc = self._find_and_tap_dynamic('explore-button.png', retries=3, wait=1.0)
            if not launch_loc:
                print("Could not find final Explore button. Recovering via city icon...")
                self._recover_via_city_icon()
                continue
            
            # Step 11 & 12: Speedup and Wait
            print("Step 11: Handling Speedups...")
            is_last_iteration = (i == iterations)
            if not self._speedup_sequence(is_last_iteration):
                self._recover_via_city_icon()
                continue
                
            print(f"Iteration {i} complete.")
            
        print("Crypting Automation Finished.")

if __name__ == "__main__":
    crypter = Crypter("moto-g51")
    # Take number of iterations from user if provided via CLI
    iters = 40
    if len(sys.argv) > 1:
        iters = int(sys.argv[1])
    crypter.run_loop(iters)
