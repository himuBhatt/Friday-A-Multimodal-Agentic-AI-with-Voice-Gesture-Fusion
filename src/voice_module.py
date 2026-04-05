"""
FRIDAY - Voice System Module
==============================
Enhanced voice engine with offline TTS fallback, wake-word detection,
audio queue, noise profiling, confidence filtering, and web dashboard hooks.

Backward compatible: All existing VoiceSystem / SharedState API is preserved.

Author  : Enhanced by AI Developer
Version : 2.0.0
Requires: speechrecognition, pygame, gtts, pyttsx3
Install : pip install SpeechRecognition pygame gtts pyttsx3
Optional: pip install vosk  (for fully offline STT)
"""

import os
import sys
import time
import queue
import logging
import threading
import tempfile
import datetime
import platform
from threading import Lock, Event
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Callable

# ── Core audio deps ──────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    print("⚠️  SpeechRecognition not found — run: pip install SpeechRecognition")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("⚠️  pygame not found — run: pip install pygame")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

# ── Offline TTS fallback ──────────────────────────────────────────────────────
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

# ── Optional: fully offline STT via Vosk ─────────────────────────────────────
try:
    from vosk import Model as VoskModel, KaldiRecognizer
    import json as _json
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════

LOG_DIR = Path.home() / "FRIDAY_Logs"
LOG_DIR.mkdir(exist_ok=True)

_handler = RotatingFileHandler(
    LOG_DIR / "voice.log",
    maxBytes=2 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
)
logger = logging.getLogger("FRIDAY.Voice")
logger.setLevel(logging.DEBUG)
logger.addHandler(_handler)
logger.addHandler(logging.StreamHandler(sys.stdout))


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED STATE  (fully backward compatible + new fields)
# ══════════════════════════════════════════════════════════════════════════════

try:
    from vision_module import SharedState
    if not hasattr(SharedState, "voice_active"):
        SharedState.voice_active = True
    # Inject new fields if missing (safe no-ops if already present)
    for _attr, _val in [
        ("tts_engine", "auto"),        # "gtts" | "pyttsx3" | "auto"
        ("stt_engine", "google"),      # "google" | "vosk"
        ("wake_word", "friday"),       # customisable wake word
        ("wake_word_required", False), # if True, only respond after wake word
        ("confidence_threshold", 0.0), # 0.0 = accept all (Google doesn't expose confidence)
        ("noise_profile_done", False),
        ("last_query", ""),
        ("last_response", ""),
        ("query_count", 0),
        ("error_count", 0),
    ]:
        if not hasattr(SharedState, _attr):
            setattr(SharedState, _attr, _val)

except ImportError:
    class SharedState:
        # ── Original fields (unchanged) ──
        is_speaking         : bool          = False
        is_listening        : bool          = False
        voice_active        : bool          = True
        web_logger          : Optional[Callable] = None

        # ── New fields ──
        tts_engine          : str           = "auto"      # "gtts" | "pyttsx3" | "auto"
        stt_engine          : str           = "google"    # "google" | "vosk"
        wake_word           : str           = "friday"
        wake_word_required  : bool          = False
        confidence_threshold: float         = 0.0
        noise_profile_done  : bool          = False
        last_query          : str           = ""
        last_response       : str           = ""
        query_count         : int           = 0
        error_count         : int           = 0


# ══════════════════════════════════════════════════════════════════════════════
#  TTS ENGINE  (gTTS online  +  pyttsx3 offline fallback)
# ══════════════════════════════════════════════════════════════════════════════

