import cv2
import numpy as np

def multi_scale_match(screen_crop, template):
    best_val = -1
    # Try different scales for the template
    for scale in np.linspace(0.3, 1.2, 20):
        w = int(template.shape[1] * scale)
        h = int(template.shape[0] * scale)
        if w < 10 or h < 10:
            continue
        if w > screen_crop.shape[1] or h > screen_crop.shape[0]:
            continue
            
        resized_template = cv2.resize(template, (w, h))
        res = cv2.matchTemplate(screen_crop, resized_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val > best_val:
            best_val = max_val
            
    return best_val

img = cv2.imread("../resource/images/dark-omens/level-20.png", cv2.IMREAD_COLOR)
screen = img.copy()
# Pad screen to simulate a larger crop
screen = cv2.copyMakeBorder(screen, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[50,0,50])
screen = cv2.resize(screen, (140, 140)) # Simulating the 140 width crop

val = multi_scale_match(screen, img)
print("Best match val:", val)
