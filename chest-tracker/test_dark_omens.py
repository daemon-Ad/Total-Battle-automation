import cv2
from vision import VisionEngine
import numpy as np

vision = VisionEngine(images_dir='images')

img = cv2.imread("../resource/images/dark-omens/level-20.png", cv2.IMREAD_UNCHANGED)
bgr = img[:, :, :3]
alpha = img[:, :, 3]

screen = bgr.copy()
# Fill transparent areas with some game-like color e.g. dark blue
screen[alpha < 128] = [50, 50, 100]

level = vision.get_dark_omens_chest_level(screen)
print("Detected Level:", level)
