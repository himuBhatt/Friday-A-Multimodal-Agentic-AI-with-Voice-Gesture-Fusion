from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import threading
import sys
import os

# Ensure the 'src' directory is in the system path for module imports
sys.path.append(os.path.join(os.getcwd(), 'src'))

try:
    from main_bot import FridayAgent
    from vision_module import SharedState
except ImportError as e:
    print(f"❌ Import Error: {e}. Ensure your folder structure matches 'src/'.")
    sys.exit(1)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'friday_ai_core_2026'

# Initialize SocketIO with threading mode for background AI tasks
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global instance of the Friday Agent
friday = FridayAgent()

def web_logger(message, sender="user"):
    """
    Callback function passed to Friday modules to update the Web UI.
    sender: 'user' (white text) or 'friday' (cyan text)
    """
    print(f"🌐 Web Log: [{sender.upper()}] {message}")
    socketio.emit('new_log', {'text': message, 'sender': sender})

# Inject the logger into the SharedState so all modules can access it
SharedState.web_logger = web_logger

@app.route('/')
def index():
    """Serves the main Cyberpunk HUD interface."""
    return render_template('index.html')

@app.route('/api/toggle', methods=['POST'])
def toggle_systems():
    """API endpoint to start/stop the AI Core."""
    if not friday.is_running:
        # Launching Friday in a background thread to prevent Flask from freezing
        try:
            threading.Thread(target=friday.run, daemon=True).start()
            return jsonify({"status": "online", "message": "Core Initialized"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        friday.stop()
        return jsonify({"status": "offline", "message": "Core Terminated"})

if __name__ == '__main__':
    # Use socketio.run instead of app.run to enable WebSocket support
    print("🛰️ FRIDAY Server starting on http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)