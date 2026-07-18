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
                    time.sleep(2.0)
                    return
                    
        print("WARNING: Could not find city/map icon for recovery.")

    def _find_and_tap_dynamic(self, template_name, retries=3, wait=1.0, threshold=0.7, delay=0.7):
        """Dynamically find a template on screen without using the config cache. Ideal for lagging UI."""
        print(f"Dynamically looking for '{template_name}' (bypassing config cache)...")
        for attempt in range(retries):
            screen_img = self.adb.capture_screen()
            if screen_img is None: 
                time.sleep(wait)
                continue
                
            template_path = os.path.join(self.images_dir, template_name)
            template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if template_img is None: return None
            
            h, w = template_img.shape[:2]
            res = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val >= threshold:
                center = (max_loc[0] + w // 2, max_loc[1] + h // 2)
                self.adb.tap(center[0], center[1])
                time.sleep(delay)
                return center
                
            print(f"Attempt {attempt+1}/{retries}: Could not find {template_name}. Waiting {wait}s...")
            time.sleep(wait)
            
        return None

    def _speedup_sequence(self, is_last_iteration):
        """Steps 11-12: Handle march time and speedups"""
        print("Waiting for taskbar to appear...")
        time.sleep(1) # Wait for task bar
        
        screen_img = self.adb.capture_screen()
        if screen_img is None: return False
        speedup_loc = self._get_or_find_location('crypter_speedup_button', 'speedup-button.png', screen_img, threshold=0.7, tap=True, delay=0.7)
        if not speedup_loc:
            print("ERROR: Could not find speedup button.")
            return False
            
        time.sleep(1) # Wait for Use button to appear
        
        screen_img = self.adb.capture_screen()
        if screen_img is None: return False
        
        use_btn_loc = self._get_or_find_location('crypter_use_button', 'use-button.png', screen_img, threshold=0.7)
        if not use_btn_loc:
            print("ERROR: Could not find Use button.")
            return False
            
        uses = 5
        print(f"Tapping Use button {uses} times.")
        
        for _ in range(uses):
            self.adb.tap(use_btn_loc[0], use_btn_loc[1])
            time.sleep(0.35)
            
        if is_last_iteration:
            print("Last iteration reached. Terminating without wait time.")
            return True
            
        wait_taskbar = self.config.get('crypter_taskbar_close_wait', 1.5)
        print(f"Waiting {wait_taskbar}s before closing taskbar...")
        time.sleep(wait_taskbar)
        
        # Tap back button to return to home screen map
        print("Pressing back button to return to homescreen.")
        self._get_or_find_location('back_button', 'back-button.png', tap=True, delay=2.0)
        
        # Visual Wait Loop: Wait until speedup button disappears from homescreen
        print("Waiting on homescreen for march to complete...")
        speedup_img = cv2.imread(os.path.join(self.images_dir, 'speedup-button.png'), cv2.IMREAD_COLOR)
        wait_speedup = self.config.get('crypter_speedup_loop_wait', 3.0)
        
        while True:
            screen_img = self.adb.capture_screen()
            if screen_img is None:
                time.sleep(2)
                continue
            
            # Check if speedup button is visible on screen
            res = cv2.matchTemplate(screen_img, speedup_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val < 0.7:
                print("Speedup banner disappeared. March is complete!")
                break
                
            print(f"Carter is still marching... waiting {wait_speedup}s.")
            time.sleep(wait_speedup)
            
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
            time.sleep(wait_watchtower)
            
            # Step 4: Go button (First crypt)
            print("Step 4: Finding Go Button...")
            if not self._get_or_find_location('crypter_go_button', 'go-button.png', tap=True):
                self._recover_via_city_icon()
                continue
            # Increased time to let the UI map center smoothly
            time.sleep(wait_center)
            
            # Step 5 & 6: Center tap (skipping redline check)
            print("Step 6: Tapping Center of Screen...")
            screen_img = self.adb.capture_screen()
            if screen_img is None: 
                print("Screen capture failed, aborting iteration.")
                self._recover_to_map()
                continue
                
            center_loc = self._get_center_screen(screen_img)
            self.adb.tap(center_loc[0], center_loc[1])
            time.sleep(1.0)
            
            # Step 7: Explore button
            print("Step 7: Visually Finding Explore Button...")
            explore_loc = self._find_and_tap_dynamic('explore-button.png', retries=3, wait=1.0)
            
            if not explore_loc:
                print("Could not enter explore menu (explore button not found). Attempting UI recovery via city icon...")
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
    iters = 10
    if len(sys.argv) > 1:
        iters = int(sys.argv[1])
    crypter.run_loop(iters)
