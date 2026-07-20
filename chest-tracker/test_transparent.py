import cv2
import glob
import os
from vision import VisionEngine

vision = VisionEngine()
print("Loaded chest color variants:")
for level, img in vision.chest_colors:
    print(f"Level {level}: shape {img.shape}")

# Test the newly added files
for path in glob.glob("images/chest-colors/*-t.png"):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    has_alpha = img.shape[2] == 4 if len(img.shape) > 2 else False
    print(f"Testing {os.path.basename(path)} -> Has Alpha: {has_alpha}")
    
    # Try testing the image against itself using the vision logic
    # It should ideally return the exact level if everything is working
    test_img = cv2.imread(path)
    detected_level = vision.get_chest_level_from_color(test_img)
    print(f"Detected level for {os.path.basename(path)}: {detected_level}")

