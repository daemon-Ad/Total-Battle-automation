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
            
        # Try raw uncompressed framebuffer first (bypasses slow on-device PNG encoding)
        raw_cmd = cmd + ["exec-out", "screencap"]
        try:
            proc = subprocess.run(raw_cmd, capture_output=True, timeout=5)
            raw_data = proc.stdout
            if len(raw_data) > 12:
                import struct
                import numpy as np
                import cv2
                w, h, f = struct.unpack('<III', raw_data[:12])
                image_bytes = raw_data[12:]
                
                # Check if size matches w*h*4 (RGBA)
                if len(image_bytes) == w * h * 4:
                    img_np = np.frombuffer(image_bytes, dtype=np.uint8).reshape((h, w, 4))
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
                    return img_bgr
        except Exception as e:
            print(f"Raw screencap optimization failed, falling back to PNG: {e}")
            
        # Fallback to PNG mode if raw parsing fails or geometry is unexpected
        png_cmd = cmd + ["exec-out", "screencap", "-p"]
        proc = subprocess.run(png_cmd, capture_output=True, timeout=5)
        import numpy as np
        import cv2
        image_array = np.frombuffer(proc.stdout, dtype=np.uint8)
        img_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
        return img_bgr

    def tap(self, x, y):
        """Tap at the given x, y coordinates with a slight random jitter to appear human."""
        jitter_x = random.randint(-5, 5)
        jitter_y = random.randint(-5, 5)
        
        final_x = max(0, x + jitter_x)
        final_y = max(0, y + jitter_y)
        
        self._adb_command("shell", "input", "tap", str(final_x), str(final_y))
        
        # Human-like delay after tapping (reduced per request)
        time.sleep(random.uniform(0.1, 0.2))

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
