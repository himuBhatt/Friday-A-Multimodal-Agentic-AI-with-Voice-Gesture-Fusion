import ollama

class FridayBrain:
    def __init__(self, model_name="llama3.2:1b"): 
        self.model = model_name
        # Friday's Identity & System Instructions
        self.messages = [
            {
                'role': 'system', 
                'content': (
                    "You are FRIDAY, an advanced AI for an HP 255 laptop. "
                    "Be witty, concise (max 15 words), and efficient. "
                    "If a user asks to open an app, respond with 'Affirmative, launching [app name]'."
                )
            }
        ]
        print(f"🧠 Friday's Brain: Online ({self.model})")

    def think(self, user_input):
        """Processes input and returns Friday's witty response."""
        # Add user message to history
        self.messages.append({'role': 'user', 'content': user_input})
        
        try:
            response = ollama.chat(model=self.model, messages=self.messages)
            friday_reply = response['message']['content']
            
            # Add Friday's reply to history
            self.messages.append({'role': 'assistant', 'content': friday_reply})
            
            # Keep history short to save RAM (last 5 exchanges)
            if len(self.messages) > 11: 
                self.messages = [self.messages[0]] + self.messages[-10:]
                
            return friday_reply
        except Exception as e:
            return f"Brain Error: {e}. Check if Ollama is running in your tray."

# --- TEST THE BRAIN ---
if __name__ == "__main__":
    brain = FridayBrain()
    print("You: Friday, what is your status?")
    print(f"Friday: {brain.think('Friday, what is your status?')}")