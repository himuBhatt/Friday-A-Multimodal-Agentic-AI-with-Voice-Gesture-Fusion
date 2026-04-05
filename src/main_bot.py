import threading
import time
from voice_module import VoiceSystem
from brain_handler import AIBrain
from vision_module import GestureController, SharedState

class FridayAgent:
    def __init__(self):
        # Initialize modules
        self.voice = VoiceSystem()
        self.brain = AIBrain(self.voice)
        self.vision = GestureController()
        
        # Thread control
        self.is_running = False
        self._voice_thread = None

    def autonomous_voice_loop(self):
        """Background thread for processing speech commands"""
        self.voice.speak("Systems initialized. I am online and monitoring, sir.", force=True)
        
        while self.is_running:
            # listen() now handles 'voice on/off' internally via SharedState
            query = self.voice.listen()
            
            if not query:
                continue
                
            # Global Shutdown Command
            if any(word in query for word in ["terminate session", "full shutdown", "system exit"]):
                self.voice.speak("Powering down all modules. Goodbye, sir.", force=True)
                self.stop()
                break
                
            # Brain processing (only returns response if voice_active is True)
            response = self.brain.execute(query)
            
            if response:
                self.voice.speak(response)
            
            time.sleep(0.1) # Prevent CPU spiking

    def run(self):
        """Called by the Flask backend to start the agent"""
        if self.is_running:
            print("⚠️ Friday is already running.")
            return

        self.is_running = True
        
        # 1. Start Voice Loop in Background
        self._voice_thread = threading.Thread(target=self.autonomous_voice_loop)
        self._voice_thread.daemon = True
        self._voice_thread.start()

        # 2. Start Vision Loop in the Current Thread
        # (This thread was spawned by app.py)
        print("🚀 Vision Core: Online")
        try:
            self.vision.start()
        except Exception as e:
            print(f"❌ Vision Error: {e}")
            self.stop()

    def stop(self):
        """Gracefully shuts down all subsystems"""
        print("🛑 Shutting down Friday...")
        self.is_running = False
        SharedState.keyboard_active = False # Close HUD
        
        # Release Camera via vision module
        if hasattr(self.vision, 'cap') and self.vision.cap.isOpened():
            self.vision.cap.release()
            
        # Stop any active audio
        import pygame
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()

if __name__ == "__main__":
    # For standalone testing
    friday = FridayAgent()
    friday.run()