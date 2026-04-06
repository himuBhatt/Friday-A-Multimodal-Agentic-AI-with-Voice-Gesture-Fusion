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

# --- SHARED STATE: The Bridge between Vision and Voice ---
class SharedState:
    """Synchronizes background voice tasks with foreground vision tasks."""
    is_speaking = False
    is_listening = False
    keyboard_active = False
    last_action_time = 0

# --- ENUMERATIONS ---
class Gest(IntEnum):
    FIST, PINKY, RING, MID, LAST3, INDEX, FIRST2, LAST4, THUMB, PALM = 0, 1, 2, 4, 7, 8, 12, 15, 16, 31
    V_GEST, TWO_FINGER_CLOSED, PINCH_MAJOR, PINCH_MINOR = 33, 34, 35, 36
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
        # Reactive UI: Changes outline when Friday is listening
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

    def get_dist(self, p):
        if not self.hand_result: return 0
        return math.sqrt((self.hand_result.landmark[p[0]].x - self.hand_result.landmark[p[1]].x)**2 +
                         (self.hand_result.landmark[p[0]].y - self.hand_result.landmark[p[1]].y)**2)

    def set_finger_state(self):
        if not self.hand_result:
            self.finger = 0
            return
        points = [[8,5,0],[12,9,0],[16,13,0],[20,17,0]]
        self.finger = 0
        for pt in points:
            d1 = self.get_dist(pt[:2])
            d2 = self.get_dist(pt[1:])
            self.finger = (self.finger << 1) | (1 if (d1/(d2 if d2!=0 else 0.01)) > 0.6 else 0)

    def get_gesture(self):
        if not self.hand_result: return Gest.NONE
        f_up = bin(self.finger).count('1')
        if f_up >= 4: current = Gest.PALM
        elif self.finger == 12: current = Gest.V_GEST
        elif self.finger == 8: current = Gest.INDEX
        elif self.finger == 4: current = Gest.MID
        elif self.finger == 0: current = Gest.FIST
        elif self.finger == 16: current = Gest.THUMB
        else: current = self.finger

        if self.finger in [Gest.LAST3, Gest.LAST4] and self.get_dist([8,4]) < 0.04:
            current = Gest.PINCH_MINOR if self.hand_label == HLabel.MINOR else Gest.PINCH_MAJOR

        if current == self.prev_gesture: self.frame_count += 1
        else: self.frame_count = 0
        self.prev_gesture = current
        if self.frame_count > 4: self.ori_gesture = current
        return self.ori_gesture

# --- SYSTEM CONTROLLER ---
class Controller:
    # EMA Smoothing Factor (0.1 to 1.0)
    alpha = 0.65
    smooth_x, smooth_y = 0, 0
    frameR, cam_w, cam_h = 40, 320, 240
    grab_flag = False
    pinch_start_val = None

    @staticmethod
    def get_smooth_pos(res):
        sx, sy = pyautogui.size()
        tx = np.interp(res.landmark[5].x * Controller.cam_w, (Controller.frameR, Controller.cam_w-Controller.frameR), (0, sx))
        ty = np.interp(res.landmark[5].y * Controller.cam_h, (Controller.frameR, Controller.cam_h-Controller.frameR), (0, sy))

        # Exponential Moving Average (EMA) Filter
        Controller.smooth_x = (Controller.alpha * tx) + ((1 - Controller.alpha) * Controller.smooth_x)
        Controller.smooth_y = (Controller.alpha * ty) + ((1 - Controller.alpha) * Controller.smooth_y)
        return Controller.smooth_x, Controller.smooth_y

    @staticmethod
    def handle_controls(maj_g, min_g, maj_res, min_res, hud):
        # Prevention: Don't click/move if Friday is talking
        if SharedState.is_speaking: return

        # Toggle HUD
        if maj_g == Gest.PALM and min_g == Gest.PALM:
            if time() - SharedState.last_action_time > 1.5:
                SharedState.keyboard_active = not SharedState.keyboard_active
                SharedState.last_action_time = time()

        if not maj_res: return
        x, y = Controller.get_smooth_pos(maj_res)

        if SharedState.keyboard_active:
            if min_g == Gest.PALM and maj_g == Gest.INDEX:
                pyautogui.moveTo(x, y, _pause=False)
                for b in hud.buttons:
                    x1, y1, x2, y2 = b['coords']
                    if x1 < x < x2 and y1 < y < y2:
                        if time() - SharedState.last_action_time > 1.2:
                            key = b['key']
                            if key == "X": SharedState.keyboard_active = False
                            elif key == "<": pyautogui.press("backspace")
                            elif key == "_": pyautogui.press("enter")
                            elif key == " ": pyautogui.press("space")
                            else: pyautogui.write(key.lower())
                            SharedState.last_action_time = time()
        else:
            if maj_g == Gest.V_GEST: pyautogui.moveTo(x, y, _pause=False)
            elif maj_g == Gest.FIST:
                if not Controller.grab_flag: pyautogui.mouseDown(); Controller.grab_flag = True
                pyautogui.moveTo(x, y, _pause=False)
            elif Controller.grab_flag: pyautogui.mouseUp(); Controller.grab_flag = False

            if maj_g == Gest.MID and time() - SharedState.last_action_time > 0.3:
                pyautogui.click(); SharedState.last_action_time = time()
            elif maj_g == Gest.INDEX and time() - SharedState.last_action_time > 0.3:
                pyautogui.rightClick(); SharedState.last_action_time = time()

            # Hardware Control (Pinch)
            if maj_g == Gest.PINCH_MAJOR:
                dy = maj_res.landmark[8].y - maj_res.landmark[4].y
                if Controller.pinch_start_val is None: Controller.pinch_start_val = dy
                delta = (Controller.pinch_start_val - dy) * 100
                if abs(delta) > 3:
                    vol = cast(AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
                    vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, vol.GetMasterVolumeLevelScalar() + delta/500)), None)
            else: Controller.pinch_start_val = None

# --- MAIN VISION EXECUTION ---
class GestureController:
    def __init__(self):
        try:
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7, min_tracking_confidence=0.7)
            self.mp_draw = mp.solutions.drawing_utils
        except Exception as e:
            print(f"❌ Mediapipe Load Error: {e}")

        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.hud = FridayHUD()

    def start(self):
        h_maj, h_min = HandRecog(HLabel.MAJOR), HandRecog(HLabel.MINOR)
        while self.cap.isOpened():
            success, img = self.cap.read()
            if not success: break
            img = cv2.flip(img, 1)
            results = self.hands.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

            h_maj.update_hand_result(None)
            h_min.update_hand_result(None)

            if results.multi_hand_landmarks:
                for idx, hand_info in enumerate(results.multi_handedness):
                    label = hand_info.classification[0].label
                    if label == 'Right': h_maj.update_hand_result(results.multi_hand_landmarks[idx])
                    else: h_min.update_hand_result(results.multi_hand_landmarks[idx])

                h_maj.set_finger_state()
                h_min.set_finger_state()
                Controller.handle_controls(h_maj.get_gesture(), h_min.get_gesture(),
                                         h_maj.hand_result, h_min.hand_result, self.hud)

            # Update Displays
            mx, my = pyautogui.position()
            #self.hud.update_hud(mx, my)

            if results.multi_hand_landmarks:
                for hand_lms in results.multi_hand_landmarks:
                    self.mp_draw.draw_landmarks(img, hand_lms, self.mp_hands.HAND_CONNECTIONS)

            cv2.imshow('Friday Vision Feed', img)
            if cv2.waitKey(1) & 0xFF == 27: break

        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    GestureController().start()
