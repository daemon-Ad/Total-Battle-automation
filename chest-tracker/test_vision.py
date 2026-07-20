import cv2
import glob
import os
from vision import VisionEngine

vision = VisionEngine()
print("Loaded levels:", vision.chest_colors.keys())

for path in glob.glob("images/chest-colors/*.png"):
    img = cv2.imread(path)
    level = vision.get_chest_level_from_color(img)
    print(f"Testing {os.path.basename(path)} -> Detected Level: {level}")