class TTSEngine:
    """
    Unified text-to-speech layer.
    Tries gTTS (online, Indian English accent) first;
    falls back to pyttsx3 (offline) automatically or on demand.
    """

    def __init__(self):
        self._pyttsx3_engine = None
        self._pyttsx3_lock   = Lock()
        self._tmp_dir        = Path(tempfile.gettempdir()) / "friday_tts"
        self._tmp_dir.mkdir(exist_ok=True)
        self._init_pyttsx3()

    def _init_pyttsx3(self):
        if not PYTTSX3_AVAILABLE:
            return
        try:
            self._pyttsx3_engine = pyttsx3.init()
            # Rate and volume matching gTTS feel
            self._pyttsx3_engine.setProperty("rate", 165)
            self._pyttsx3_engine.setProperty("volume", 0.95)
            # Prefer an Indian English voice if available
            voices = self._pyttsx3_engine.getProperty("voices")
            for v in voices:
                if "india" in v.name.lower() or "en_in" in v.id.lower():
                    self._pyttsx3_engine.setProperty("voice", v.id)
                    break
            logger.info("pyttsx3 offline TTS initialised.")
        except Exception as e:
            logger.warning(f"pyttsx3 init failed: {e}")
            self._pyttsx3_engine = None

    def synthesize(self, text: str, engine_preference: str = "auto") -> Optional[Path]:
        """
        Convert text → audio file.
        Returns path to .mp3/.wav, or None if both engines fail.
        engine_preference: "gtts" | "pyttsx3" | "auto"
        """
        ts = int(time.time() * 1000)

        # ── gTTS (online) ────────────────────────────────────────────────────
        if engine_preference in ("gtts", "auto") and GTTS_AVAILABLE:
            try:
                path = self._tmp_dir / f"tts_{ts}.mp3"
                gTTS(text=text, lang="en-IN").save(str(path))
                logger.debug(f"gTTS synthesised: {path.name}")
                return path
            except Exception as e:
                logger.warning(f"gTTS failed ({e}), falling back to pyttsx3.")

        # ── pyttsx3 (offline fallback) ────────────────────────────────────────
        if PYTTSX3_AVAILABLE and self._pyttsx3_engine:
            try:
                path = self._tmp_dir / f"tts_{ts}.wav"
                with self._pyttsx3_lock:
                    self._pyttsx3_engine.save_to_file(text, str(path))
                    self._pyttsx3_engine.runAndWait()
                logger.debug(f"pyttsx3 synthesised: {path.name}")
                return path
            except Exception as e:
                logger.error(f"pyttsx3 synthesis failed: {e}")

        logger.error("All TTS engines failed.")
        return None

    def cleanup(self, path: Path):
        try:
            if path and path.exists():
                path.unlink()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  AUDIO PLAYER  (pygame-backed, non-blocking queue)
# ══════════════════════════════════════════════════════════════════════════════

class AudioPlayer:
    """
    Plays audio files through pygame.
    Uses an internal queue so speak() calls from different threads
    never overlap — each utterance waits its turn.
    """

    def __init__(self):
        if PYGAME_AVAILABLE:
            pygame.mixer.pre_init(frequency=24000, size=-16, channels=1, buffer=512)
            pygame.mixer.init()
        self._queue : queue.Queue = queue.Queue()
        self._lock  : Lock        = Lock()
        self._worker = threading.Thread(target=self._playback_worker, daemon=True)
        self._worker.start()

    def enqueue(self, path: Path, blocking: bool = True):
        """Add a file to the playback queue. If blocking, wait until done."""
        done_event = Event()
        self._queue.put((path, done_event))
        if blocking:
            done_event.wait()

    def _playback_worker(self):
        while True:
            path, done_event = self._queue.get()
            if PYGAME_AVAILABLE and path and path.exists():
                try:
                    with self._lock:
                        pygame.mixer.music.load(str(path))
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)
                        pygame.mixer.music.unload()
                except Exception as e:
                    logger.error(f"Playback error: {e}")
            done_event.set()
            self._queue.task_done()

    def stop(self):
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  NOISE PROFILER
# ══════════════════════════════════════════════════════════════════════════════

class NoiseProfiler:
    """
    Builds a rolling ambient noise baseline and recommends
    an energy threshold for the recognizer.
    """

    SAMPLE_DURATION = 1.2   # seconds per sample
    HISTORY_SIZE    = 5     # rolling window

    def __init__(self):
        self._samples: list[float] = []

    def calibrate(self, recognizer: "sr.Recognizer") -> float:
        """
        Perform a fresh calibration and return the recommended threshold.
        Called automatically on first listen() if not yet done.
        """
        if not SR_AVAILABLE:
            return 400.0
        try:
            with sr.Microphone() as src:
                recognizer.adjust_for_ambient_noise(src, duration=self.SAMPLE_DURATION)
            threshold = recognizer.energy_threshold * 1.2   # 20% headroom
            self._samples.append(threshold)
            if len(self._samples) > self.HISTORY_SIZE:
                self._samples.pop(0)
            avg = sum(self._samples) / len(self._samples)
            logger.info(f"Noise calibration: threshold={avg:.0f}")
            SharedState.noise_profile_done = True
            return avg
        except Exception as e:
            logger.warning(f"Noise calibration failed: {e}")
            return 400.0


