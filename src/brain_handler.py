import pyautogui
import subprocess
import time
import os
import webbrowser

class AIBrain:
    def __init__(self, voice_engine):
        self.voice = voice_engine
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1 

    def execute(self, query):
        query = query.lower().strip()
        executed_tasks = []

        # --- 1. REMOVED MANUAL MOVEMENT ---
        # Only keeping "Click" and "Scroll" as voice overrides
        if "click" in query:
            if "double" in query: 
                pyautogui.doubleClick()
                executed_tasks.append("Double Click")
            elif "right" in query:
                pyautogui.rightClick()
                executed_tasks.append("Right Click")
            else:
                pyautogui.click()
                executed_tasks.append("Left Click")

        # --- 2. SYSTEM CONTROLS (Volume & Brightness) ---
        if "volume" in query:
            if "up" in query: [pyautogui.press("volumeup") for _ in range(5)]
            elif "down" in query: [pyautogui.press("volumedown") for _ in range(5)]
            executed_tasks.append("Volume Adjusted")

        # --- 3. UNIVERSAL APP LAUNCHER ---
        if "open" in query or "kholo" in query:
            app = query.replace("open", "").replace("kholo", "").replace("friday", "").strip()
            
            # Smart URL detection
            if any(ext in app for ext in [".com", ".in", ".org", "youtube", "google"]):
                url = app if app.startswith("http") else f"https://www.google.com/search?q={app}"
                webbrowser.open(url)
            else:
                # 'start' command handles local apps perfectly
                subprocess.Popen(f"start {app}", shell=True)
            executed_tasks.append(f"Opening {app}")

        # --- 4. TYPING LOGIC ---
        if "type" in query or "likho" in query:
            text = query.replace("type", "").replace("likho", "").strip()
            self.voice.speak("Sir, please position the cursor. Typing in 2 seconds.")
            time.sleep(2) # Give user time to move hand to text field
            pyautogui.write(text, interval=0.03)
            executed_tasks.append("Text Input")

        # --- 5. CALCULATOR ---
        if "calculate" in query or "hisab" in query:
            task = query.replace("calculate", "").replace("hisab", "").strip()
            subprocess.Popen("calc.exe")
            time.sleep(1.2)
            pyautogui.write(task.replace("plus", "+").replace("minus", "-").replace("into", "*").replace("divided", "/"))
            pyautogui.press('enter')
            executed_tasks.append("Calculation")

        # --- 6. WINDOW MANAGEMENT ---
        if "minimize" in query: 
            pyautogui.hotkey('win', 'm')
            executed_tasks.append("Minimized")
        elif "close" in query or "band karo" in query:
            pyautogui.hotkey('alt', 'f4')
            executed_tasks.append("Closed Window")

        if not executed_tasks:
            return None # Brain didn't find a command
        
        return f"Friday: {', '.join(executed_tasks)} complete."