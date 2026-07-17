import cv2
import easyocr

reader = easyocr.Reader(['en'])
img = cv2.imread('/home/celestial/Projects/total-battle-automation/chest-tracker/images/multiple-scan.png')
results = reader.readtext(img, detail=1)

# Sort by Y
results.sort(key=lambda r: r[0][0][1])

for bbox, text, conf in results:
    y = int(bbox[0][1])
    print(f"Y: {y} | Text: {text}")
