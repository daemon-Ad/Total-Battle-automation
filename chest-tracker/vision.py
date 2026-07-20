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
        self.chest_colors = {}
        
        self._load_templates()
        self._load_chest_colors()

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

    def _load_chest_colors(self):
        """Pre-load chest color references."""
        self.chest_colors = []  # List of (level, img)
        self.ancient_chest_colors = []
        
        colors_dir = os.path.join(self.images_dir, "chest-colors")
        if os.path.exists(colors_dir):
            import re
            for path in glob.glob(os.path.join(colors_dir, "*-t.png")):
                basename = os.path.basename(path) # e.g., level-15-t.png
                match = re.search(r'(\d+)', basename)
                if match:
                    try:
                        level = int(match.group(1))
                        # Load with alpha channel if present
                        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                        if img is not None:
                            self.chest_colors.append((level, img))
                    except ValueError:
                        pass
        else:
            print(f"Warning: Chest colors directory {colors_dir} not found.")
            
        ancient_dir = os.path.join(self.images_dir, "Identical-ancient ")
        if os.path.exists(ancient_dir):
            import re
            for path in glob.glob(os.path.join(ancient_dir, "*.png")):
                basename = os.path.basename(path)
                match = re.search(r'(\d+)', basename)
                if match:
                    try:
                        level = int(match.group(1))
                        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                        if img is not None:
                            self.ancient_chest_colors.append((level, img))
                    except ValueError:
                        pass
        else:
            print(f"Warning: Ancient colors directory {ancient_dir} not found.")

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

    def get_chest_level_from_color(self, chest_crop, ancient=False):
        """
        Compare the chest crop against known level colors.
        Uses structural similarity or simple MSE on resized images.
        """
        templates = self.ancient_chest_colors if ancient else self.chest_colors
        
        if not templates:
            return 0
            
        # Resize crop to a standard size for comparison (e.g., 50x50)
        target_size = (50, 50)
        resized_crop = cv2.resize(chest_crop, target_size)
        
        best_level = 0
        min_diff = float('inf')
        
        for level, ref_img in templates:
            if len(ref_img.shape) == 3 and ref_img.shape[2] == 4:
                # Image has an alpha channel (transparency)
                alpha = ref_img[:, :, 3] / 255.0
                mask = cv2.resize(alpha, target_size)
                bgr_ref = ref_img[:, :, :3]
                resized_ref = cv2.resize(bgr_ref, target_size)
            else:
                # Standard BGR image
                resized_ref = cv2.resize(ref_img, target_size)
                mask = np.ones(target_size)
                # Ignore the middle polygon (chest body) to focus on colored corners
                mask[10:40, 10:40] = 0
                
            # Expand mask to 3 dimensions for color broadcasting
            mask_3d = np.expand_dims(mask, axis=2)
            
            # Calculate Mean Squared Error (MSE) only on non-transparent pixels
            diff = (resized_crop.astype("float") - resized_ref.astype("float")) * mask_3d
            err = np.sum(diff ** 2)
            
            # Normalize error by the number of valid pixels
            valid_pixels = np.sum(mask) * 3
            if valid_pixels > 0:
                err /= valid_pixels
            else:
                err = float('inf')
            
            if err < min_diff:
                min_diff = err
                best_level = level
                
        return best_level

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
