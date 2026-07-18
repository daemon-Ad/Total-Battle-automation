import subprocess
import time
import random
import os

class ADBController:
    def __init__(self, device_id=None):
        self.device_id = device_id
        self._check_connection()

    def _adb_command(self, *args):
        """Helper to run adb commands."""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def _check_connection(self):
        """Verify ADB is connected and device is found."""
        result = self._adb_command("devices")
        lines = result.stdout.strip().split('\n')[1:]
        devices = [line.split('\t')[0] for line in lines if line.strip()]
        
        if not devices:
            print("Warning: No ADB devices found.")
        elif self.device_id and self.device_id not in devices:
            print(f"Warning: Device {self.device_id} not found. Available devices: {devices}")
        else:
            print(f"Connected to ADB. Devices: {devices}")

    def capture_screen(self):
        """Capture the screen in-memory using exec-out and return as OpenCV BGR array."""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
            
        # We only use PNG mode (-p) streamed directly over stdout. 
        # This is very fast and NEVER writes to the phone's memory/disk.
        # The raw framebuffer method was causing freezes on some devices.
        png_cmd = cmd + ["exec-out", "screencap", "-p"]
        try:
            proc = subprocess.run(png_cmd, capture_output=True, timeout=10)
            import numpy as np
            import cv2
            image_array = np.frombuffer(proc.stdout, dtype=np.uint8)
            img_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            return img_bgr
        except subprocess.TimeoutExpired:
            print("ERROR: adb screencap timed out!")
            return None

    def tap(self, x, y, jitter_range=15):
        """Tap at the given x, y coordinates with a slight random jitter to appear human."""
        jitter_x = random.randint(-jitter_range, jitter_range)
        jitter_y = random.randint(-jitter_range, jitter_range)
        
        final_x = max(0, x + jitter_x)
        final_y = max(0, y + jitter_y)
        
        self._adb_command("shell", "input", "tap", str(final_x), str(final_y))
        
        # Human-like delay after tapping (randomized)
        time.sleep(random.uniform(0.15, 0.35))

    def back(self):
        """Press the Android Back button to close menus/popups."""
        self._adb_command("shell", "input", "keyevent", "4")
        time.sleep(1)

    def swipe(self, x1, y1, x2, y2, duration_ms=500):
        """Swipe from (x1, y1) to (x2, y2)."""
        # Add slight jitter to duration and coordinates
        jitter_x1 = random.randint(-10, 10)
        jitter_y1 = random.randint(-10, 10)
        jitter_x2 = random.randint(-10, 10)
        jitter_y2 = random.randint(-10, 10)
        actual_duration = duration_ms + random.randint(-100, 100)
        
        self._adb_command("shell", "input", "swipe", 
                          str(x1 + jitter_x1), str(y1 + jitter_y1), 
                          str(x2 + jitter_x2), str(y2 + jitter_y2), 
                          str(actual_duration))
        
        time.sleep(random.uniform(0.5, 1.0))

if __name__ == "__main__":
    # Test script
    adb = ADBController()
    print("Testing screen capture...")
    adb.capture_screen("test_screen.png")
    if os.path.exists("test_screen.png"):
        print("Screen capture successful. Saved to test_screen.png")
