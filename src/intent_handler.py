import os
import subprocess

class IntentHandler:
    def __init__(self):
        # Dictionary of keywords Friday might say vs actual Windows commands
        self.apps = {
            "chrome": "start chrome",
            "google": "start chrome",
            "notepad": "start notepad",
            "calculator": "start calc",
            "code": "code .",  # Opens VS Code in current folder
            "explorer": "start .",
            "cmd": "start cmd",
            "task manager": "start taskmgr"
        }

    def execute(self, friday_text):
        """Scans Friday's reply for keywords and triggers the system."""
        lowered_text = friday_text.lower()
        
        for app, command in self.apps.items():
            if app in lowered_text:
                print(f"⚡ Friday Action: Launching {app}...")
                try:
                    # Using Popen so it doesn't freeze Friday while the app opens
                    subprocess.Popen(command, shell=True)
                    return True
                except Exception as e:
                    print(f"❌ Execution Error: {e}")
        return False