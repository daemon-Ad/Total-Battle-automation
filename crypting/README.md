# Total Battle Crypting Automation

An automated, high-performance script designed to handle the crypting process in Total Battle. This project automates repetitive crypting tasks by driving the game directly via ADB (Android Debug Bridge), using computer vision to navigate the UI, verify captain availability, manage Tar resources, and efficiently deploy march speedups.

## Technology Stack

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![OpenCV](https://img.shields.io/badge/opencv-%23white.svg?style=for-the-badge&logo=opencv&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white)
![Android](https://img.shields.io/badge/Android-3DDC84?style=for-the-badge&logo=android&logoColor=white)

## System Overview

This automation eliminates the manual grind of sending marches to crypts. It is designed to be robust and efficient, adapting to the game's UI and ensuring optimal resource usage.

### 1. Intelligent UI Navigation
The script uses dynamic template matching (`cv2.matchTemplate`) to find buttons and icons on the screen. Instead of relying on hardcoded coordinates that break across different devices or resolutions, the script "learns" the layout of your game during its first iteration and caches these coordinates for blazing-fast execution on subsequent runs. It also skips redundant menus (like the Crypts tab) after the first iteration to save time.

### 2. Automated Resource Management
Before sending a march, the system performs critical safety checks using Optical Character Recognition (OCR):
- **Captain Verification:** Ensures that the correct captain (Carter) is selected and active.
- **Tar Capacity Check:** Reads the available Tar and the Tar carrying capacity, ensuring you never send a march without sufficient resources. It intelligently caches the carrying capacity during the first run and simply decrements the available Tar locally on subsequent runs, minimizing OCR overhead and vastly speeding up the loop.

### 3. Smart Speedup Deployment
The automation reads the exact march time directly from the explore screen using PyTorch-backed EasyOCR. It then calculates the optimal number of times to press the "Use" button (which halves the remaining time) to reduce the march time to under 23 seconds, maximizing speedup efficiency without wasting them. The script will automatically terminate without waiting during the final requested iteration.

## Prerequisites

- Python 3.10+
- ADB (Android Debug Bridge) enabled emulator or physical Android device connected via USB/WiFi.
- The game must be open and on the main map/city screen before starting.

## Installation & Setup

1. Ensure all dependencies are installed from the root directory:
   ```bash
   pip install -r requirements.txt
   ```

2. Connect your Android device via ADB and verify it is detected:
   ```bash
   adb devices
   ```

## Running the Automation

To start the automation, simply run the script. By default, it will execute 10 crypting iterations.
```bash
python crypting/crypter.py
```

If you want to specify a different number of iterations, pass the number as an argument:
```bash
python crypting/crypter.py 5
```

### The Calibration Phase
During the very first iteration, the script will take slightly longer as it captures the screen to find and memorize the locations of various buttons (Watchtower, Crypts Tab, Explore, Use buttons, etc.). These coordinates are saved securely in the `config/` directory. All subsequent iterations will bypass the visual search and use these cached locations to operate at maximum speed. 

If your game layout changes (e.g., you rotate the screen or change devices), simply delete the configuration file in the `config/` directory to force a fresh recalibration.
