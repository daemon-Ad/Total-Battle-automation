import cv2
import easyocr
import sys

image_path = "/home/celestial/Projects/total-battle-automation/chest-tracker/images/clan-chests-empty.png"
img = cv2.imread(image_path)
if img is None:
    print("Could not load image")
    sys.exit(1)

reader = easyocr.Reader(['en'], gpu=False)
results = reader.readtext(img, detail=0)
print("EXTRACTED TEXT:", results)
