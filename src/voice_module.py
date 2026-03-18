import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import time

class VoiceSystem:
    def __init__(self):
        # Initialize mixer with specific frequency to avoid 'chipmunk' voice
        pygame.mixer.init(frequency=24000) 
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300 # Adjusts sensitivity to noise

    def speak(self, text):
        if not text: return
        print(f"🤖 FRIDAY: {text}")
        
        try:
            tts = gTTS(text=text, lang='hi') # Hindi support active
            filename = f"speech_{int(time.time())}.mp3" # Unique name to avoid conflicts
            tts.save(filename)
            
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            
            pygame.mixer.music.unload()
            # Safety delay before deletion
            time.sleep(0.1) 
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            print(f"⚠️ Speak Error: {e}")

    def listen(self):
        with sr.Microphone() as source:
            # Clear console and show listening status
            print("\r🎤 Sun raha hoon sir...", end="", flush=True)
            self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
            
            try:
                # phrase_time_limit prevents Friday from listening for too long
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=8)
                query = self.recognizer.recognize_google(audio, language='en-IN')
                print(f"\r🗣️ User: {query}")
                return query.lower()
            except sr.WaitTimeoutError:
                return ""
            except sr.UnknownValueError:
                return ""
            except Exception as e:
                print(f"\n⚠️ Listen Error: {e}")
                return ""