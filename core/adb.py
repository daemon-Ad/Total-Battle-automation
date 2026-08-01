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

    def tap(self, x, y, short_press=False, box_dims=None, custom_delay=None):
        """Simulate a perfect human tap using Gaussian scatter, finger roll, and Log-Normal durations."""
        
        # If we know the exact dimensions of the button, we map the Gaussian curve across the entire button surface.
        if box_dims:
            w, h = box_dims
            # sigma = width / 6 means 99.7% of taps fall safely within the button bounds.
            jitter_x = int(random.gauss(0, w / 6))
            jitter_y = int(random.gauss(0, h / 6))
            # Hard limit to ensure it never clicks completely outside the button
            jitter_x = max(int(-w/2.2), min(int(w/2.2), jitter_x))
            jitter_y = max(int(-h/2.2), min(int(h/2.2), jitter_y))
        else:
            # Fallback to standard tight cluster
            jitter_x = int(random.gauss(0, 7))
            jitter_y = int(random.gauss(0, 7))
            
        final_x = max(0, x + jitter_x)
        final_y = max(0, y + jitter_y)
        
        # Simulate finger "roll" (the end pixel of a tap is rarely the exact start pixel)
        roll_x = final_x + int(random.gauss(0, 1.5))
        roll_y = final_y + int(random.gauss(0, 1.5))
        
        if short_press:
            # Force a hyper-fast 20-50ms press for sensitive UI elements
            duration_ms = random.randint(20, 50)
        else:
            # Simulate tap duration (how long the finger depresses the screen). Humans average 40-150ms.
            duration_ms = int(random.gauss(80, 20))
            duration_ms = max(30, min(200, duration_ms)) # Bound to realistic limits
        
        # Use swipe to broadcast complex touch telemetry (duration + micro-movement) instead of a 0ms single-pixel tap
        self._adb_command("shell", "input", "swipe", str(final_x), str(final_y), str(roll_x), str(roll_y), str(duration_ms))
        
        if custom_delay is not None:
            time.sleep(custom_delay)
        else:
            # Human-like delay after tapping using a Log-Normal distribution (median ~0.35s, with rare long tails)
            extra_delay = random.lognormvariate(-1.0, 0.8)
            time.sleep(0.1 + extra_delay)

    def simple_tap(self, x, y, custom_delay=0.2):
        """Perform a direct, raw adb tap without any swipe/telemetry simulation."""
        self._adb_command("shell", "input", "tap", str(int(x)), str(int(y)))
        if custom_delay is not None:
            time.sleep(custom_delay)

    def back(self, back_btn_loc=None):
        """Press the Android Back button to close menus/popups using a random method."""
        choice = random.random()
        
        # 1. Physical UI Button
        if back_btn_loc and choice < 0.33:
            self.tap(back_btn_loc[0], back_btn_loc[1])
            return
            
        # 2. Gesture Swipe
        if choice < 0.66:
            screen_w, screen_h = 1080, 2460
            y = random.randint(int(screen_h * 0.4), int(screen_h * 0.8))
            duration = random.randint(150, 300)
            
            if random.choice([True, False]):
                # Left edge to 35-40% width
                x_start = random.randint(0, 10)
                x_end = int(screen_w * random.uniform(0.35, 0.45))
            else:
                # Right edge to 60-65% width
                x_start = random.randint(screen_w - 10, screen_w)
                x_end = int(screen_w * random.uniform(0.55, 0.65))
                
            # Add slight vertical finger drift
            y_end = y + random.randint(-20, 20)
            self._adb_command("shell", "input", "swipe", str(x_start), str(y), str(x_end), str(y_end), str(duration))
            time.sleep(random.uniform(0.8, 1.5))
            return
            
        # 3. Hardware Key
        self._adb_command("shell", "input", "keyevent", "4")
        time.sleep(random.uniform(0.8, 1.5))

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
