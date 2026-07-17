import time
import re
import random
from adb import ADBController
from vision import VisionEngine
from db import log_chest
from time_utils import calculate_acquired_time
from points import calculate_points
from datetime import datetime, timedelta, timezone
import build_site

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
        
        print("Extraction complete. Generating static site files...")
        build_site.main()
        print("Static site updated.")
        
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
        cached_open_btn = None
        cached_text_crop = None
        
        while self.run_active:
            screen_path = self.adb.capture_screen()
            
            import cv2
            img = cv2.imread(screen_path)
            H, W = img.shape[:2]
            
            if not cached_open_btn:
                # First time: Find the top-most "Open" button
                crop_y1 = int(H * 0.20)
                crop_y2 = int(H * 0.45)
                img_crop = img[crop_y1:crop_y2, :]
                
                raw_results = self.vision.reader.readtext(img_crop, detail=1)
                
                # Find all "Open" or "Delete" buttons
                open_buttons = []
                for bbox, text, conf in raw_results:
                    txt = text.strip().lower()
                    if txt == "open" or txt == "delete":
                        new_bbox = [[pt[0], pt[1] + crop_y1] for pt in bbox]
                        open_buttons.append(new_bbox)
                
                if not open_buttons:
                    print("No 'Open' buttons found. List might be empty.")
                    break
                    
                # Sort by Y coordinate to get the topmost one
                open_buttons.sort(key=lambda b: b[0][1])
                top_open_bbox = open_buttons[0]
                
                # Cache the center coordinate for tapping
                cx = int((top_open_bbox[0][0] + top_open_bbox[2][0]) / 2)
                cy = int((top_open_bbox[0][1] + top_open_bbox[2][1]) / 2)
                cached_open_btn = (cx, cy)
                
                # Cache the vertical text area for this top chest
                button_bottom_y = int(top_open_bbox[2][1])
                button_top_y = int(top_open_bbox[0][1])
                card_top_y = max(0, button_top_y - 200) # approximate height of a chest card
                cached_text_crop = (card_top_y, button_bottom_y)
            
            # --- Fast Path using Cached Coordinates ---
            cx, cy = cached_open_btn
            card_top_y, button_bottom_y = cached_text_crop
            
            # Crop strictly to the text area of the top chest
            text_img_crop = img[card_top_y:button_bottom_y, :]
            
            # OCR is now nearly instant because the image is tiny
            results = self.vision.reader.readtext(text_img_crop, detail=1)
            
            # Sort by Y-coordinate to ensure top-to-bottom reading
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
                    # Keep original casing if possible
                    idx = line_lower.find("from:") + 5
                    player = line[idx:].strip()
                    continue
                    
                if "source:" in line_lower:
                    idx = line_lower.find("source:") + 7
                    source = line[idx:].strip()
                    continue
                    
                if "contains:" in line_lower:
                    continue
                    
                # Advanced timer parsing
                clean_line = line_lower.replace('i', '1').replace('l', '1').replace('o', '0')
                time_matches = re.findall(r'\d+[hms]', clean_line)
                if time_matches:
                    timer = " ".join(time_matches)
                    continue
                    
                # If we haven't found a title yet, and it's a decent length string, it's the title!
                # This bypasses the need for the word "Chest", which OCR fails on when the chest is expired and dark.
                if not title and len(line) >= 3:
                    title = line
            
            # 1. Determine Type
            chest_type = "common" # default
            source_lower = source.lower()
            title_lower = title.lower()
            
            is_event = False
            # If no crypt or citadel in source, it's an event chest (unless it's expired which might miss source)
            if "crypt" not in source_lower and "citadel" not in source_lower and not is_expired:
                 is_event = True
                 chest_type = "event"
                 
            # Clan wealth parsing overrides
            if "clan wealth" in source_lower or "clan wealth" in title_lower:
                player = "Clan"
                if "rare" in title_lower: chest_type = "rare"
                elif "epic" in title_lower or "legendary" in title_lower: chest_type = "epic"
                else: chest_type = "common" # covers common/uncommon
            elif not is_event:
                if "rare" in source_lower or "rare" in title_lower: chest_type = "rare"
                elif "epic" in source_lower or "epic" in title_lower: chest_type = "epic"

            # 2. Determine Level
            level = 0
            match = re.search(r'Level (\d+)', source, re.IGNORECASE)
            if match:
                level = int(match.group(1))
            else:
                # Fallback to color
                x_left = 10 
                x_right = 150 
                chest_crop = img[card_top_y:button_bottom_y, x_left:x_right]
                level = self.vision.get_chest_level_from_color(chest_crop)
                
                # If color guessing completely fails, default to 15 and treat as event
                # Also, if it incorrectly guesses level 5 for a blue (event) chest, default to 15.
                if level == 0 or (level == 5 and chest_type == "event"):
                    level = 15
                    chest_type = "event"
                    
            # Runic squad mapping
            if "runic" in source_lower or "runic" in title_lower:
                if level >= 40: level = 25
                elif level >= 35: level = 20
                elif level >= 30: level = 15
                elif level >= 25: level = 10
                elif level >= 20: level = 5
                chest_type = "common"
            # Expired fallback
            if is_expired and level == 0:
                level = 20
                chest_type = "common"
                
            # Stopping Condition: If we see the empty screen text, or no valid chest data
            full_text = " ".join(chest_texts).lower()
            if "no gifts" in full_text or "empty" in full_text or (not title and not player):
                print("Empty list detected. Extraction complete for this tab.")
                break
                
            # Clean up defaults
            if not title: title = "Unknown Chest"
            if not player: player = "Unknown Player"
            if not source: source = "Unknown Source"
            
            # 3. Calculate time and points
            if is_expired:
                acquired_at = datetime.now(timezone.utc) - timedelta(days=1)
            else:
                acquired_at = calculate_acquired_time(timer)
                
            pts = calculate_points(chest_type, level)
            
            # Log to Database
            log_chest(player, title, chest_type, level, source, timer, acquired_at, pts)
            
            # Tap the cached button ("Open" or "Delete")
            print(f"Tapping 'Open' at ({cx}, {cy})")
            self.adb.tap(cx, cy)
            
            # Wait for animation and next chest to slide up
            time.sleep(0.2)

if __name__ == "__main__":
    extractor = ChestExtractor()
    extractor.start()
