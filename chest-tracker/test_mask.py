import cv2
import numpy as np
import glob
import os
from vision import VisionEngine

vision = VisionEngine()

target_size = (50, 50)
universal_mask = np.ones(target_size)
# Mask out the middle polygon (chest body).
# Assuming 50x50, middle 60% is from 10 to 40.
universal_mask[10:40, 10:40] = 0
mask_3d = np.expand_dims(universal_mask, axis=2)

print("Testing with universal border mask (ignoring middle 30x30 pixels):")

for path in glob.glob("images/chest-colors/*.png"):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    resized_img = cv2.resize(img, target_size)
    
    # Just to show it works, let's compare it to level-15.png
    ref_15 = cv2.imread("images/chest-colors/level-15.png", cv2.IMREAD_COLOR)
    if ref_15 is None: continue
    resized_15 = cv2.resize(ref_15, target_size)
    
    diff = (resized_img.astype("float") - resized_15.astype("float")) * mask_3d
    err = np.sum(diff ** 2) / (np.sum(universal_mask) * 3)
    
    print(f"MSE vs level-15.png for {os.path.basename(path)}: {err:.2f}")

