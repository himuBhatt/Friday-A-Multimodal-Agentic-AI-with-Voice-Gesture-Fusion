import sys
import os
import cv2
import pyautogui
import math
import numpy as np
from enum import IntEnum
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
    print("✅ Friday Vision: Mediapipe linked successfully!")
except ImportError as e:
    print(f"❌ Critical Error: {e}")
    sys.exit(1)

pyautogui.FAILSAFE = True

class Gest(IntEnum):
    FIST, PINKY, RING, MID, LAST3, INDEX, FIRST2, LAST4, THUMB, PALM = 0, 1, 2, 4, 7, 8, 12, 15, 16, 31
    V_GEST, TWO_FINGER_CLOSED, PINCH_MAJOR, PINCH_MINOR = 33, 34, 35, 36

class HLabel(IntEnum):
    MINOR, MAJOR = 0, 1

class HandRecog:
    def __init__(self, hand_label):
        self.finger = 0
        self.ori_gesture = Gest.PALM
        self.prev_gesture = Gest.PALM
        self.frame_count = 0
        self.hand_result = None
        self.hand_label = hand_label
    
    def update_hand_result(self, hand_result):
        self.hand_result = hand_result

    def get_signed_dist(self, point):
        if not self.hand_result: return 0
        sign = 1 if self.hand_result.landmark[point[0]].y < self.hand_result.landmark[point[1]].y else -1
        dist = math.sqrt((self.hand_result.landmark[point[0]].x - self.hand_result.landmark[point[1]].x)**2 + 
                         (self.hand_result.landmark[point[0]].y - self.hand_result.landmark[point[1]].y)**2)
        return dist * sign
    
    def get_dist(self, point):
        if not self.hand_result: return 0
        return math.sqrt((self.hand_result.landmark[point[0]].x - self.hand_result.landmark[point[1]].x)**2 + 
                         (self.hand_result.landmark[point[0]].y - self.hand_result.landmark[point[1]].y)**2)
    
    def get_dz(self,point):
        if not self.hand_result: return 0
        return abs(self.hand_result.landmark[point[0]].z - self.hand_result.landmark[point[1]].z)
    
    def set_finger_state(self):
        if not self.hand_result: return
        points = [[8,5,0],[12,9,0],[16,13,0],[20,17,0]]
        self.finger = 0
        for point in points:
            dist, dist2 = self.get_signed_dist(point[:2]), self.get_signed_dist(point[1:])
            try:
                ratio = round(dist/(dist2 if dist2 != 0 else 0.01), 1)
            except: ratio = 0
            self.finger = (self.finger << 1) | (1 if ratio > 0.5 else 0)
    
    def get_gesture(self):
        if not self.hand_result: return Gest.PALM
        current_gesture = Gest.PALM
        if self.finger in [Gest.LAST3,Gest.LAST4] and self.get_dist([8,4]) < 0.05:
            current_gesture = Gest.PINCH_MINOR if self.hand_label == HLabel.MINOR else Gest.PINCH_MAJOR
        elif Gest.FIRST2 == self.finger :
            point = [[8,12],[5,9]]
            dist1 = self.get_dist(point[0])
            dist2 = self.get_dist(point[1])
            ratio = dist1/(dist2 if dist2 != 0 else 0.01)
            if ratio > 1.7: current_gesture = Gest.V_GEST
            else: current_gesture = Gest.TWO_FINGER_CLOSED if self.get_dz([8,12]) < 0.1 else Gest.MID
        else: current_gesture = self.finger
        
        if current_gesture == self.prev_gesture: self.frame_count += 1
        else: self.frame_count = 0
        self.prev_gesture = current_gesture
        if self.frame_count > 4 : self.ori_gesture = current_gesture
        return self.ori_gesture

