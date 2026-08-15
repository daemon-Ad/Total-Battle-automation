import cv2
import easyocr
import numpy as np
import os
import glob

class VisionEngine:
    def __init__(self, images_dir=None):
        # Initialize EasyOCR (uses CPU by default if GPU not configured)
        self.reader = easyocr.Reader(['en'], gpu=False)
        
        if images_dir is None:
            # Point to chest-tracker/images robustly
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.images_dir = os.path.join(base_dir, "images")
        else:
            self.images_dir = images_dir
            
        self.templates = {}
        self.ancient_templates = {}
        
        self._load_templates()
        self._load_ancient_templates()
        self._load_dark_omens_templates()

    def _load_templates(self):
        """Pre-load commonly used templates."""
        template_paths = {
            "clan_logo": os.path.join(self.images_dir, "clan-logo.png"),
            "gift_chests": os.path.join(self.images_dir, "clan-Gift-chests.png"),
            "back_button": os.path.join(self.images_dir, "back-button.png")
        }
        
        for name, path in template_paths.items():
            if os.path.exists(path):
                # Read in color for template matching if needed, or grayscale
                self.templates[name] = cv2.imread(path, cv2.IMREAD_COLOR)
            else:
                print(f"Warning: Template {path} not found.")

    def _load_ancient_templates(self):
        """Pre-load ancient chest templates for exact image matching."""
        ancients_dir = os.path.join(self.images_dir, "ancients")
        self.ancient_templates = {}
        if os.path.exists(ancients_dir):
            for path in glob.glob(os.path.join(ancients_dir, "*.png")):
                basename = os.path.basename(path)
                level_str = basename.replace("level-", "").replace(".png", "")
                try:
                    level = int(level_str)
                    img = cv2.imread(path, cv2.IMREAD_COLOR)
                    self.ancient_templates[level] = img
                except ValueError:
                    pass
        else:
            print(f"Warning: Ancients directory {ancients_dir} not found.")

    def _load_dark_omens_templates(self):
        """Pre-load dark omens chest templates for exact image matching."""
        dark_omens_dir = os.path.abspath(os.path.join(self.images_dir, "../../resource/images/dark-omens"))
        self.dark_omens_templates = {}
        if os.path.exists(dark_omens_dir):
            # Pick up both .png and .jpeg/.jpg
            patterns = [
                os.path.join(dark_omens_dir, "*.png"),
                os.path.join(dark_omens_dir, "*.jpeg"),
                os.path.join(dark_omens_dir, "*.jpg"),
            ]
            for pattern in patterns:
                for path in glob.glob(pattern):
                    basename = os.path.basename(path)
                    # Strip any extension: level-20.png -> 20, level-25.jpeg -> 25
                    name_no_ext = os.path.splitext(basename)[0]  # e.g. "level-20"
                    level_str = name_no_ext.replace("level-", "")
                    try:
                        level = int(level_str)
                        img = cv2.imread(path, cv2.IMREAD_COLOR)
                        if img is not None:
                            self.dark_omens_templates[level] = img
                            print(f"Loaded Dark Omens template: level {level} from {basename}")
                    except ValueError:
                        pass
        else:
            print(f"Warning: Dark Omens directory {dark_omens_dir} not found.")

    def find_template(self, screen_input, template_name, threshold=0.8):
        """
        Find a pre-loaded template on the screen.
        Returns the (x, y) coordinates of the center, or None.
        """
        if template_name not in self.templates:
            print(f"Template {template_name} not loaded.")
            return None

        if isinstance(screen_input, str):
            screen = cv2.imread(screen_input, cv2.IMREAD_COLOR)
        else:
            screen = screen_input
            
        if screen is None:
            return None

        template = self.templates[template_name]
        h, w = template.shape[:2]

        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= threshold)
        
        points = list(zip(*loc[::-1])) # (x, y) coordinates
        
        if points:
            # Return the center of the first match
            pt = points[0]
            center_x = pt[0] + w // 2
            center_y = pt[1] + h // 2
            return (center_x, center_y)
        
        return None

    def find_template_image(self, screen_img, template_img, threshold=0.8):
        """Find a template image array inside a screen image array."""
        h, w = template_img.shape[:2]
        res = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= threshold)
        points = list(zip(*loc[::-1]))
        
        if points:
            # We might want to return all points, or group them.
            # For simplicity, let's group close points.
            grouped_points = []
            for pt in points:
                # check if close to existing point
                close = False
                for gpt in grouped_points:
                    if abs(pt[0] - gpt[0]) < 20 and abs(pt[1] - gpt[1]) < 20:
                        close = True
                        break
                if not close:
                    grouped_points.append(pt)
            
            centers = [(pt[0] + w//2, pt[1] + h//2) for pt in grouped_points]
            return centers
        return []

    def extract_text(self, image_crop):
        """Extract text from an image crop using EasyOCR."""
        # Convert BGR to RGB for EasyOCR
        rgb_image = cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB)
        result = self.reader.readtext(rgb_image, detail=0)
        return " ".join(result).strip()

    def get_ancient_chest_level(self, chest_crop):
        """
        Use cv2.matchTemplate to find the best matching ancient chest image.
        """
        if not self.ancient_templates or chest_crop is None or chest_crop.size == 0:
            return 0
            
        best_level = 0
        best_match_val = -1
        all_scores = {}
        
        for level, ref_img in self.ancient_templates.items():
            if ref_img is None or ref_img.size == 0:
                continue
            
            h, w = ref_img.shape[:2]
            try:
                resized_crop = cv2.resize(chest_crop, (w, h))
                res = cv2.matchTemplate(resized_crop, ref_img, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                all_scores[level] = round(max_val, 3)
                
                if max_val > best_match_val:
                    best_match_val = max_val
                    best_level = level
            except Exception as e:
                pass
        
        print(f"[Ancients] Template scores: {all_scores} | Best: level={best_level} score={best_match_val:.3f}")
        
        # Confidence threshold — 0.45 is intentionally lenient since we always
        # pick the BEST match among all templates; we just want to exclude
        # completely unrelated crops.
        if best_match_val > 0.45:
            return best_level
        return 0

    def get_dark_omens_chest_level(self, chest_crop):
        """
        Compare the chest image crop against all Dark Omens templates (level 20, 25).
        Returns the best-matching level, or 35 if none match above the threshold.
        
        Strategy: resize the chest_crop UP to each template's size so we always
        compare at full template resolution — this avoids losing detail when
        the in-game crop is smaller than the reference image.
        """
        if not self.dark_omens_templates or chest_crop is None or chest_crop.size == 0:
            return 35  # fallback

        best_level = -1
        best_match_val = -1

        for level, ref_img in self.dark_omens_templates.items():
            if ref_img is None or ref_img.size == 0:
                continue

            h, w = ref_img.shape[:2]
            try:
                # Resize the crop UP to the template's size for a fair full-resolution compare
                resized_crop = cv2.resize(chest_crop, (w, h))
                res = cv2.matchTemplate(resized_crop, ref_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)

                if max_val > best_match_val:
                    best_match_val = max_val
                    best_level = level
            except Exception:
                pass

        # Only trust the result if confidence is high enough
        if best_match_val > 0.6:
            return best_level
        # Neither template matched — this is a level 35 chest
        return 35

    def parse_chest_block(self, screen_path, block_rect):
        """
        Extracts info from a specific chest block bounding box.
        block_rect is (x, y, w, h).
        """
        screen = cv2.imread(screen_path)
        x, y, w, h = block_rect
        block_img = screen[y:y+h, x:x+w]
        
        # Here we make assumptions about layout relative to the block.
        # This will require fine-tuning based on actual UI testing.
        # For now, we will run OCR on the whole block and try to parse it with logic,
        # or slice it into regions. 
        # Since EasyOCR provides bounding boxes (detail=1), we can get all text and sort by Y.
        
        rgb_block = cv2.cvtColor(block_img, cv2.COLOR_BGR2RGB)
        results = self.reader.readtext(rgb_block, detail=1)
        
        # Sort by vertical position (y coordinate of top-left corner)
        results.sort(key=lambda x: x[0][0][1])
        
        lines = [res[1] for res in results]
        return lines
