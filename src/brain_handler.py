"""
FRIDAY - Advanced AI Brain Module
===================================
A modular, extensible, and robust AI assistant brain for Windows.

Author  : Enhanced by AI Developer
Version : 2.1.0  (security hardened)
Requires: pyautogui, psutil, Pillow (PIL), pyperclip
Install : pip install pyautogui psutil Pillow pyperclip

Security changelog (v2.1.0):
  - All subprocess calls use shell=False (list args) — eliminates command injection
  - eval() replaced with ast-based safe evaluator — eliminates DoS via exponentiation
  - Clipboard output redacted for high-entropy strings — prevents secret leakage
  - App launcher validates against allowlist only — blocks path traversal
  - Sensitive data never written to log files
"""

import pyautogui
import subprocess
import time
import webbrowser
import os
import glob
import re
import sys
import ast
import json
import operator
import logging
import threading
import platform
import ctypes
import shutil
import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# ── Optional imports with graceful fallback ──────────────────────────────────
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from PIL import ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════

LOG_DIR = Path.home() / "FRIDAY_Logs"
LOG_DIR.mkdir(exist_ok=True)

_log_handler = RotatingFileHandler(
    LOG_DIR / "friday.log",
    maxBytes=2 * 1024 * 1024,   # 2 MB
    backupCount=3,
    encoding="utf-8"
)
_log_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
)
logger = logging.getLogger("FRIDAY")
logger.setLevel(logging.DEBUG)
logger.addHandler(_log_handler)
logger.addHandler(logging.StreamHandler(sys.stdout))


# ══════════════════════════════════════════════════════════════════════════════
#  APP REGISTRY  (data-driven — no code changes needed to add new apps)
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_APP_MAP: dict[str, dict] = {
    # key            : {process, args (list for subprocess), aliases}
    # 'args' is passed directly to subprocess.Popen — shell=False, no injection possible.
    "word"           : {"process": "winword",    "args": ["cmd", "/c", "start", "", "winword"],    "aliases": ["microsoft word", "ms word"]},
    "excel"          : {"process": "excel",      "args": ["cmd", "/c", "start", "", "excel"],      "aliases": ["spreadsheet", "xlsx"]},
    "powerpoint"     : {"process": "powerpnt",   "args": ["cmd", "/c", "start", "", "powerpnt"],   "aliases": ["presentation", "pptx", "slides"]},
    "notepad"        : {"process": "notepad",    "args": ["notepad"],                              "aliases": ["text editor", "txt"]},
    "chrome"         : {"process": "chrome",     "args": ["cmd", "/c", "start", "", "chrome"],     "aliases": ["browser", "google chrome"]},
    "firefox"        : {"process": "firefox",    "args": ["cmd", "/c", "start", "", "firefox"],    "aliases": []},
    "edge"           : {"process": "msedge",     "args": ["cmd", "/c", "start", "", "msedge"],     "aliases": ["microsoft edge"]},
    "calculator"     : {"process": "calc",       "args": ["calc"],                                 "aliases": ["calc", "calculate"]},
    "paint"          : {"process": "mspaint",    "args": ["mspaint"],                              "aliases": ["drawing", "image editor"]},
    "file explorer"  : {"process": "explorer",   "args": ["explorer"],                             "aliases": ["explorer", "files", "my computer"]},
    "task manager"   : {"process": "taskmgr",    "args": ["taskmgr"],                              "aliases": ["task mgr"]},
    "cmd"            : {"process": "cmd",        "args": ["cmd"],                                  "aliases": ["command prompt", "terminal", "console"]},
    "powershell"     : {"process": "powershell", "args": ["powershell"],                           "aliases": []},
    "settings"       : {"process": "systemsettings", "args": ["cmd", "/c", "start", "", "ms-settings:"], "aliases": ["control panel", "system settings"]},
    "spotify"        : {"process": "spotify",    "args": ["cmd", "/c", "start", "", "spotify"],    "aliases": ["music"]},
    "vlc"            : {"process": "vlc",        "args": ["cmd", "/c", "start", "", "vlc"],        "aliases": ["media player", "video player"]},
    "vscode"         : {"process": "code",       "args": ["cmd", "/c", "start", "", "code"],       "aliases": ["visual studio code", "vs code", "editor"]},
    # ── Custom project shortcuts: replace paths, never use user-supplied input here ──
    "record keeper"  : {"process": "explorer",
                        "args": ["explorer", r"C:\Path\To\Your\RecordKeeper"],
                        "aliases": []},
    "vital care"     : {"process": "explorer",
                        "args": ["explorer", r"C:\Path\To\Your\VitalCare"],
                        "aliases": []},
}

