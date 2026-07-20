import cv2
import glob
import os
import numpy as np
from collections import defaultdict

for path in glob.glob("images/chest-colors/*.png"):
    img = cv2.imread(path)
    if img is None:
        continue
    # resize to small to average
    img = cv2.resize(img, (50, 50))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # We want to ignore very dark (low V) or very washed out (low S) colors
    mask = (hsv[:,:,1] > 40) & (hsv[:,:,2] > 40)
    
    if np.any(mask):
        valid_hues = hsv[:,:,0][mask]
        median_hue = np.median(valid_hues)
        median_sat = np.median(hsv[:,:,1][mask])
        median_val = np.median(hsv[:,:,2][mask])
        print(f"{os.path.basename(path)} -> Median Hue: {median_hue}, Sat: {median_sat}, Val: {median_val}")
    else:
        print(f"{os.path.basename(path)} -> No saturated colors found")

