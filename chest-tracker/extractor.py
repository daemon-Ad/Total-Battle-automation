import time
import re
import random
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

    def start(self):
        print("Starting extraction pipeline...")
        self.run_active = True
        
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
        
        print("Extraction complete.")
        
    def _navigate_to_clan_page(self):
        print("Locating Clan logo...")
        screen_path = self.adb.capture_screen()
        pos = self.vision.find_template(screen_path, "clan_logo")
        if pos:
            print(f"Found clan logo at {pos}. Tapping...")
            self.adb.tap(pos[0], pos[1])
            time.sleep(2)
        else:
            print("Clan logo not found. Assuming already on clan page or manual navigation.")

    def _navigate_to_gift_chests(self):
        print("Locating Gift Chests icon...")
        screen_path = self.adb.capture_screen()
        pos = self.vision.find_template(screen_path, "gift_chests")
        if pos:
            print(f"Found gift chests at {pos}. Tapping...")
            self.adb.tap(pos[0], pos[1])
            time.sleep(3)
        else:
            print("Gift chests icon not found.")

    def _navigate_to_triumphal_gifts(self):
        # We can use OCR to find the 'Triumphal Gifts' tab and tap it
        screen_path = self.adb.capture_screen()
        import cv2
        img = cv2.imread(screen_path)
        results = self.vision.reader.readtext(img, detail=1)
        for bbox, text, conf in results:
            if "Triumphal" in text or "Triumphal Gifts" in text:
                # bbox is [top_left, top_right, bottom_right, bottom_left]
                top_left = bbox[0]
                bottom_right = bbox[2]
                cx = int((top_left[0] + bottom_right[0]) / 2)
                cy = int((top_left[1] + bottom_right[1]) / 2)
                self.adb.tap(cx, cy)
                time.sleep(2)
                return
        print("Could not find Triumphal Gifts tab.")

    def _process_chest_list(self):
        while self.run_active:
            screen_path = self.adb.capture_screen()
            
            import cv2
            img = cv2.imread(screen_path)
            if img is None:
                print("Failed to capture screen.")
                time.sleep(1)
                continue
                
            H, W = img.shape[:2]
            
            # 1. Dynamic Safe Zone Calculation
            min_y = int(H * (555 / 2460))
            max_y = int(H * (2200 / 2460))
            
            # 2. Fast Button Discovery
            crop_x1 = int(W * 0.6) # Only scan right 40% for buttons
            img_btn_crop = img[:, crop_x1:]
            
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
                print("No valid buttons found in safe zone. Retrying...")
                time.sleep(1)
                continue
                
            # Sort buttons from top to bottom
            open_buttons.sort(key=lambda b: b[0][1])
            
            # 3. Batch Processing
            chests_processed = 0
            for btn_bbox in open_buttons:
                button_top_y = int(btn_bbox[0][1])
                button_bottom_y = int(btn_bbox[2][1])
                card_top_y = max(0, button_top_y - int(H * (300/2460))) # approximate chest card height
                
                # Crop strictly to the text area of this chest
                text_img_crop = img[card_top_y:button_bottom_y, :int(W * 0.75)]
                
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
                        
                # If we got absolutely nothing, skip this button (OCR fail)
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
                    x_left = 10 
                    x_right = 150 
                    chest_crop = img[card_top_y:button_bottom_y, x_left:x_right]
                    level = self.vision.get_chest_level_from_color(chest_crop)
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
                chests_processed += 1
                
            # 4. Batch Tapping
            if chests_processed > 0:
                top_btn = open_buttons[0]
                cx = int((top_btn[0][0] + top_btn[2][0]) / 2)
                cy = int((top_btn[0][1] + top_btn[2][1]) / 2)
                
                print(f"Batch processed {chests_processed} chests. Tapping at ({cx}, {cy}) {chests_processed} times.")
                for _ in range(chests_processed):
                    self.adb.tap(cx, cy)
                    time.sleep(0.5) # Wait for animation/slide
                
                # Wait for the next batch of chests to slide all the way up
                time.sleep(1.5)
            else:
                print("Failed to process any chests in this batch. Retrying...")
                time.sleep(1)

if __name__ == "__main__":
    extractor = ChestExtractor()
    extractor.start()