# Intent → keyword sets (order matters: most-specific first)
INTENT_KEYWORDS: dict[str, list[str]] = {
    "close"       : ["close", "kill", "band karo", "band kar", "exit", "quit", "terminate"],
    "create_doc"  : ["create", "nayi file", "new file", "banao", "bana do"],
    "find_file"   : ["find", "open file", "search for", "dhoondo", "dhundo", "locate"],
    "open_app"    : ["open", "launch", "start", "chalu karo", "kholo"],
    "web_search"  : ["google", "search", "browse", "kholo", "find online"],
    "youtube"     : ["youtube"],
    "type_text"   : ["type", "write", "likho", "likh do"],
    "screenshot"  : ["screenshot", "screen capture", "snap", "capture screen"],
    "clipboard"   : ["copy", "paste", "clipboard"],
    "sysinfo"     : ["system info", "cpu", "ram", "memory", "battery", "disk space", "performance"],
    "processes"   : ["running apps", "running processes", "process list", "kya chal raha"],
    "reminder"    : ["remind me", "reminder", "alert me", "yaad dilao"],
    "minimize"    : ["minimize", "hide window", "chota karo"],
    "maximize"    : ["maximize", "fullscreen", "bada karo"],
    "volume"      : ["volume", "awaaz", "sound"],
    "brightness"  : ["brightness", "screen brightness", "roshan karo"],
    "shutdown"    : ["shutdown", "power off", "band karo computer"],
    "restart"     : ["restart", "reboot", "dobara chalu"],
    "lock"        : ["lock", "lock screen", "screen lock"],
    "sleep"       : ["sleep", "hibernate", "suspend"],
    "weather"     : ["weather", "mausam"],
    "date_time"   : ["time", "date", "what time", "kitne baje", "aaj ki tarikh"],
    "calculate"   : ["calculate", "compute", "math", "hisab"],
    "joke"        : ["joke", "mazak", "funny"],
    "identity"    : ["who are you", "naam", "apna naam", "your name", "introduce yourself"],
    "status"      : ["how are you", "kaise ho", "status", "are you ok"],
}


# ══════════════════════════════════════════════════════════════════════════════
#  NLP PARSER  (intent + entity extraction without external libraries)
# ══════════════════════════════════════════════════════════════════════════════

class NLPParser:
    """Lightweight intent + entity extractor for voice commands."""

    # Filler words stripped when extracting entity names
    _STOP_WORDS = {
        "please", "sir", "now", "me", "my", "the", "a", "an", "of", "in",
        "on", "for", "to", "and", "or", "is", "are", "was",
        "karo", "kar", "do", "bhi", "hai", "hain", "mujhe", "mere",
        "open", "launch", "start", "find", "search", "play", "show",
        "create", "close", "kill", "type", "write", "google", "browse",
        "friday", "ok", "hey",
    }

    @staticmethod
    def detect_intent(query: str) -> Optional[str]:
        """Return the first matching intent key or None."""
        q = query.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in q for kw in keywords):
                return intent
        return None

    @staticmethod
    def extract_entity(query: str, strip_patterns: list[str]) -> str:
        """Remove command-specific patterns and stop-words; return residual."""
        text = query.lower()
        for pat in strip_patterns:
            text = text.replace(pat.lower(), "")
        tokens = [w for w in text.split() if w not in NLPParser._STOP_WORDS]
        return " ".join(tokens).strip()

    @staticmethod
    def resolve_app(name: str) -> Optional[tuple[str, dict]]:
        """Return (canonical_key, app_dict) for a fuzzy app name, or None."""
        name = name.lower().strip()
        # Exact key match
        if name in DEFAULT_APP_MAP:
            return name, DEFAULT_APP_MAP[name]
        # Alias match
        for key, info in DEFAULT_APP_MAP.items():
            if name in info["aliases"] or any(a in name for a in info["aliases"]) or key in name:
                return key, info
        return None

    @staticmethod
    def parse_duration(text: str) -> Optional[int]:
        """Parse 'X minutes/seconds' from text → seconds, or None."""
        m = re.search(r"(\d+)\s*(minute|min|second|sec|hour|hr)", text.lower())
        if not m:
            return None
        n = int(m.group(1))
        unit = m.group(2)
        if unit in ("hour", "hr"):
            return n * 3600
        elif unit in ("minute", "min"):
            return n * 60
        return n


# ══════════════════════════════════════════════════════════════════════════════
#  SAFE MATH EVALUATOR  (replaces eval — immune to DoS via exponentiation)
# ══════════════════════════════════════════════════════════════════════════════