class Controller:
    smoothening = 7
    plocX, plocY = 0, 0
    clocX, clocY = 0, 0
    frameR = 60 # Reduced frame for 320x240 resolution
    cam_w, cam_h = 320, 240 # Optimized for 8GB RAM

    flag, grabflag, pinchmajorflag, pinchminorflag = False, False, False, False
    pinchstartxcoord, pinchstartycoord, pinchdirectionflag = None, None, None
    prevpinchlv, pinchlv, framecount = 0, 0, 0
    
    @staticmethod
    def get_position(hand_result):
        point = 8 
        sx, sy = pyautogui.size()
        x1 = hand_result.landmark[point].x * Controller.cam_w
        y1 = hand_result.landmark[point].y * Controller.cam_h
        
        x2 = np.interp(x1, (Controller.frameR, Controller.cam_w - Controller.frameR), (0, sx))
        y2 = np.interp(y1, (Controller.frameR, Controller.cam_h - Controller.frameR), (0, sy))
        
        Controller.clocX = Controller.plocX + (x2 - Controller.plocX) / Controller.smoothening
        Controller.clocY = Controller.plocY + (y2 - Controller.plocY) / Controller.smoothening
        
        Controller.plocX, Controller.plocY = Controller.clocX, Controller.clocY
        return Controller.clocX, Controller.clocY

    @staticmethod
    def changesystembrightness():
        try:
            cur = sbcontrol.get_brightness(display=0)
            if isinstance(cur, list): cur = cur[0]
            sbcontrol.set_brightness(max(0, min(100, int(cur + Controller.pinchlv * 2))))
        except: pass

    @staticmethod
    def changesystemvolume():
        try:
            devices = AudioUtilities.GetSpeakers()
            volume = cast(devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
            cur = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, cur + Controller.pinchlv/50.0)), None)
        except: pass

    @staticmethod
    def scrollVertical():
        pyautogui.scroll(150 if Controller.pinchlv > 0 else -150)

    @staticmethod
    def scrollHorizontal():
        pyautogui.hotkey('shift')
        pyautogui.scroll(-150 if Controller.pinchlv > 0 else 150)

    @staticmethod
    def handle_controls(gesture, hand_result):      
        x, y = (None, None) if gesture == Gest.PALM else Controller.get_position(hand_result)
        
        if gesture != Gest.FIST and Controller.grabflag:
            Controller.grabflag = False
            pyautogui.mouseUp(button="left")

        if gesture == Gest.V_GEST:
            Controller.flag = True
            pyautogui.moveTo(x, y, _pause=False)
        elif gesture == Gest.FIST:
            if not Controller.grabflag:
                Controller.grabflag = True
                pyautogui.mouseDown(button="left")
            pyautogui.moveTo(x, y, _pause=False)
        elif gesture == Gest.MID and Controller.flag:
            pyautogui.click(); Controller.flag = False
        elif gesture == Gest.INDEX and Controller.flag:
            pyautogui.click(button='right'); Controller.flag = False
        elif gesture == Gest.TWO_FINGER_CLOSED and Controller.flag:
            pyautogui.doubleClick(); Controller.flag = False
        elif gesture in [Gest.PINCH_MINOR, Gest.PINCH_MAJOR]:
            flag_attr = 'pinchminorflag' if gesture == Gest.PINCH_MINOR else 'pinchmajorflag'
            if not getattr(Controller, flag_attr):
                Controller.pinchstartxcoord, Controller.pinchstartycoord = hand_result.landmark[8].x, hand_result.landmark[8].y
                Controller.pinchlv, Controller.prevpinchlv, Controller.framecount = 0, 0, 0
                setattr(Controller, flag_attr, True)
            
            lvx = round((hand_result.landmark[8].x - Controller.pinchstartxcoord)*10,1)
            lvy = round((Controller.pinchstartycoord - hand_result.landmark[8].y)*10,1)
            Controller.pinchdirectionflag = abs(lvx) > abs(lvy)
            target_lv = lvx if Controller.pinchdirectionflag else lvy
            
            if abs(Controller.prevpinchlv - target_lv) < 0.3: Controller.framecount += 1
            else: Controller.prevpinchlv, Controller.framecount = target_lv, 0
            
            if Controller.framecount == 5:
                Controller.pinchlv = Controller.prevpinchlv
                if gesture == Gest.PINCH_MINOR:
                    Controller.scrollHorizontal() if Controller.pinchdirectionflag else Controller.scrollVertical()
                else:
                    Controller.changesystembrightness() if Controller.pinchdirectionflag else Controller.changesystemvolume()

class GestureController:
    gc_mode = 0
    cap = None
    dom_hand = True # Fixed the missing attribute

    def __init__(self):
        GestureController.gc_mode = 1
        GestureController.cap = cv2.VideoCapture(0)
        GestureController.cap.set(3, Controller.cam_w)
        GestureController.cap.set(4, Controller.cam_h)

    def start(self):
        handmajor, handminor = HandRecog(HLabel.MAJOR), HandRecog(HLabel.MINOR)
        with mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7, min_tracking_confidence=0.7) as hands:
            while GestureController.cap.isOpened() and GestureController.gc_mode:
                success, image = GestureController.cap.read()
                if not success: continue
                
                image = cv2.flip(image, 1)
                results = hands.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

                if results.multi_hand_landmarks:
                    right, left = None, None
                    for idx, hand_handedness in enumerate(results.multi_handedness):
                        label = MessageToDict(hand_handedness)['classification'][0]['label']
                        if label == 'Right': right = results.multi_hand_landmarks[idx]
                        else: left = results.multi_hand_landmarks[idx]
                    
                    handmajor.update_hand_result(right if self.dom_hand else left)
                    handminor.update_hand_result(left if self.dom_hand else right)

                    handmajor.set_finger_state(); handminor.set_finger_state()
                    
                    gest = handminor.get_gesture()
                    if gest == Gest.PINCH_MINOR: Controller.handle_controls(gest, handminor.hand_result)
                    else: Controller.handle_controls(handmajor.get_gesture(), handmajor.hand_result)

                    cv2.rectangle(image, (Controller.frameR, Controller.frameR), 
                                 (Controller.cam_w - Controller.frameR, Controller.cam_h - Controller.frameR), 
                                 (255, 0, 255), 2)

                    for hand_landmarks in results.multi_hand_landmarks:
                        mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                cv2.imshow('Friday Vision Controller', image)
                if cv2.waitKey(5) & 0xFF == 13: break 

        GestureController.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    gc = GestureController(); gc.start()