# ══════════════════════════════════════════════════════════════════════════════
#  COMMAND HISTORY
# ══════════════════════════════════════════════════════════════════════════════

class CommandHistory:
    """Keeps a rolling in-memory log of the last N recognised commands."""

    MAX = 50

    def __init__(self):
        self._log: list[dict] = []
        self._lock = Lock()

    def record(self, query: str, response: str = ""):
        entry = {
            "time"    : datetime.datetime.now().strftime("%H:%M:%S"),
            "query"   : query,
            "response": response,
        }
        with self._lock:
            self._log.append(entry)
            if len(self._log) > self.MAX:
                self._log.pop(0)

    def last(self, n: int = 5) -> list[dict]:
        with self._lock:
            return list(self._log[-n:])

    def clear(self):
        with self._lock:
            self._log.clear()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN VOICE SYSTEM  (backward compatible drop-in replacement)
# ══════════════════════════════════════════════════════════════════════════════

class VoiceSystem:
    """
    FRIDAY's voice I/O system.

    Public API (unchanged from v1):
        speak(text, force=False)
        listen() → str

    New public API:
        speak_async(text, force=False)        — non-blocking speak
        set_wake_word(word)                   — change wake word at runtime
        set_tts_engine(engine)                — "gtts" | "pyttsx3" | "auto"
        set_stt_engine(engine)                — "google" | "vosk"
        noise_calibrate()                     — manual recalibration
        history.last(n)                       — last N commands
        status() → dict                       — engine health report
    """

    VERSION = "2.0.0"

    # ── Wake / control command vocabularies ──────────────────────────────────
    _WAKE_ON_PHRASES  = {"voice on",  "activate voice", "start listening", "awake"}
    _WAKE_OFF_PHRASES = {"voice off", "deactivate voice", "stop listening", "sleep"}
    _NOISE_CAL_PHRASES = {"recalibrate", "calibrate noise", "adjust microphone"}

    def __init__(self):
        logger.info(f"VoiceSystem v{self.VERSION} initialising…")

        # Sub-components
        self._tts      = TTSEngine()
        self._player   = AudioPlayer()
        self._profiler = NoiseProfiler()
        self.history   = CommandHistory()

        # Speech recognizer setup (same settings as v1 + new fields)
        if SR_AVAILABLE:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold        = 400
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold          = 0.8   # NEW: tighter pause detection
            self.recognizer.phrase_threshold         = 0.3   # NEW: faster phrase start
        else:
            self.recognizer = None

        self._audio_lock = Lock()   # kept for compatibility
        self._vosk_model  = None    # lazy-loaded

        logger.info(f"VoiceSystem ready. TTS: {self._active_tts_label()} | "
                    f"STT: {SharedState.stt_engine}")

    # ──────────────────────────────────────────────────────────────────────────
    #  SPEAK  (original signature preserved)
    # ──────────────────────────────────────────────────────────────────────────

    def speak(self, text: str, force: bool = False):
        """
        Blocking TTS.  Identical call signature to v1.
        Now routes through the audio queue so concurrent calls never overlap.
        """
        if not text:
            return

        if not getattr(SharedState, "voice_active", True) and not force:
            return

        SharedState.is_speaking  = True
        SharedState.last_response = text

        # Web dashboard hook (unchanged from v1)
        if SharedState.web_logger:
            try:
                SharedState.web_logger(text, sender="friday")
            except Exception as e:
                logger.warning(f"web_logger error: {e}")

        pref = getattr(SharedState, "tts_engine", "auto")
        audio_path = self._tts.synthesize(text, engine_preference=pref)

        try:
            if audio_path:
                self._player.enqueue(audio_path, blocking=True)
                self._tts.cleanup(audio_path)
            else:
                # Last resort: print to console so the assistant isn't completely silent
                print(f"[FRIDAY] {text}")
        except Exception as e:
            logger.error(f"speak() playback error: {e}")
        finally:
            SharedState.is_speaking = False

    # ──────────────────────────────────────────────────────────────────────────
    #  SPEAK ASYNC  (new — non-blocking fire-and-forget)
    # ──────────────────────────────────────────────────────────────────────────

    def speak_async(self, text: str, force: bool = False):
        """Non-blocking version of speak(). Returns immediately."""
        t = threading.Thread(target=self.speak, args=(text, force), daemon=True)
        t.start()

    # ──────────────────────────────────────────────────────────────────────────
    #  LISTEN  (original signature preserved)
    # ──────────────────────────────────────────────────────────────────────────

    def listen(self) -> str:
        """
        Listen for a voice command and return recognised text (lowercase).
        Returns "" on silence / error — identical behaviour to v1.

        New behaviour (non-breaking):
        - Auto-calibrates noise on first call
        - Supports wake-word gating (off by default)
        - Routes to Vosk (offline) when SharedState.stt_engine == "vosk"
        - Records query to CommandHistory
        - Updates SharedState.last_query and SharedState.query_count
        """
        if SharedState.is_speaking:
            return ""

        if not SR_AVAILABLE or self.recognizer is None:
            logger.warning("SpeechRecognition not available.")
            return ""

        # First-run noise calibration
        if not SharedState.noise_profile_done:
            threshold = self._profiler.calibrate(self.recognizer)
            self.recognizer.energy_threshold = threshold

        with sr.Microphone() as source:
            SharedState.is_listening = True
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

            try:
                audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=6)
                SharedState.is_listening = False

                # ── Transcription ──────────────────────────────────────────
                query = self._transcribe(audio)
                if not query:
                    return ""

                logger.debug(f"Recognised: '{query}'")

                # ── Built-in control commands (checked before wake-word) ───
                control = self._handle_control_commands(query)
                if control is not None:
                    return control

                # ── Wake-word gating (optional, off by default) ────────────
                if getattr(SharedState, "wake_word_required", False):
                    ww = getattr(SharedState, "wake_word", "friday").lower()
                    if ww not in query:
                        return ""
                    query = query.replace(ww, "").strip()

                # ── Voice-off gate ─────────────────────────────────────────
                if not getattr(SharedState, "voice_active", True):
                    return ""

                # ── Web dashboard hook ─────────────────────────────────────
                if SharedState.web_logger:
                    try:
                        SharedState.web_logger(query, sender="user")
                    except Exception as e:
                        logger.warning(f"web_logger error: {e}")

                # ── State bookkeeping ──────────────────────────────────────
                SharedState.last_query  = query
                SharedState.query_count = getattr(SharedState, "query_count", 0) + 1
                self.history.record(query)

                return query

            except Exception:
                SharedState.is_listening = False
                SharedState.error_count  = getattr(SharedState, "error_count", 0) + 1
                return ""

    # ──────────────────────────────────────────────────────────────────────────
    #  INTERNAL: TRANSCRIPTION
    # ──────────────────────────────────────────────────────────────────────────

    def _transcribe(self, audio) -> str:
        """Route audio to the configured STT engine."""
        engine = getattr(SharedState, "stt_engine", "google")

        if engine == "vosk" and VOSK_AVAILABLE:
            return self._transcribe_vosk(audio)

        # Default: Google Web Speech (same as v1)
        try:
            return self.recognizer.recognize_google(audio, language="en-IN").lower()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            logger.warning(f"Google STT unavailable ({e}), trying pyttsx3 offline path.")
            SharedState.error_count = getattr(SharedState, "error_count", 0) + 1
            # Auto-fallback to Vosk if available
            if VOSK_AVAILABLE:
                return self._transcribe_vosk(audio)
            return ""

    def _transcribe_vosk(self, audio) -> str:
        """Offline transcription using Vosk."""
        if self._vosk_model is None:
            model_path = Path.home() / "vosk-model"
            if not model_path.exists():
                logger.warning(
                    "Vosk model not found at ~/vosk-model. "
                    "Download from https://alphacephei.com/vosk/models"
                )
                return ""
            try:
                self._vosk_model = VoskModel(str(model_path))
                logger.info("Vosk model loaded.")
            except Exception as e:
                logger.error(f"Vosk model load failed: {e}")
                return ""

        try:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            rec  = KaldiRecognizer(self._vosk_model, 16000)
            rec.AcceptWaveform(raw)
            result = _json.loads(rec.Result())
            return result.get("text", "").lower()
        except Exception as e:
            logger.error(f"Vosk transcription failed: {e}")
            return ""

    # ──────────────────────────────────────────────────────────────────────────
    #  INTERNAL: CONTROL COMMANDS
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_control_commands(self, query: str) -> Optional[str]:
        """
        Handle built-in wake/sleep/calibrate commands.
        Returns a sentinel string if handled, None if not a control command.
        Mirrors v1 behaviour for "voice on" / "voice off".
        """
        # ── Voice ON ──────────────────────────────────────────────────────────
        if any(p in query for p in self._WAKE_ON_PHRASES) or "voice on" in query:
            if not SharedState.voice_active:
                SharedState.voice_active = True
                self.speak(
                    "Voice systems activated. I am online and responding, sir.",
                    force=True
                )
            return "voice_on_triggered"

        # ── Voice OFF ─────────────────────────────────────────────────────────
        if any(p in query for p in self._WAKE_OFF_PHRASES) or "voice off" in query:
            if SharedState.voice_active:
                self.speak(
                    "Deactivating voice response. "
                    "I'll be waiting for the 'voice on' command.",
                    force=True
                )
                SharedState.voice_active = False
            return "voice_off_triggered"

        # ── Noise recalibration ───────────────────────────────────────────────
        if any(p in query for p in self._NOISE_CAL_PHRASES):
            SharedState.noise_profile_done = False
            self.speak("Recalibrating microphone for ambient noise.", force=True)
            threshold = self._profiler.calibrate(self.recognizer)
            self.recognizer.energy_threshold = threshold
            self.speak(f"Calibration complete. Threshold set to {threshold:.0f}.", force=True)
            return "calibration_triggered"

        # ── History query ─────────────────────────────────────────────────────
        if "command history" in query or "what did i say" in query:
            entries = self.history.last(3)
            if entries:
                summary = ". ".join(e["query"] for e in entries)
                self.speak(f"Your last commands were: {summary}", force=True)
            else:
                self.speak("No command history yet.", force=True)
            return "history_triggered"

        return None   # not a control command

    # ──────────────────────────────────────────────────────────────────────────
    #  CONFIGURATION SETTERS
    # ──────────────────────────────────────────────────────────────────────────

    def set_wake_word(self, word: str):
        """Change the wake word at runtime. Pass '' to disable."""
        SharedState.wake_word = word.lower().strip()
        SharedState.wake_word_required = bool(word.strip())
        logger.info(f"Wake word set to: '{SharedState.wake_word}' | "
                    f"Required: {SharedState.wake_word_required}")

    def set_tts_engine(self, engine: str):
        """Switch TTS engine: 'gtts' | 'pyttsx3' | 'auto'"""
        if engine not in ("gtts", "pyttsx3", "auto"):
            logger.warning(f"Unknown TTS engine: {engine}")
            return
        SharedState.tts_engine = engine
        logger.info(f"TTS engine set to: {engine}")

    def set_stt_engine(self, engine: str):
        """Switch STT engine: 'google' | 'vosk'"""
        if engine not in ("google", "vosk"):
            logger.warning(f"Unknown STT engine: {engine}")
            return
        SharedState.stt_engine = engine
        logger.info(f"STT engine set to: {engine}")

    def noise_calibrate(self):
        """Manually trigger a fresh noise calibration."""
        SharedState.noise_profile_done = False
        if self.recognizer:
            threshold = self._profiler.calibrate(self.recognizer)
            self.recognizer.energy_threshold = threshold

    # ──────────────────────────────────────────────────────────────────────────
    #  STATUS REPORT
    # ──────────────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a health/config snapshot — useful for web dashboards."""
        return {
            "version"          : self.VERSION,
            "voice_active"     : SharedState.voice_active,
            "is_speaking"      : SharedState.is_speaking,
            "is_listening"     : SharedState.is_listening,
            "tts_engine"       : getattr(SharedState, "tts_engine", "auto"),
            "stt_engine"       : getattr(SharedState, "stt_engine", "google"),
            "wake_word"        : getattr(SharedState, "wake_word", "friday"),
            "wake_word_required": getattr(SharedState, "wake_word_required", False),
            "noise_calibrated" : SharedState.noise_profile_done,
            "energy_threshold" : self.recognizer.energy_threshold if self.recognizer else None,
            "query_count"      : getattr(SharedState, "query_count", 0),
            "error_count"      : getattr(SharedState, "error_count", 0),
            "gtts_available"   : GTTS_AVAILABLE,
            "pyttsx3_available": PYTTSX3_AVAILABLE,
            "vosk_available"   : VOSK_AVAILABLE,
            "last_query"       : getattr(SharedState, "last_query", ""),
        }

    # ──────────────────────────────────────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _active_tts_label(self) -> str:
        if GTTS_AVAILABLE:
            return "gTTS (online) + pyttsx3 fallback" if PYTTSX3_AVAILABLE else "gTTS (online only)"
        if PYTTSX3_AVAILABLE:
            return "pyttsx3 (offline only)"
        return "NONE — install gtts or pyttsx3"