import time
import re
import random
import os
import json
import sys
import cv2
import threading
import queue
from datetime import datetime, timezone, timedelta
from adb import ADBController
from vision import VisionEngine
from db import log_chest
from time_utils import calculate_acquired_time
from points import calculate_points
from datetime import datetime, timedelta, timezone

class ChestExtractor:
    def __init__(self):
        self.adb = ADBController()
        self.vision = VisionEngine()
        self.run_active = False
        
        self.task_queue = queue.Queue()
        self.ocr_thread = None
        
        self.config_dir = "config"
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
            
        self.device_config = {}
        self._load_or_calibrate()

    def _load_or_calibrate(self):
        print("\n--- Device Configuration ---")
        device_name = input("Enter device name (e.g. 'galaxy_s22'): ").strip()
        if not device_name:
            device_name = "default"
            
        config_path = os.path.join(self.config_dir, f"{device_name}-config.json")
        
        if os.path.exists(config_path):
            print(f"Loading existing config for '{device_name}'...")
            with open(config_path, 'r') as f:
                self.device_config = json.load(f)
        else:
            print(f"No config found for '{device_name}'. Starting Calibration Phase...")
            self._calibrate(config_path)
            print("Calibration complete. Please restart the script to run the extraction.")
            sys.exit(0)
            
    def _calibrate(self, config_path):
        print("\n[Calibration] Make sure the game is on the main map/city screen.")
        input("Press Enter to continue...")
        
        config = {}
        
        # 1. Clan Logo
        print("Finding Clan Logo...")
        screen_img = self.adb.capture_screen()
        pos = self.vision.find_template(screen_img, "clan_logo")
        if pos:
            config['clan_logo'] = (int(pos[0]), int(pos[1]))
            self.adb.tap(pos[0], pos[1])
            print("Tapped Clan Logo. Waiting for clan page...")
            time.sleep(3)
        else:
            print("WARNING: Could not find Clan Logo! Using default coords (0,0)")
            config['clan_logo'] = (0, 0)
            
        # 2. Gift Chests
        print("Finding Gift Chests button...")
        screen_img = self.adb.capture_screen()
        pos = self.vision.find_template(screen_img, "gift_chests")
        if pos:
            config['gift_chests'] = (int(pos[0]), int(pos[1]))
            self.adb.tap(pos[0], pos[1])
            print("Tapped Gift Chests. Waiting for chest list...")
            time.sleep(3)
        else:
            print("WARNING: Could not find Gift Chests! Using default coords (0,0)")
            config['gift_chests'] = (0, 0)
            
        # 3. Triumphal Gifts
        print("Finding Triumphal Gifts tab...")
        screen_img = self.adb.capture_screen()
        H, W = screen_img.shape[:2]
        results = self.vision.reader.readtext(screen_img, detail=1)
        found_triumphal = False
        for bbox, text, conf in results:
            if "Triumphal" in text or "Triumphal Gifts" in text:
                cx = int((bbox[0][0] + bbox[2][0]) / 2)
                cy = int((bbox[0][1] + bbox[2][1]) / 2)
                config['triumphal_tab'] = (cx, cy)
                found_triumphal = True
                print("Found Triumphal tab.")
                break
        if not found_triumphal:
            config['triumphal_tab'] = (0, 0)
            print("WARNING: Could not find Triumphal Gifts tab.")
            
        # 4. Back Button & Safe Ratios
        config['back_button'] = (50, 50) # Fallback if we don't have a template for it yet
        print("Finding Back Button... (Using default template or hardcoded top-left)")
        back_pos = self.vision.find_template(screen_img, "back_button")
        if back_pos:
            config['back_button'] = (int(back_pos[0]), int(back_pos[1]))
            print(f"Found Back Button at {back_pos}")
            
        config['safe_zone_ratios'] = {"min": 555/2460, "max": 2200/2460}
        
        # Tap back twice to return home
        print("Returning home...")
        self.adb.tap(config['back_button'][0], config['back_button'][1])
        time.sleep(2)
        self.adb.tap(config['back_button'][0], config['back_button'][1])
        time.sleep(2)
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)

    def start(self):
        print("Starting extraction pipeline...")
        self.run_active = True
        
        # Start OCR Consumer Thread
        self.ocr_thread = threading.Thread(target=self._ocr_worker, daemon=True)
        self.ocr_thread.start()
        
        # 1. Navigate to Clan Page (if needed)
        # Assuming we start from the main city or map screen
        self._navigate_to_clan_page()
        
        # 2. Go to Gift Chests
        self._navigate_to_gift_chests()
        
        # 3. Process Gifts Tab
        print("Processing Gifts...")
        self._process_chest_list()
        
        # 4. Process Triumphal Gifts Tab
        print("Switching to Triumphal Gifts...")
        self._navigate_to_triumphal_gifts()
        
        print("Processing Triumphal Gifts...")
        self._process_chest_list()
        
        print("Extraction complete. Shutting down OCR thread...")
        self.run_active = False
        self.task_queue.put(None) # Sentinel to kill worker
        self.ocr_thread.join()
        
        print("Returning to homepage...")
        back_pos = self.device_config.get('back_button', (50, 50))
        self.adb.tap(back_pos[0], back_pos[1])
        time.sleep(1)
        self.adb.tap(back_pos[0], back_pos[1])
        print("All done.")
    def _navigate_to_clan_page(self):
        print("Navigating to Clan page using cached config...")
        pos = self.device_config.get('clan_logo')
        if pos and pos != [0, 0]:
            self.adb.tap(pos[0], pos[1])
            time.sleep(2)
        else:
            print("No valid clan logo coords in config.")

    def _navigate_to_gift_chests(self):
        print("Navigating to Gift Chests using cached config...")
        pos = self.device_config.get('gift_chests')
        if pos and pos != [0, 0]:
            self.adb.tap(pos[0], pos[1])
            time.sleep(3)
        else:
            print("No valid gift chests coords in config.")

    def _navigate_to_triumphal_gifts(self):
        print("Switching to Triumphal Gifts tab using cached config...")
        pos = self.device_config.get('triumphal_tab')
        if pos and pos != [0, 0]:
            self.adb.tap(pos[0], pos[1])
            time.sleep(2)
        else:
            print("No valid Triumphal tab coords in config.")

    def _process_chest_list(self):
        empty_retries = 0
        while self.run_active:
            screen_img = self.adb.capture_screen()
            
            if screen_img is None:
                print("Failed to capture screen.")
                time.sleep(1)
                continue
                
            H, W = screen_img.shape[:2]
            
            # 1. Dynamic Safe Zone Calculation
            safe_ratios = self.device_config.get('safe_zone_ratios', {"min": 555/2460, "max": 2200/2460})
            min_y = int(H * safe_ratios["min"])
            max_y = int(H * safe_ratios["max"])
            
            # 2. Fast Button Discovery
            crop_x1 = int(W * 0.6) # Only scan right 40% for buttons
            img_btn_crop = screen_img[:, crop_x1:]
            
            raw_results = self.vision.reader.readtext(img_btn_crop, detail=1)
            
            open_buttons = []
            for bbox, text, conf in raw_results:
                txt = text.strip().lower()
                if txt == "open" or txt == "delete":
                    new_bbox = [[pt[0] + crop_x1, pt[1]] for pt in bbox]
                    cy = int((new_bbox[0][1] + new_bbox[2][1]) / 2)
                    if min_y <= cy <= max_y:
                        open_buttons.append(new_bbox)
                        
            if not open_buttons:
                # To prevent false stopping on slow loads, we check text
                full_text = " ".join([t for b,t,c in raw_results]).lower()
                if "no gifts" in full_text or "empty" in full_text:
                    print("Empty list detected. Extraction complete for this tab.")
                    break
                    
                empty_retries += 1
                print(f"No valid buttons found in safe zone. Retrying... ({empty_retries}/3)")
                if empty_retries >= 3:
                    print("Max empty retries reached. Assuming tab is empty.")
                    break
                    
                time.sleep(1)
                continue
                
            # Reset counter on successful find
            empty_retries = 0
                
            # Sort buttons from top to bottom
            open_buttons.sort(key=lambda b: b[0][1])
            
            # 3. Batch Processing (Producer)
            chests_processed = len(open_buttons)
            batch_crops = []
            
            for btn_bbox in open_buttons:
                button_top_y = int(btn_bbox[0][1])
                button_bottom_y = int(btn_bbox[2][1])
                card_top_y = max(0, button_top_y - int(H * (300/2460))) # approximate chest card height
                
                # Crop strictly to the text area of this chest
                text_img_crop = screen_img[card_top_y:button_bottom_y, :int(W * 0.75)]
                
                x_left = 10 
                x_right = 150 
                color_img_crop = screen_img[card_top_y:button_bottom_y, x_left:x_right]
                
                batch_crops.append((text_img_crop, color_img_crop))
                
            if batch_crops:
                # Push the batch to the background thread for heavy OCR
                self.task_queue.put(batch_crops)
                
            # 4. Batch Tapping (Fast UI Driving)
            if chests_processed > 0:
                top_btn = open_buttons[0]
                cx = int((top_btn[0][0] + top_btn[2][0]) / 2)
                cy = int((top_btn[0][1] + top_btn[2][1]) / 2)
                
                print(f"[Driver] Found {chests_processed} chests. Queued for OCR. Tapping instantly.")
                for _ in range(chests_processed):
                    self.adb.tap(cx, cy)
                    time.sleep(0.3) # Wait for animation/slide
                
                # Wait for the next batch of chests to slide all the way up
                time.sleep(0.3)
            else:
                print("Failed to process any chests in this batch. Retrying...")
                time.sleep(1)

    def _ocr_worker(self):
        """Background thread that pulls images from the queue and runs heavy OCR."""
        print("[OCR Worker] Thread started.")
        while True:
            batch = self.task_queue.get()
            if batch is None:
                print("[OCR Worker] Received shutdown signal.")
                self.task_queue.task_done()
                break
                
            for text_img_crop, color_img_crop in batch:
                results = self.vision.reader.readtext(text_img_crop, detail=1)
                results.sort(key=lambda r: r[0][0][1])
                chest_texts = [text for bbox, text, conf in results]
                
                # Parse the extracted text
                title = ""
                player = ""
                source = ""
                timer = ""
                is_expired = False
                
                for line_raw in chest_texts:
                    line = line_raw.strip()
                    line_lower = line.lower()
                    
                    if "delete" in line_lower:
                        is_expired = True
                        continue
                        
                    if "from:" in line_lower:
                        player = line_lower.split("from:")[1].strip()
                        idx = line_lower.find("from:") + 5
                        player = line[idx:].strip()
                        continue
                        
                    if "source:" in line_lower:
                        idx = line_lower.find("source:") + 7
                        source = line[idx:].strip()
                        continue
                        
                    if "contains:" in line_lower:
                        continue
                        
                    clean_line = line_lower.replace('i', '1').replace('l', '1').replace('o', '0')
                    time_matches = re.findall(r'\d+[hms]', clean_line)
                    if time_matches:
                        timer = " ".join(time_matches)
                        continue
                        
                    if not title and len(line) >= 3:
                        title = line
                        
                if not title and not player and not source:
                    continue
                    
                # 1. Determine Type
                chest_type = "common"
                source_lower = source.lower()
                title_lower = title.lower()
                
                is_event = False
                if "crypt" not in source_lower and "citadel" not in source_lower and not is_expired:
                     is_event = True
                     chest_type = "event"
                     
                if "clan wealth" in source_lower or "clan wealth" in title_lower:
                    player = "Clan"
                    if "rare" in title_lower: chest_type = "rare"
                    elif "epic" in title_lower or "legendary" in title_lower: chest_type = "epic"
                    else: chest_type = "common"
                elif not is_event:
                    if "rare" in source_lower or "rare" in title_lower: chest_type = "rare"
                    elif "epic" in source_lower or "epic" in title_lower: chest_type = "epic"
                    
                # 2. Determine Level
                level = 0
                match = re.search(r'Level (\d+)', source, re.IGNORECASE)
                if match:
                    level = int(match.group(1))
                else:
                    level = self.vision.get_chest_level_from_color(color_img_crop)
                    if level == 0 or (level == 5 and chest_type == "event"):
                        level = 15
                        chest_type = "event"
                        
                if "runic" in source_lower or "runic" in title_lower:
                    if level >= 40: level = 25
                    elif level >= 35: level = 20
                    elif level >= 30: level = 15
                    elif level >= 25: level = 10
                    elif level >= 20: level = 5
                    chest_type = "common"
                    
                if "summoning" in source_lower and "dark" in source_lower and "omens" in source_lower:
                    chest_type = "epic"
                    level = 30
                elif "dark omens" in source_lower or "dark omens" in title_lower:
                    chest_type = "event"
                    if level < 20:
                        level = 20
                        
                if "olympus" in source_lower or "olympus" in title_lower:
                    chest_type = "event"
                    level = 25
                    
                if "ragnarok" in source_lower or "ragnarok" in title_lower:
                    chest_type = "event"
                    level = 25
                    
                if "tartaros" in source_lower or "tartaros" in title_lower:
                    chest_type = "epic"
                        
                if is_expired and level == 0:
                    level = 20
                    chest_type = "common"
                    
                if not title: title = "Unknown Chest"
                if not player: player = "Unknown Player"
                if not source: source = "Unknown Source"
                
                if is_expired:
                    acquired_at = datetime.now(timezone.utc) - timedelta(days=1)
                else:
                    acquired_at = calculate_acquired_time(timer)
                    
                pts = calculate_points(chest_type, level)
                
                log_chest(player, title, chest_type, level, source, timer, acquired_at, pts)
                
            self.task_queue.task_done()

if __name__ == "__main__":
    extractor = ChestExtractor()
    extractor.start()
