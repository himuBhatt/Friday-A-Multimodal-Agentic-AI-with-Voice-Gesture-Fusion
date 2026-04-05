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

# Prevent PyAutoGUI from silently crashing if the cursor hits the edge of the screen
pyautogui.FAILSAFE = False

# --- SHARED STATE ---
class SharedState:
    is_speaking = False
    is_listening = False
    keyboard_active = False
    last_action_time = 0

# --- ENUMERATIONS ---
class Gest(IntEnum):
    FIST, PALM, INDEX, MID, V_GEST, THUMB = 0, 31, 8, 4, 12, 16
    PINCH_MAJOR, PINCH_MINOR = 35, 36
    NONE = -1

class HLabel(IntEnum):
    MINOR, MAJOR = 0, 1

# --- HUD INTERFACE ---
class FridayHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.6)
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
        start_x, start_y, size = self.screen_w // 4, self.screen_h // 1.8, 70
        for i, row in enumerate(self.keys):
            for j, key in enumerate(row):
                x, y = start_x + j*(size+10), start_y + i*(size+10)
                rect = self.canvas.create_rectangle(x, y, x+size, y+size, outline="#00FFFF", width=2)
                self.canvas.create_text(x+(size//2), y+(size//2), text=key, fill="#00FFFF", font=("Segoe UI", 18, "bold"))
                self.buttons.append({'coords': (x, y, x+size, y+size), 'rect': rect, 'key': key})

    def update_hud(self, cursor_x, cursor_y):
        if not SharedState.keyboard_active:
            self.root.withdraw()
            return
        self.root.deiconify()
        glow = "#FF00FF" if SharedState.is_listening else "#00FFFF"
        for b in self.buttons:
            x1, y1, x2, y2 = b['coords']
            fill = "#004444" if x1 < cursor_x < x2 and y1 < cursor_y < y2 else ""
            self.canvas.itemconfig(b['rect'], fill=fill, outline=glow)
        self.root.update()

# --- GESTURE INTERPRETATION ---
class HandRecog:
    def __init__(self, hand_label):
        self.finger = 0
        self.ori_gesture = Gest.NONE
        self.prev_gesture = Gest.NONE
        self.frame_count = 0
        self.hand_result = None
        self.hand_label = hand_label
    
    def update_hand_result(self, hand_result): 
        self.hand_result = hand_result

    def get_dist(self, p1, p2):
        if not self.hand_result: return 1.0
        return math.hypot(self.hand_result.landmark[p1].x - self.hand_result.landmark[p2].x,
                          self.hand_result.landmark[p1].y - self.hand_result.landmark[p2].y)

    def set_finger_state(self):
        if not self.hand_result: 
            self.finger = 0
            return
        
        # Stability: Measure Tip vs PIP Knuckle relative to the Wrist (Landmark 0)
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        self.finger = 0
        
        for i in range(4):
            tip_dist = self.get_dist(tips[i], 0)
            pip_dist = self.get_dist(pips[i], 0)
            is_open = 1 if tip_dist > pip_dist else 0
            self.finger = (self.finger << 1) | is_open
    
    def get_gesture(self):
        if not self.hand_result: return Gest.NONE
        
        idx_thumb_dist = self.get_dist(8, 4)
        f_up = bin(self.finger).count('1')
        
        # Binary-based classification
        if f_up >= 3: current = Gest.PALM
        elif f_up == 0: current = Gest.FIST
        elif self.finger == 12: current = Gest.V_GEST
        elif self.finger == 8: current = Gest.INDEX
        else: current = Gest.NONE

        # Pinch overrides
        if idx_thumb_dist < 0.05: 
            current = Gest.PINCH_MINOR if self.hand_label == HLabel.MINOR else Gest.PINCH_MAJOR

        if current == self.prev_gesture: self.frame_count += 1
        else: self.frame_count = 0
            
        self.prev_gesture = current
        if self.frame_count > 1: self.ori_gesture = current
            
        return self.ori_gesture

# --- SYSTEM CONTROLLER ---
class Controller:
    alpha = 0.35 
    smooth_x, smooth_y = 0, 0
    frameR, cam_w, cam_h = 40, 320, 240
    grab_flag = False
    vol_start_y = None
    vol_start_level = None

    @staticmethod
    def get_smooth_pos(res):
        sx, sy = pyautogui.size()
        # Anchor to Landmark 5 (Index Knuckle) for drift prevention
        tx = np.interp(res.landmark[5].x * Controller.cam_w, (Controller.frameR, Controller.cam_w-Controller.frameR), (0, sx))
        ty = np.interp(res.landmark[5].y * Controller.cam_h, (Controller.frameR, Controller.cam_h-Controller.frameR), (0, sy))
        
        Controller.smooth_x = (Controller.alpha * tx) + ((1 - Controller.alpha) * Controller.smooth_x)
        Controller.smooth_y = (Controller.alpha * ty) + ((1 - Controller.alpha) * Controller.smooth_y)
        return Controller.smooth_x, Controller.smooth_y

    @staticmethod
    def handle_controls(maj_g, min_g, maj_res, min_res, hud):
        if SharedState.is_speaking: return

        # HUD Toggle (Both hands PALM)
        if maj_g == Gest.PALM and min_g == Gest.PALM:
            if time() - SharedState.last_action_time > 1.5:
                SharedState.keyboard_active = not SharedState.keyboard_active
                SharedState.last_action_time = time()

        if not maj_res: return
        x, y = Controller.get_smooth_pos(maj_res)

        # Precise pinch distances for clicking
        idx_thumb_dist = math.hypot(maj_res.landmark[8].x - maj_res.landmark[4].x, 
                                    maj_res.landmark[8].y - maj_res.landmark[4].y)
        mid_thumb_dist = math.hypot(maj_res.landmark[12].x - maj_res.landmark[4].x, 
                                    maj_res.landmark[12].y - maj_res.landmark[4].y)

        if SharedState.keyboard_active:
            if min_g == Gest.PALM:
                pyautogui.moveTo(x, y, _pause=False)
                if idx_thumb_dist < 0.05 and time() - SharedState.last_action_time > 0.8:
                    for b in hud.buttons:
                        x1, y1, x2, y2 = b['coords']
                        if x1 < x < x2 and y1 < y < y2:
                            if b['key'] == "X": SharedState.keyboard_active = False
                            elif b['key'] == "<": pyautogui.press("backspace")
                            elif b['key'] == "_": pyautogui.press("enter")
                            elif b['key'] == " ": pyautogui.press("space")
                            else: pyautogui.write(b['key'].lower())
                            SharedState.last_action_time = time()
        else:
            # Main Hand (MAJOR) controls cursor
            if maj_g != Gest.FIST:
                pyautogui.moveTo(x, y, _pause=False)
                if Controller.grab_flag: 
                    pyautogui.mouseUp()
                    Controller.grab_flag = False
            
            # Drag/Grab Logic
            elif maj_g == Gest.FIST:
                if not Controller.grab_flag: 
                    pyautogui.mouseDown()
                    Controller.grab_flag = True
                pyautogui.moveTo(x, y, _pause=False)
            
            # Clicking Logic (Priority over Pinch Volume)
            if idx_thumb_dist < 0.05 and time() - SharedState.last_action_time > 0.4 and maj_g != Gest.PINCH_MAJOR:
                pyautogui.click()
                SharedState.last_action_time = time()
            elif mid_thumb_dist < 0.05 and time() - SharedState.last_action_time > 0.4:
                pyautogui.rightClick()
                SharedState.last_action_time = time()

            # Volume Control: Pinch and Move hand up/down
            if maj_g == Gest.PINCH_MAJOR:
                try:
                    vol_interface = cast(AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
                    if Controller.vol_start_y is None:
                        Controller.vol_start_y = maj_res.landmark[5].y
                        Controller.vol_start_level = vol_interface.GetMasterVolumeLevelScalar()
                    else:
                        dy = Controller.vol_start_y - maj_res.landmark[5].y
                        new_vol = max(0.0, min(1.0, Controller.vol_start_level + (dy * 2.5)))
                        vol_interface.SetMasterVolumeLevelScalar(new_vol, None)
                except Exception: pass
            else: 
                Controller.vol_start_y = None
                Controller.vol_start_level = None

# --- MAIN VISION EXECUTION ---
class GestureController:
    def __init__(self):
        import mediapipe as mp
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.75, min_tracking_confidence=0.75)
        self.mp_draw = mp.solutions.drawing_utils
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.hud = FridayHUD()
        self.h_maj = HandRecog(HLabel.MAJOR)
        self.h_min = HandRecog(HLabel.MINOR)

    def process_frame(self):
        success, img = self.cap.read()
        if not success: return

        img = cv2.flip(img, 1)
        results = self.hands.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        
        self.h_maj.update_hand_result(None)
        self.h_min.update_hand_result(None)

        if results.multi_hand_landmarks:
            for idx, hand_info in enumerate(results.multi_handedness):
                label = hand_info.classification[0].label
                # Right physical hand = Major (Cursor)
                if label == 'Right':  
                    self.h_maj.update_hand_result(results.multi_hand_landmarks[idx])
                else: 
                    self.h_min.update_hand_result(results.multi_hand_landmarks[idx])
            
            self.h_maj.set_finger_state()
            self.h_min.set_finger_state()
            Controller.handle_controls(self.h_maj.get_gesture(), self.h_min.get_gesture(), 
                                     self.h_maj.hand_result, self.h_min.hand_result, self.hud)

        # HUD Update
        mx, my = pyautogui.position()
        self.hud.update_hud(mx, my)
        
        if results.multi_hand_landmarks:
            for hand_lms in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(img, hand_lms, self.mp_hands.HAND_CONNECTIONS)

        # On-Screen Debugging
        maj_txt = f"Right (Major): {self.h_maj.get_gesture().name}" if self.h_maj.hand_result else "Right: None"
        min_txt = f"Left (Minor): {self.h_min.get_gesture().name}" if self.h_min.hand_result else "Left: None"
        cv2.putText(img, f"{maj_txt} | {min_txt}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.imshow('Friday Vision Feed', img)
        if cv2.waitKey(1) & 0xFF == 27: 
            self.shutdown()
            return

        self.hud.root.after(5, self.process_frame)

    def shutdown(self):
        self.cap.release()
        cv2.destroyAllWindows()
        self.hud.root.destroy()

if __name__ == "__main__":
    gc = GestureController()
    gc.hud.root.after(10, gc.process_frame)
    gc.hud.root.mainloop()