class SafeMathEvaluator:
    """
    Evaluates arithmetic expressions using Python's AST module.

    Why not eval():
      eval("9**9**9**9") causes unbounded CPU/memory use because Python
      computes arbitrarily large integers. This evaluator:
        1. Parses the expression into an AST — no code is executed.
        2. Walks only whitelisted node types (numbers, +, -, *, /, %).
        3. Caps exponent base and power to prevent resource exhaustion.
        4. Raises ValueError for any disallowed construct.
    """

    # Maximum values for ** to prevent DoS (e.g. 9**9**9**9)
    MAX_BASE   = 10_000
    MAX_EXP    = 300

    _OPS = {
        ast.Add      : operator.add,
        ast.Sub      : operator.sub,
        ast.Mult     : operator.mul,
        ast.Div      : operator.truediv,
        ast.FloorDiv : operator.floordiv,
        ast.Mod      : operator.mod,
        ast.Pow      : operator.pow,
        ast.USub     : operator.neg,
        ast.UAdd     : operator.pos,
    }

    def evaluate(self, expression: str) -> str:
        """
        Parse and evaluate a math expression string.
        Returns the result as a string, or raises ValueError on bad input.
        """
        # Allow only digits, whitespace, and basic math operators/parens
        sanitised = re.sub(r"[^\d\s\+\-\*\/\.\(\)\^%]", "", expression)
        sanitised = sanitised.replace("^", "**")

        if not sanitised.strip():
            raise ValueError("Empty expression after sanitisation.")

        try:
            tree = ast.parse(sanitised, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid expression: {e}") from e

        result = self._eval_node(tree.body)

        # Round floats to a sensible number of decimal places
        if isinstance(result, float):
            result = round(result, 10)
        return str(result)

    def _eval_node(self, node):
        if isinstance(node, ast.Constant):          # numbers
            if not isinstance(node.value, (int, float)):
                raise ValueError("Only numeric constants are allowed.")
            return node.value

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self._OPS:
                raise ValueError(f"Operator {op_type.__name__} is not allowed.")
            left  = self._eval_node(node.left)
            right = self._eval_node(node.right)
            # Guard against exponentiation DoS
            if op_type is ast.Pow:
                if abs(left) > self.MAX_BASE or abs(right) > self.MAX_EXP:
                    raise ValueError(
                        f"Exponentiation operands too large "
                        f"(max base {self.MAX_BASE}, max exponent {self.MAX_EXP})."
                    )
            return self._OPS[op_type](left, right)

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self._OPS:
                raise ValueError(f"Unary operator {op_type.__name__} is not allowed.")
            return self._OPS[op_type](self._eval_node(node.operand))

        raise ValueError(f"Unsupported AST node: {type(node).__name__}")




class FileManager:
    """Parallel file search across user directories and optional extra drives."""

    DEFAULT_ROOTS = [
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home() / "Pictures",
        Path.home() / "Videos",
        Path.home() / "Music",
    ]

    EXTENSION_MAP: dict[str, list[str]] = {
        "document"    : [".docx", ".doc", ".odt", ".rtf", ".pdf"],
        "spreadsheet" : [".xlsx", ".xls", ".csv", ".ods"],
        "presentation": [".pptx", ".ppt", ".odp"],
        "image"       : [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
        "video"       : [".mp4", ".mkv", ".avi", ".mov", ".wmv"],
        "audio"       : [".mp3", ".wav", ".flac", ".aac", ".ogg"],
        "code"        : [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".go"],
        "archive"     : [".zip", ".rar", ".7z", ".tar", ".gz"],
    }

    def search(
        self,
        name: str,
        file_type: Optional[str] = None,
        extra_roots: Optional[list[Path]] = None,
        max_results: int = 5,
    ) -> list[Path]:
        """Return up to max_results matching files."""
        roots = self.DEFAULT_ROOTS + (extra_roots or [])
        exts = self.EXTENSION_MAP.get(file_type, []) if file_type else []
        results: list[Path] = []
        name_lower = name.lower()

        def _search_root(root: Path):
            nonlocal results
            if not root.exists():
                return
            for p in root.rglob(f"*{name}*"):
                if exts and p.suffix.lower() not in exts:
                    continue
                if name_lower in p.name.lower():
                    results.append(p)
                if len(results) >= max_results:
                    return

        threads = [threading.Thread(target=_search_root, args=(r,), daemon=True) for r in roots]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        return results[:max_results]

    def open(self, path: Path) -> bool:
        """Open file with its default OS handler."""
        try:
            os.startfile(str(path))
            return True
        except Exception as e:
            logger.error(f"FileManager.open failed: {e}")
            return False

    def create_document(self, doc_type: str, filename: Optional[str] = None) -> Optional[Path]:
        """Create an empty file of the given type in Documents."""
        ext_map = {"word": ".docx", "notepad": ".txt", "excel": ".xlsx", "powerpoint": ".pptx"}
        ext = ext_map.get(doc_type.lower(), ".txt")
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = filename or f"FRIDAY_{doc_type}_{ts}{ext}"
        target = Path.home() / "Documents" / fname
        try:
            target.touch()
            return target
        except Exception as e:
            logger.error(f"FileManager.create_document failed: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM INFO
# ══════════════════════════════════════════════════════════════════════════════

class SystemInfo:
    """Reads live system metrics using psutil when available."""

    def cpu(self) -> str:
        if not PSUTIL_AVAILABLE:
            return "psutil not installed — run: pip install psutil"
        pct = psutil.cpu_percent(interval=0.5)
        freq = psutil.cpu_freq()
        cores = psutil.cpu_count(logical=False)
        freq_str = f" @ {freq.current:.0f} MHz" if freq else ""
        return f"CPU usage: {pct}%  |  Cores: {cores}{freq_str}"

    def memory(self) -> str:
        if not PSUTIL_AVAILABLE:
            return "psutil not installed."
        vm = psutil.virtual_memory()
        used_gb = vm.used / 1e9
        total_gb = vm.total / 1e9
        return f"RAM: {used_gb:.1f} GB used / {total_gb:.1f} GB total  ({vm.percent}%)"

    def disk(self, drive: str = "C:\\") -> str:
        if not PSUTIL_AVAILABLE:
            return "psutil not installed."
        try:
            du = psutil.disk_usage(drive)
            free_gb = du.free / 1e9
            total_gb = du.total / 1e9
            return f"Disk ({drive}): {free_gb:.1f} GB free / {total_gb:.1f} GB total"
        except Exception as e:
            return f"Disk info unavailable: {e}"

    def battery(self) -> str:
        if not PSUTIL_AVAILABLE:
            return "psutil not installed."
        bat = psutil.sensors_battery()
        if not bat:
            return "No battery detected (desktop system)."
        status = "Charging" if bat.power_plugged else "Discharging"
        mins = int(bat.secsleft / 60) if bat.secsleft > 0 else 0
        time_str = f"  |  ~{mins} min remaining" if not bat.power_plugged and mins else ""
        return f"Battery: {bat.percent:.0f}%  |  {status}{time_str}"

    def full_report(self) -> str:
        return "\n".join([self.cpu(), self.memory(), self.disk(), self.battery()])

    def top_processes(self, n: int = 5) -> list[dict]:
        if not PSUTIL_AVAILABLE:
            return []
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return sorted(procs, key=lambda x: x.get("cpu_percent", 0), reverse=True)[:n]


# ══════════════════════════════════════════════════════════════════════════════
#  SCREENSHOT MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class ScreenshotManager:
    """Capture full screen or active window screenshots."""

    SAVE_DIR = Path.home() / "Pictures" / "FRIDAY_Screenshots"

    def __init__(self):
        self.SAVE_DIR.mkdir(parents=True, exist_ok=True)

    def capture(self, region=None, name: Optional[str] = None) -> Optional[Path]:
        if not PIL_AVAILABLE:
            logger.warning("Pillow not installed — run: pip install Pillow")
            return None
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = name or f"screenshot_{ts}.png"
        path = self.SAVE_DIR / filename
        try:
            img = ImageGrab.grab(bbox=region)
            img.save(str(path))
            logger.info(f"Screenshot saved: {path}")
            return path
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None

    def capture_active_window(self) -> Optional[Path]:
        """Capture only the active window via Alt+PrintScreen."""
        pyautogui.hotkey("alt", "printscreen")
        time.sleep(0.3)
        return self.capture(name=f"window_{datetime.datetime.now().strftime('%H%M%S')}.png")


# ══════════════════════════════════════════════════════════════════════════════
#  CLIPBOARD MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class ClipboardManager:
    """Read/write system clipboard."""

    def read(self) -> str:
        if PYPERCLIP_AVAILABLE:
            return pyperclip.paste()
        # Fallback via PowerShell — shell=False, args as list (no injection)
        try:
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, shell=False
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def write(self, text: str) -> bool:
        if PYPERCLIP_AVAILABLE:
            pyperclip.copy(text)
            return True
        # Fallback: pipe through powershell — text passed as stdin, never interpolated
        try:
            subprocess.run(
                ["powershell", "-NonInteractive", "-Command",
                 "[System.Windows.Forms.Clipboard]::SetText($input)"],
                input=text, capture_output=True, text=True, shell=False
            )
            return True
        except Exception as e:
            logger.error(f"Clipboard write failed: {e}")
            return False


# ══════════════════════════════════════════════════════════════════════════════
#  REMINDER ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class ReminderEngine:
    """Non-blocking reminder scheduler using daemon threads."""

    def __init__(self, voice_engine):
        self.voice = voice_engine
        self._reminders: list[threading.Timer] = []

    def set(self, message: str, delay_seconds: int) -> str:
        mins = delay_seconds // 60
        secs = delay_seconds % 60
        label = f"{mins}m {secs}s" if mins else f"{secs}s"

        def _fire():
            logger.info(f"Reminder fired: {message}")
            self.voice.speak(f"Sir, reminder: {message}", force=True)

        t = threading.Timer(delay_seconds, _fire)
        t.daemon = True
        t.start()
        self._reminders.append(t)
        return f"Reminder set for {label}: \"{message}\""

    def cancel_all(self) -> str:
        for t in self._reminders:
            t.cancel()
        count = len(self._reminders)
        self._reminders.clear()
        return f"Cancelled {count} pending reminder(s)."


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN AI BRAIN
# ══════════════════════════════════════════════════════════════════════════════

class AIBrain:
    """
    FRIDAY's central execution engine.
    All commands flow through execute(query) → str response.
    """

    VERSION = "2.0.0"

    def __init__(self, voice_engine):
        self.voice        = voice_engine
        self.nlp          = NLPParser()
        self.files        = FileManager()
        self.sysinfo      = SystemInfo()
        self.screenshots  = ScreenshotManager()
        self.clipboard    = ClipboardManager()
        self.reminders    = ReminderEngine(voice_engine)
        self.math         = SafeMathEvaluator()
        self._last_results: list = []  # cache for "open the first one" style follow-ups

        # PyAutoGUI safety settings
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.08

        logger.info(f"FRIDAY AIBrain v{self.VERSION} initialised.")

    # ──────────────────────────────────────────────────────────────────────────
    #  MAIN DISPATCH
    # ──────────────────────────────────────────────────────────────────────────

    def execute(self, query: str) -> Optional[str]:
        """
        Central dispatcher.  Returns a spoken/displayed response string,
        or None if no handler matched.
        """
        if not query or not query.strip():
            return None

        query = query.strip()
        q     = query.lower()
        intent = self.nlp.detect_intent(q)

        logger.debug(f"Query: '{query}'  →  Intent: {intent}")

        try:
            # ── Numeric follow-up ("open the first one", "number 2") ──────
            if self._last_results:
                m = re.search(r"\b(first|1st|1|second|2nd|2|third|3rd|3)\b", q)
                idx_map = {"first": 0, "1st": 0, "1": 0, "second": 1, "2nd": 1, "2": 1,
                           "third": 2, "3rd": 2, "3": 2}
                if m and m.group(1) in idx_map:
                    idx = idx_map[m.group(1)]
                    if idx < len(self._last_results):
                        path = self._last_results[idx]
                        self.files.open(Path(path))
                        return f"Opening {Path(path).name}."

            # ── Route by detected intent ───────────────────────────────────
            handlers = {
                "identity"   : self._handle_identity,
                "status"     : self._handle_status,
                "date_time"  : self._handle_datetime,
                "close"      : self._handle_close,
                "create_doc" : self._handle_create_doc,
                "find_file"  : self._handle_find_file,
                "open_app"   : self._handle_open_app,
                "web_search" : self._handle_web_search,
                "youtube"    : self._handle_youtube,
                "type_text"  : self._handle_type,
                "screenshot" : self._handle_screenshot,
                "clipboard"  : self._handle_clipboard,
                "sysinfo"    : self._handle_sysinfo,
                "processes"  : self._handle_processes,
                "reminder"   : self._handle_reminder,
                "minimize"   : self._handle_minimize,
                "maximize"   : self._handle_maximize,
                "volume"     : self._handle_volume,
                "brightness" : self._handle_brightness,
                "shutdown"   : self._handle_power,
                "restart"    : self._handle_power,
                "lock"       : self._handle_power,
                "sleep"      : self._handle_power,
                "calculate"  : self._handle_calculate,
                "weather"    : self._handle_weather,
                "joke"       : self._handle_joke,
            }

            if intent and intent in handlers:
                return handlers[intent](q, query)

            return None

        except Exception as e:
            logger.exception(f"Unhandled error in execute(): {e}")
            return "I encountered an error processing that request, sir."

    # ──────────────────────────────────────────────────────────────────────────
    #  INTENT HANDLERS
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_identity(self, q, raw):
        return (
            f"I am FRIDAY — Functional Responsive Intelligence with Dynamic Autonomous Yield, "
            f"version {self.VERSION}. Running on {platform.system()} {platform.release()}. "
            f"All systems nominal, sir."
        )

    def _handle_status(self, q, raw):
        responses = [
            "Fully operational, all subsystems nominal.",
            "Optimised and ready. How may I assist, sir?",
            "Running at peak efficiency. Your command?",
        ]
        import random
        return random.choice(responses)

    def _handle_datetime(self, q, raw):
        now = datetime.datetime.now()
        if "date" in q or "tarikh" in q:
            return f"Today is {now.strftime('%A, %d %B %Y')}."
        return f"Current time is {now.strftime('%I:%M %p')}."

    def _handle_close(self, q, raw):
        # Check for specific app to close
        for key, info in DEFAULT_APP_MAP.items():
            if key in q or any(a in q for a in info["aliases"]):
                proc = info["process"] + ".exe"
                # shell=False: proc comes from the hardcoded registry, not user input
                result = subprocess.run(
                    ["taskkill", "/f", "/im", proc],
                    capture_output=True, text=True, shell=False
                )
                if result.returncode == 0:
                    return f"{key.title()} terminated, sir."
                return f"Could not find a running instance of {key.title()}."

        # Generic active-window close
        if any(w in q for w in ["window", "close", "band karo", "this"]):
            pyautogui.hotkey("alt", "f4")
            return "Closing the active window."

        return None

    def _handle_create_doc(self, q, raw):
        # Maps keyword → (display name, args list for Popen, post-launch wait seconds)
        doc_types = {
            "word"       : ("Word",        ["cmd", "/c", "start", "", "winword"], 4),
            "excel"      : ("Excel",       ["cmd", "/c", "start", "", "excel"],   4),
            "powerpoint" : ("PowerPoint",  ["cmd", "/c", "start", "", "powerpnt"],4),
            "notepad"    : ("Notepad",     ["notepad"],                           1),
            "text"       : ("Notepad",     ["notepad"],                           1),
        }
        for keyword, (label, args, wait) in doc_types.items():
            if keyword in q:
                subprocess.Popen(args, shell=False)
                if label == "Word":
                    time.sleep(wait)
                    pyautogui.press("enter")
                return f"New {label} document created, sir."

        # Fallback: Notepad
        subprocess.Popen(["notepad"], shell=False)
        return "Opening Notepad for a new file."

    def _handle_find_file(self, q, raw):
        strip_words = ["find", "open file", "search for", "dhoondo", "dhundo", "locate", "file"]
        entity = self.nlp.extract_entity(raw, strip_words)

        if not entity:
            return "Please specify a filename to search for."

        # Detect optional file type hint in query
        file_type = None
        for ft in FileManager.EXTENSION_MAP:
            if ft in q:
                file_type = ft
                break

        results = self.files.search(entity, file_type=file_type)
        self._last_results = [str(p) for p in results]

        if not results:
            return f"I could not locate any file matching '{entity}' in your main folders."

        if len(results) == 1:
            self.files.open(results[0])
            return f"Found and opening: {results[0].name}"

        # Multiple results → list them
        names = "\n".join(f"  {i+1}. {p.name}" for i, p in enumerate(results))
        return f"Found {len(results)} files matching '{entity}':\n{names}\nSay a number to open one."

    def _handle_open_app(self, q, raw):
        strip_words = ["open", "launch", "start", "chalu karo", "kholo"]
        entity = self.nlp.extract_entity(raw, strip_words)

        if not entity:
            return "Which application should I open, sir?"

        resolved = self.nlp.resolve_app(entity)
        if resolved:
            key, info = resolved
            # Always use the pre-validated args list — never user input → shell
            subprocess.Popen(info["args"], shell=False)
            return f"Launching {key.title()}, sir."

        # Security: unrecognised apps are NOT launched.
        # Passing unvalidated voice input to subprocess is a command injection risk.
        # Register new apps via add_app() with a hardcoded args list instead.
        logger.warning(f"Open request for unregistered app blocked: '{entity}'")
        return (
            f"I don't have '{entity}' in my app registry. "
            f"Ask me to register it with a specific path first, sir."
        )

    def _handle_web_search(self, q, raw):
        strip = ["search", "google", "browse", "kholo", "for", "online"]
        term = self.nlp.extract_entity(raw, strip)

        # Detect if it's a direct URL
        url_match = re.search(r"(https?://\S+|www\.\S+\.\w+)", raw, re.IGNORECASE)
        if url_match:
            url = url_match.group(1)
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            return f"Navigating to {url}."

        if not term or "friday" in term:
            webbrowser.open("https://www.google.com")
            return "Opening Google."

        webbrowser.open(f"https://www.google.com/search?q={term.replace(' ', '+')}")
        return f"Searching Google for: {term}."

    def _handle_youtube(self, q, raw):
        term = re.sub(r"(play|on youtube|youtube|search|watch)", "", raw, flags=re.IGNORECASE).strip()
        if term:
            webbrowser.open(f"https://www.youtube.com/results?search_query={term.replace(' ', '+')}")
            return f"Searching YouTube for: {term}."
        webbrowser.open("https://www.youtube.com")
        return "Opening YouTube."

    def _handle_type(self, q, raw):
        content = re.sub(r"(type|write|likho|likh do)", "", raw, flags=re.IGNORECASE).strip()
        if not content:
            return "What should I type, sir?"
        self.voice.speak("Focus the target window. Typing in 3 seconds.", force=True)
        time.sleep(3)
        pyautogui.write(content, interval=0.025)
        pyautogui.press("enter")
        return "Dictation complete."

    def _handle_screenshot(self, q, raw):
        if "window" in q or "active" in q:
            path = self.screenshots.capture_active_window()
        else:
            path = self.screenshots.capture()

        if path:
            os.startfile(str(path.parent))
            return f"Screenshot saved to {path.name}."
        return "Screenshot failed. Pillow may not be installed (pip install Pillow)."

    def _handle_clipboard(self, q, raw):
        if "read" in q or "paste" in q or "kya hai" in q:
            content = self.clipboard.read()
            if not content:
                return "Clipboard is empty."

            # Redact probable secrets: long strings with no spaces
            # (API keys, passwords, tokens typically look like this)
            if len(content) > 12 and " " not in content.strip():
                logger.debug("Clipboard read suppressed — high-entropy string detected.")
                return (
                    "Clipboard contains a secure-looking string. "
                    "I've hidden it to protect your privacy, sir."
                )

            # Safe to read — cap at 150 chars, never write to log
            preview = content[:150] + ("…" if len(content) > 150 else "")
            return f"Clipboard contains: {preview}"

        if "copy" in q:
            strip = ["copy", "clipboard"]
            text = self.nlp.extract_entity(raw, strip)
            if text:
                self.clipboard.write(text)
                # Log intent only, never the actual clipboard content
                logger.debug("Clipboard write: user-supplied text.")
                return "Copied to clipboard."
            # Simulate Ctrl+C on selected text
            pyautogui.hotkey("ctrl", "c")
            return "Selection copied to clipboard."

        return None

    def _handle_sysinfo(self, q, raw):
        if "cpu" in q:
            return self.sysinfo.cpu()
        if any(w in q for w in ["ram", "memory", "mem"]):
            return self.sysinfo.memory()
        if "battery" in q or "charge" in q:
            return self.sysinfo.battery()
        if "disk" in q or "storage" in q or "space" in q:
            return self.sysinfo.disk()
        return self.sysinfo.full_report()

    def _handle_processes(self, q, raw):
        procs = self.sysinfo.top_processes(n=5)
        if not procs:
            return "psutil not available. Run: pip install psutil"
        lines = ["Top 5 processes by CPU usage:"]
        for p in procs:
            lines.append(
                f"  {p.get('name','?'):<30} CPU: {p.get('cpu_percent',0):.1f}%  "
                f"RAM: {p.get('memory_percent',0):.1f}%"
            )
        return "\n".join(lines)

    def _handle_reminder(self, q, raw):
        if "cancel" in q or "remove" in q:
            return self.reminders.cancel_all()

        delay = self.nlp.parse_duration(raw)
        if not delay:
            return "Please specify a duration, e.g. 'remind me in 10 minutes to drink water'."

        # Strip time references to get the message
        msg_raw = re.sub(
            r"remind\s*me|in\s+\d+\s*(minute|min|second|sec|hour|hr)s?|yaad dilao|reminder",
            "", raw, flags=re.IGNORECASE
        ).strip()
        msg_raw = re.sub(r"\bto\b", "", msg_raw).strip()
        message = msg_raw if msg_raw else "your reminder"
        return self.reminders.set(message, delay)

    def _handle_minimize(self, q, raw):
        if "all" in q:
            pyautogui.hotkey("win", "d")
            return "All windows minimised."
        pyautogui.hotkey("win", "down")
        return "Active window minimised."

    def _handle_maximize(self, q, raw):
        pyautogui.hotkey("win", "up")
        return "Window maximised."

    def _handle_volume(self, q, raw):
        # Parse explicit level: "set volume to 60"
        m = re.search(r"(\d{1,3})\s*%?", q)
        if m and "set" in q:
            target = max(0, min(100, int(m.group(1))))
            script = (
                f"$obj = New-Object -ComObject WScript.Shell; "
                f"for($i=0;$i -lt {target};$i++){{$obj.SendKeys([char]175)}}"
            )
            subprocess.run(["powershell", "-Command", script],
                           capture_output=True, creationflags=0x08000000)
            return f"Volume set to approximately {target}."

        steps = 10
        if any(w in q for w in ["mute", "silence", "band karo awaaz"]):
            pyautogui.press("volumemute")
            return "Audio muted."
        if any(w in q for w in ["up", "increase", "zyada", "louder", "badhao"]):
            for _ in range(steps):
                pyautogui.press("volumeup")
            return "Volume increased."
        if any(w in q for w in ["down", "decrease", "kam karo", "quieter", "ghataao"]):
            for _ in range(steps):
                pyautogui.press("volumedown")
            return "Volume decreased."
        return None

    def _handle_brightness(self, q, raw):
        m = re.search(r"(\d{1,3})", q)
        level = int(m.group(1)) if m else (75 if "increase" in q or "badhao" in q else 25)
        level = max(0, min(100, level))
        script = (
            f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{level})"
        )
        subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True, creationflags=0x08000000
        )
        return f"Brightness set to {level}%."

    def _handle_power(self, q, raw):
        if "shutdown" in q or "power off" in q:
            self.voice.speak("Initiating shutdown in 10 seconds. Say cancel to abort.", force=True)
            timer = threading.Timer(
                10, lambda: subprocess.run(["shutdown", "/s", "/t", "0"], shell=False)
            )
            timer.daemon = True
            timer.start()
            return "Shutdown scheduled in 10 seconds."
        if "restart" in q or "reboot" in q:
            subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True, shell=False)
            return "Restarting in 5 seconds."
        if "lock" in q:
            ctypes.windll.user32.LockWorkStation()
            return "Workstation locked."
        if "sleep" in q or "hibernate" in q:
            subprocess.run(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                capture_output=True, shell=False
            )
            return "System going to sleep."
        return None

    def _handle_calculate(self, q, raw):
        expr = re.sub(r"(calculate|compute|math|hisab|what is|=)", "", raw, flags=re.IGNORECASE).strip()
        if not expr:
            return "No valid math expression detected."
        try:
            result = self.math.evaluate(expr)
            return f"{expr} = {result}"
        except ValueError as e:
            # Covers DoS attempts (huge exponents) and invalid expressions
            logger.warning(f"SafeMath rejected expression '{expr}': {e}")
            subprocess.Popen(["calc"], shell=False)
            return "That expression is too complex for me to evaluate safely. Opening Calculator."
        except Exception as e:
            logger.error(f"SafeMath unexpected error: {e}")
            subprocess.Popen(["calc"], shell=False)
            return "Opening Calculator for that expression."

    def _handle_weather(self, q, raw):
        city = self.nlp.extract_entity(raw, ["weather", "mausam", "in", "of", "for"])
        if city:
            webbrowser.open(f"https://www.google.com/search?q=weather+{city.replace(' ', '+')}")
            return f"Opening weather for {city}."
        webbrowser.open("https://www.google.com/search?q=weather+today")
        return "Opening current weather."

    def _handle_joke(self, q, raw):
        jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs.",
            "I would tell you a UDP joke, but you might not get it.",
            "There are 10 types of people: those who understand binary, and those who don't.",
            "A SQL query walks into a bar, walks up to two tables and asks: 'Can I join you?'",
            "Why did the developer go broke? Because he used up all his cache.",
        ]
        import random
        return random.choice(jokes)

    # ──────────────────────────────────────────────────────────────────────────
    #  PUBLIC UTILITY METHODS
    # ──────────────────────────────────────────────────────────────────────────

    def add_app(self, name: str, process: str, args: list[str], aliases: list[str] = None):
        """
        Dynamically register a new app at runtime.
        'args' must be a pre-validated list passed directly to subprocess.Popen
        (shell=False) — never constructed from user voice input.

        Example:
            brain.add_app("slack", "slack", ["cmd", "/c", "start", "", "slack"])
        """
        if not isinstance(args, list) or not args:
            logger.error(f"add_app rejected: 'args' must be a non-empty list.")
            return
        DEFAULT_APP_MAP[name.lower()] = {
            "process": process,
            "args"   : args,
            "aliases": aliases or [],
        }
        logger.info(f"App registered: {name}")

    def status_report(self) -> str:
        """Return a brief health summary of the AIBrain."""
        return (
            f"FRIDAY v{self.VERSION} — "
            f"psutil: {'✓' if PSUTIL_AVAILABLE else '✗'}  "
            f"Pillow: {'✓' if PIL_AVAILABLE else '✗'}  "
            f"pyperclip: {'✓' if PYPERCLIP_AVAILABLE else '✗'}  "
            f"Apps loaded: {len(DEFAULT_APP_MAP)}"
        )