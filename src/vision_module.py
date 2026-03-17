import sys
import os
import cv2
import pyautogui
import math
import numpy as np
from enum import IntEnum
from time import time
import tkinter as tk
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import screen_brightness_control as sbcontrol

# --- FORCE PATH INJECTION FOR MEDIAPIPE ---
venv_site_packages = os.path.join(os.getcwd(), 'venv', 'Lib', 'site-packages')
mp_path = os.path.join(venv_site_packages, 'mediapipe', 'python')
if mp_path not in sys.path:
    sys.path.append(mp_path)

try:
    import mediapipe as mp
    from mediapipe.python.solutions import hands as mp_hands
    from mediapipe.python.solutions import drawing_utils as mp_drawing
    from google.protobuf.json_format import MessageToDict
    print("✅ Friday Vision: All Systems Integrated")
except ImportError as e:
    print(f"❌ Critical Error: {e}")
    sys.exit(1)

pyautogui.FAILSAFE = True

class Gest(IntEnum):
    FIST, PINKY, RING, MID, LAST3, INDEX, FIRST2, LAST4, THUMB, PALM = 0, 1, 2, 4, 7, 8, 12, 15, 16, 31
    V_GEST, TWO_FINGER_CLOSED, PINCH_MAJOR, PINCH_MINOR = 33, 34, 35, 36
    NONE = -1

class HLabel(IntEnum):
    MINOR, MAJOR = 0, 1

class FridayHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.7)
        self.root.config(bg='black')
        self.root.wm_attributes("-transparentcolor", "black")
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.keys = [["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
                     ["A", "S", "D", "F", "G", "H", "J", "K", "L", "<"],
                     ["Z", "X", "C", "V", "B", "N", "M", " ", "_", "X"]]
        self.buttons = []
        self._setup_layout()
        self.root.withdraw()

    def _setup_layout(self):
        start_x, start_y, size = self.screen_w // 4, self.screen_h // 1.8, 75
        for i, row in enumerate(self.keys):
            for j, key in enumerate(row):
                x, y = start_x + j*(size+10), start_y + i*(size+10)
                rect = self.canvas.create_rectangle(x, y, x+size, y+size, outline="#00FFFF", width=2)
                self.canvas.create_text(x+(size//2), y+(size//2), text=key, fill="#00FFFF", font=("Segoe UI", 20, "bold"))
                self.buttons.append({'coords': (x, y, x+size, y+size), 'rect': rect, 'key': key})

    def update_hud(self, cursor_x, cursor_y, active):
        if not active: self.root.withdraw(); return
        self.root.deiconify()
        for b in self.buttons:
            x1, y1, x2, y2 = b['coords']
            fill = "#005555" if x1 < cursor_x < x2 and y1 < cursor_y < y2 else ""
            self.canvas.itemconfig(b['rect'], fill=fill)
        self.root.update()

class HandRecog:
    def __init__(self, hand_label):
        self.finger = 0
        self.ori_gesture = Gest.NONE
        self.prev_gesture = Gest.NONE
        self.frame_count = 0
        self.hand_result = None
        self.hand_label = hand_label
    
    def update_hand_result(self, hand_result): self.hand_result = hand_result

    def get_dist(self, p):
        if not self.hand_result: return 0
        return math.sqrt((self.hand_result.landmark[p[0]].x - self.hand_result.landmark[p[1]].x)**2 + 
                         (self.hand_result.landmark[p[0]].y - self.hand_result.landmark[p[1]].y)**2)

    def set_finger_state(self):
        if not self.hand_result: self.finger = 0; return
        points = [[8,5,0],[12,9,0],[16,13,0],[20,17,0]]
        self.finger = 0
        for pt in points:
            d1 = self.get_dist(pt[:2])
            d2 = self.get_dist(pt[1:])
            self.finger = (self.finger << 1) | (1 if (d1/(d2 if d2!=0 else 0.01)) > 0.6 else 0)
    
    def get_gesture(self):
        if not self.hand_result: return Gest.NONE
        f_up = bin(self.finger).count('1')
        res = self.hand_result.landmark
        
        # Gestures Detection
        if f_up >= 4: current = Gest.PALM
        elif self.finger == 12: current = Gest.V_GEST
        elif self.finger == 8: current = Gest.INDEX
        elif self.finger == 4: current = Gest.MID
        elif self.finger == 0: current = Gest.FIST
        elif self.finger == 16: current = Gest.THUMB
        else: current = self.finger

        # Pinch Logic
        if self.finger in [Gest.LAST3, Gest.LAST4] and self.get_dist([8,4]) < 0.05:
            current = Gest.PINCH_MINOR if self.hand_label == HLabel.MINOR else Gest.PINCH_MAJOR

        if current == self.prev_gesture: self.frame_count += 1
        else: self.frame_count = 0
        self.prev_gesture = current
        if self.frame_count > 4: self.ori_gesture = current
        return self.ori_gesture

class Controller:
    smoothening = 5
    plocX, plocY = 0, 0
    frameR, cam_w, cam_h = 50, 320, 240
    keyboard_active, grabflag = False, False
    last_action_time, pinch_start_coords = 0, None

    @staticmethod
    def get_position(res):
        sx, sy = pyautogui.size()
        x1, y1 = res.landmark[8].x * Controller.cam_w, res.landmark[8].y * Controller.cam_h
        x2 = np.interp(x1, (Controller.frameR, Controller.cam_w - Controller.frameR), (0, sx))
        y2 = np.interp(y1, (Controller.frameR, Controller.cam_h - Controller.frameR), (0, sy))
        Controller.plocX += (x2 - Controller.plocX) / Controller.smoothening
        Controller.plocY += (y2 - Controller.plocY) / Controller.smoothening
        return Controller.plocX, Controller.plocY

    @staticmethod
    def handle_controls(maj_g, min_g, maj_res, min_res, hud):
        # 1. Toggle HUD (Double Palm - 2s)
        if maj_res and min_res and maj_g == Gest.PALM and min_g == Gest.PALM:
            if time() - Controller.last_action_time > 2.0:
                Controller.keyboard_active = not Controller.keyboard_active
                Controller.last_action_time = time()

        if not maj_res: return
        x, y = Controller.get_position(maj_res)

        # 2. Typing Mode
        if Controller.keyboard_active and min_g == Gest.PALM and maj_g == Gest.INDEX:
            pyautogui.moveTo(x, y, _pause=False)
            mx, my = pyautogui.position()
            for b in hud.buttons:
                x1, y1, x2, y2 = b['coords']
                if x1 < mx < x2 and y1 < my < y2:
                    if time() - Controller.last_action_time > 2.0:
                        key = b['key']
                        if key == "X": Controller.keyboard_active = False
                        elif key == "<": pyautogui.press("backspace")
                        elif key == "_": pyautogui.press("enter")
                        elif key == " ": pyautogui.press("space")
                        else: pyautogui.press(key.lower())
                        Controller.last_action_time = time()
        
        # 3. Command Mode
        elif not Controller.keyboard_active:
            if maj_g == Gest.V_GEST: pyautogui.moveTo(x, y, _pause=False)
            elif maj_g == Gest.FIST:
                if not Controller.grabflag: pyautogui.mouseDown(); Controller.grabflag = True
                pyautogui.moveTo(x, y, _pause=False)
            elif Controller.grabflag: pyautogui.mouseUp(); Controller.grabflag = False
            
            elif maj_g == Gest.MID: 
                if time()-Controller.last_action_time > 0.3: pyautogui.click(); Controller.last_action_time = time()
            elif maj_g == Gest.INDEX:
                if time()-Controller.last_action_time > 0.3: pyautogui.click(button='right'); Controller.last_action_time = time()
            
            # Pinch Controls
            if maj_g == Gest.PINCH_MAJOR or min_g == Gest.PINCH_MINOR:
                res = maj_res if maj_g == Gest.PINCH_MAJOR else min_res
                if not Controller.pinch_start_coords: Controller.pinch_start_coords = (res.landmark[8].x, res.landmark[8].y)
                dx = (res.landmark[8].x - Controller.pinch_start_coords[0]) * 10
                dy = (Controller.pinch_start_coords[1] - res.landmark[8].y) * 10
                
                if maj_g == Gest.PINCH_MAJOR: # Vol/Bright
                    if abs(dx) > abs(dy): # Horizontal: Brightness
                        sbcontrol.set_brightness(max(0, min(100, sbcontrol.get_brightness()[0] + int(dx*5))))
                    else: # Vertical: Volume
                        vol = cast(AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
                        vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, vol.GetMasterVolumeLevelScalar() + dy/10)), None)
                else: # Scroll
                    pyautogui.scroll(int(dy*50))
            else: Controller.pinch_start_coords = None

class GestureController:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        self.cap.set(3, 320); self.cap.set(4, 240)
        self.hud = FridayHUD()
        self.dom_hand = True

    def start(self):
        h_maj, h_min = HandRecog(HLabel.MAJOR), HandRecog(HLabel.MINOR)
        with mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.8) as hands:
            while self.cap.isOpened():
                success, img = self.cap.read()
                if not success: continue
                img = cv2.flip(img, 1)
                res = hands.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                h_maj.update_hand_result(None); h_min.update_hand_result(None)

                if res.multi_hand_landmarks:
                    for idx, hand in enumerate(res.multi_handedness):
                        label = MessageToDict(hand)['classification'][0]['label']
                        if label == 'Right': h_maj.update_hand_result(res.multi_hand_landmarks[idx])
                        else: h_min.update_hand_result(res.multi_hand_landmarks[idx])
                    h_maj.set_finger_state(); h_min.set_finger_state()
                    Controller.handle_controls(h_maj.get_gesture(), h_min.get_gesture(), h_maj.hand_result, h_min.hand_result, self.hud)

                mx, my = pyautogui.position()
                self.hud.update_hud(mx, my, Controller.keyboard_active)
                cv2.imshow('Friday Vision Feed', img)
                if cv2.waitKey(5) & 0xFF == 27: break
        self.cap.release(); cv2.destroyAllWindows()

if __name__ == "__main__":
    GestureController().start()