import threading
from voice_module import VoiceSystem
from brain_handler import AIBrain
from vision_module import GestureController # Import your vision class

class FridayAgent:
    def __init__(self):
        self.voice = VoiceSystem()
        self.brain = AIBrain(self.voice)
        self.vision = GestureController()
        self.is_running = True

    def autonomous_voice_loop(self):
        """This runs in the background (Thread)"""
        self.voice.speak("Friday is now fully autonomous. I am monitoring your voice commands, sir.")
        
        while self.is_running:
            query = self.voice.listen()
            
            if not query:
                continue
                
            # Stop command
            if any(word in query for word in ["go to sleep", "offline", "shutdown"]):
                self.voice.speak("Systems powering down. Goodbye sir.")
                self.is_running = False
                # Optionally kill the vision window here
                break
                
            # Autonomous execution via Brain
            response = self.brain.execute(query)
            
            # Friday talks back
            if response:
                self.voice.speak(response)

    def run(self):
        # 1. Start the Voice/Brain thread
        voice_thread = threading.Thread(target=self.autonomous_voice_loop)
        voice_thread.daemon = True  # Ensures thread dies when main program exits
        voice_thread.start()

        # 2. Start the Vision loop (Main Thread)
        # This will open your Camera and HUD
        print("🚀 Systems Initializing... Vision Online.")
        self.vision.start()

if __name__ == "__main__":
    friday = FridayAgent()
    friday.run()