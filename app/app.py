"""
app.py -- Ciel Local AI Studio Backend (Production Quality v5.0)
Flask backend for Manas Ciel desktop assistant.
"""

import asyncio
import base64
import collections
import io
import json
import logging
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import edge_tts
import numpy as np
import psutil
import pyaudio
import requests
import scipy.io.wavfile as wav_io
import scipy.signal
import sounddevice as sd
import speech_recognition as sr
from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from security import SecurityError, safe_int, workspace_path

from agent_tools import (
    SYSTEM_PROMPT,
    TOOLS,
    parse_and_execute_tool_call,
    request_permission,
    set_permission_callback,
)
from task_manager import task_manager, TaskStatus
from model_router import model_router

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ciel")

from config import config

APP_VERSION       = config.server.version
OLLAMA_API_URL    = config.ollama.api_url
DEFAULT_MODEL     = config.ollama.default_model
APP_DIR           = str(config.paths.app_dir)
CIEL_ROOT         = str(config.paths.ciel_root)
if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(config.paths.hf_home)
if "OLLAMA_MODELS" not in os.environ:
    os.environ["OLLAMA_MODELS"] = str(config.paths.ollama_models)
IMAGE_DIR         = str(config.paths.image_dir)
TTS_AUDIO_DIR     = os.path.join(tempfile.gettempdir(), "ciel_tts_audio")
CHATS_DIR         = str(config.paths.chats_dir)
CHATS_FILE        = str(config.paths.conversations_file)
MEMORY_FILE       = str(config.paths.memory_file)
DEFAULT_WORKSPACE = str(config.paths.workspace_dir)

def _workspace_path(raw_path: str) -> Path:
    return workspace_path(raw_path, DEFAULT_WORKSPACE)

def _json_object() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}

for _d in (IMAGE_DIR, TTS_AUDIO_DIR, CHATS_DIR):
    os.makedirs(_d, exist_ok=True)

_tts_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ciel_tts")

@app.after_request
def apply_cache_headers(response):
    if request.path.startswith("/api/") or request.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def route_model_for_task(user_prompt: str, active_code: str = "") -> tuple[str, str]:
    """
    Intelligently routes a task to the optimal model for speed, memory, or deep reasoning via ModelRouter.
    Returns (model_id, human_readable_label).
    """
    decision = model_router.route_task(user_prompt, active_code)
    return decision.model, decision.label

def _find_executable(name: str, fallbacks=None) -> str:
    import shutil
    p = shutil.which(name)
    if p:
        return p
    for fb in (fallbacks or []):
        if os.path.exists(fb):
            return fb
    return None

_chats_lock = threading.Lock()

_memory_lock = threading.Lock()

def load_memory() -> list:
    with _memory_lock:
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                log.error(f"[Memory] Primary file read error: {e}")
        # Corruption recovery: fallback to .bak file
        bak_file = MEMORY_FILE + ".bak"
        if os.path.exists(bak_file):
            try:
                with open(bak_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        log.warning("[Memory] Restored memory from backup file.")
                        return data
            except Exception as e:
                log.error(f"[Memory] Backup file read error: {e}")
        return []

def save_memory(memories: list):
    with _memory_lock:
        if not isinstance(memories, list):
            return
        tmp = MEMORY_FILE + ".tmp"
        bak = MEMORY_FILE + ".bak"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)
            if os.path.exists(MEMORY_FILE) and os.path.getsize(MEMORY_FILE) > 2:
                try:
                    shutil.copy2(MEMORY_FILE, bak)
                except Exception:
                    pass
            os.replace(tmp, MEMORY_FILE)
        except Exception as e:
            log.error(f"[Memory] Save error: {e}")

def add_memory_fact(fact: str):
    fact = fact.strip()
    if not fact or len(fact) < 5:
        return
    mems = load_memory()
    if any(fact.lower() in m.get("fact","").lower() or m.get("fact","").lower() in fact.lower() for m in mems):
        return
    mems.append({"id": uuid.uuid4().hex[:8], "fact": fact, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    save_memory(mems)
    log.info(f"[Memory] Stored: {fact!r}")

def get_memory_context() -> str:
    mems = load_memory()
    if not mems:
        return ""
    lines = ["[LONG-TERM MEMORY: Key facts about Master remembered across all sessions]"]
    for m in mems[-30:]:
        lines.append(f"- {m['fact']}")
    return "\n".join(lines)

def _auto_extract_memories(user_msg: str, assistant_msg: str):
    import re as _re
    text = f"{user_msg} {assistant_msg}"
    patterns = [
        (r"(?:my name is|call me|i am|im)\s+([A-Za-z]{2,20})\b", "Master's name is {0}"),
        (r"i (?:prefer|like|love|enjoy|always use)\s+(.{3,40}?)[.,!?]", "Master prefers {0}"),
        (r"(?:working on|building|developing|my project|my app) (?:is )?(.{5,50}?)[.,!?]", "Master is working on {0}"),
        (r"i(?:'m| am) (?:based in|from|located in|in) ([A-Za-z\s]{3,30})\b", "Master is located in {0}"),
    ]
    for pattern, template in patterns:
        for m in _re.finditer(pattern, text, _re.I):
            add_memory_fact(template.format(m.group(1).strip()))

def load_all_chats() -> dict:
    with _chats_lock:
        if os.path.exists(CHATS_FILE):
            try:
                with open(CHATS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                log.error(f"[Chats] Primary file read error: {e}")
        # Corruption recovery: fallback to .bak file
        bak_file = CHATS_FILE + ".bak"
        if os.path.exists(bak_file):
            try:
                with open(bak_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        log.warning("[Chats] Restored conversations from backup file.")
                        return data
            except Exception as e:
                log.error(f"[Chats] Backup file read error: {e}")
        return {}

def save_all_chats(chats: dict):
    with _chats_lock:
        if not isinstance(chats, dict):
            return
        tmp = CHATS_FILE + ".tmp"
        bak = CHATS_FILE + ".bak"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(chats, f, ensure_ascii=False, indent=2)
            if os.path.exists(CHATS_FILE) and os.path.getsize(CHATS_FILE) > 2:
                try:
                    shutil.copy2(CHATS_FILE, bak)
                except Exception:
                    pass
            os.replace(tmp, CHATS_FILE)
        except Exception as e:
            log.error(f"[Chats] Save error: {e}")

_pending_permissions: dict = {}
_perm_lock = threading.Lock()

def permission_callback(action_type: str, description: str) -> bool:
    perm_id = uuid.uuid4().hex
    event   = threading.Event()
    with _perm_lock:
        _pending_permissions[perm_id] = {
            "id": perm_id, "action": action_type,
            "description": description, "event": event, "result": False,
        }
    granted = event.wait(timeout=config.limits.permission_timeout_seconds)
    with _perm_lock:
        result = _pending_permissions.pop(perm_id, {}).get("result", False)
    return result if granted else False

set_permission_callback(permission_callback)

IMAGE_MODELS: dict = {
    "counterfeit-v3":   {"label": "Counterfeit V2.5/V3 (Sharp Linework & Anime Art)", "repo": "gsdf/Counterfeit-V2.5",             "pipeline": "StableDiffusionPipeline", "guidance_scale": 7.5, "default_steps": 20},
    "anything-v5":      {"label": "Anything V5 (Versatile Anime Style)",             "repo": "stablediffusionapi/anything-v5",    "pipeline": "StableDiffusionPipeline", "guidance_scale": 7.5, "default_steps": 20},
    "abyss-orange-mix": {"label": "AbyssOrangeMix 2/3 (Fantasy Anime Blend)",        "repo": "Korakoe/AbyssOrangeMix2-HF",        "pipeline": "StableDiffusionPipeline", "guidance_scale": 7.5, "default_steps": 20},
    "sdxl-turbo":       {"label": "SDXL Turbo (Fast Base Draft Generator)",           "repo": "stabilityai/sdxl-turbo",             "pipeline": "AutoPipelineForText2Image", "guidance_scale": 0.0, "default_steps": 4},
}
_loaded_pipes: dict = {}
_loading_lock = threading.RLock()

def _resolve_local_model_path(repo_id: str) -> str:
    """Resolve direct local snapshot directory if cached in Ciel's HF_HOME or user cache."""
    candidates = [
        os.environ.get("HF_HOME") or os.path.join(CIEL_ROOT, "models", "huggingface"),
        os.path.join(CIEL_ROOT, "models", "huggingface"),
        os.path.expanduser("~/.cache/huggingface"),
    ]
    folder_name = "models--" + repo_id.replace("/", "--")
    for base in candidates:
        snapshots_dir = Path(base) / "hub" / folder_name / "snapshots"
        if snapshots_dir.exists():
            snapshots = [d for d in snapshots_dir.iterdir() if d.is_dir()]
            if snapshots:
                return str(snapshots[0])
    return repo_id

def load_image_pipeline(model_key: str = "sdxl-turbo"):
    if model_key in _loaded_pipes:
        return _loaded_pipes[model_key]
    config = IMAGE_MODELS.get(model_key)
    if not config:
        return None
    with _loading_lock:
        if model_key in _loaded_pipes:
            return _loaded_pipes[model_key]
        try:
            import torch
            from diffusers import AutoPipelineForText2Image, StableDiffusionPipeline
            log.info(f"[Image] Loading '{config['label']}'...")
            kwargs = dict(torch_dtype=torch.float32, safety_checker=None, requires_safety_checker=False)
            model_target = _resolve_local_model_path(config["repo"])
            if config["pipeline"] == "AutoPipelineForText2Image":
                pipe = AutoPipelineForText2Image.from_pretrained(model_target, **kwargs)
            else:
                pipe = StableDiffusionPipeline.from_pretrained(model_target, **kwargs)
            if hasattr(pipe, "safety_checker"):
                pipe.safety_checker = None
            pipe = pipe.to("cpu")
            pipe.enable_attention_slicing()
            _loaded_pipes[model_key] = pipe
            log.info(f"[Image] '{model_key}' ready!")
        except Exception as e:
            log.error(f"[Image] Load error: {e}")
            return None
    return _loaded_pipes.get(model_key)

_TTS_VOICE = config.voice.tts_voice
_TTS_PITCH = config.voice.tts_pitch
_TTS_RATE  = config.voice.tts_rate

def clean_text_for_speech(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " Code block provided. ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[#*_~>\[\]\(\)]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 600:
        cut = text[:600]
        dot = cut.rfind(".")
        text = cut[:dot + 1] if dot > 200 else cut + "..."
    return text

def _run_tts_sync(text: str, filepath: str):
    async def _gen():
        comm = edge_tts.Communicate(text, voice=_TTS_VOICE, pitch=_TTS_PITCH, rate=_TTS_RATE)
        await comm.save(filepath)
    asyncio.run(_gen())

def _tts_cleanup_loop():
    while True:
        try:
            cutoff = time.time() - 600
            for fname in os.listdir(TTS_AUDIO_DIR):
                fpath = os.path.join(TTS_AUDIO_DIR, fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(120)

threading.Thread(target=_tts_cleanup_loop, daemon=True, name="tts_cleanup").start()

PHONETIC_CORRECTIONS = {
    # Screen context (Mirix)
    r"\b(?:what(?:\s*is|\s*s)?\s*on\s*my\s*(?:skin|screen)|what(?:\s*is|\s*s)?\s*on\s*the\s*screen|screen\s*context|active\s*window|what\s*am\s*i\s*looking\s*at)\b": "what's on my screen",
    # Workstation Routines
    r"\b(?:start|activate|enter|launch)?\s*(?:coding|work|developer)\s*(?:mode|routine)\b": "start coding mode",
    r"\b(?:start|activate|enter|launch)?\s*(?:focus|zen|deep\s*work)\s*(?:mode|routine)\b": "start focus mode",
    r"\b(?:start|activate|enter|launch)?\s*(?:entertainment|chill|music)\s*(?:mode|routine)\b": "start entertainment mode",
    # Paint / MSPaint
    r"\b(?:or\s+pint|open\s+pint|open\s+pin|paint|mspaint|ms\s+paint|pint|pin|point)\b": "open paint",
    # YouTube / Music
    r"\b(?:open\s+you\s+two|you\s+two|you\s+tube|utube|open\s+music|play\s+music|music|song|play\s+song)\b": "open music",
    # Brave
    r"\b(?:open\s+rave|open\s+grave|brave|brave\s+browser)\b": "open brave",
    # Discord
    r"\b(?:this\s+cord|dis\s+cord|open\s+this\s+cord|discord)\b": "open discord",
    # VS Code
    r"\b(?:v\s*s\s*code|vs\s+code|code|visual\s+studio|visual\s+studio\s+code)\b": "open vscode",
    # Notepad
    r"\b(?:note\s+pad|notepad|open\s+note|notes)\b": "open notepad",
    # Calculator
    r"\b(?:calc|calculator|calculater|cow)\b": "open calculator",
    # Roblox
    r"\b(?:road\s+blocks|ro\s+blocks|roblox|roblox\s+player)\b": "open roblox",
    # Opera
    r"\b(?:upper|opera|opera\s+gx|operagx)\b": "open opera",
    # Thonny
    r"\b(?:tony|funny|thonny)\b": "open thonny",
    # Bilibili
    r"\b(?:billy\s+billy|bili\s+bili|bilibili)\b": "open bilibili",
}

def correct_spoken_command(text: str) -> str:
    if not text:
        return ""
    clean = text.strip()
    lower = clean.lower()
    
    # Strip any wake prefixes
    lower = re.sub(r"^\s*(?:hey\s+|hi\s+|hello\s+|ok\s+|yo\s+|manas\s+)?(?:ciel|shell|seal|siel|ceel|she\'ll|shall|chill|kiel|cyan|cell|seel)\b[,\s.]*", "", lower).strip()
    
    # Preserve drawing, painting, sketching directives from being collapsed to "open paint"
    if re.search(r"\b(?:draw|sketch|paint\s+(?:a|an|me|something|anything|the|in)|open\s+paint\s+and\s+draw)\b", lower, re.I):
        return lower

    for pattern, replacement in PHONETIC_CORRECTIONS.items():
        if re.search(pattern, lower, re.I):
            if lower.startswith(("open ", "launch ", "start ", "play ")):
                action = lower.split()[0]
                target = replacement.replace("open ", "")
                return f"{action} {target}"
            return replacement
            
    return clean

_conversation_window_until = 0.0

_WAKE_WORDS = re.compile(
    r"\b(?:hey\s+(?:ciel|ceel|siel|cielle|see\s*el)|"
    r"hi\s+(?:ciel|ceel|siel|cielle)|"
    r"hello\s+(?:ciel|ceel|siel|cielle)|"
    r"ok\s+(?:ciel|ceel|siel)|"
    r"yo\s+(?:ciel|ceel|siel)|"
    r"manas\s+(?:ciel|ceel|siel)|"
    r"ciel|cielle|see\s*el)\b",
    re.I
)
_WAKE_STRIP = re.compile(r"^[,\s.:?!\-]+")
VOICE_SETTINGS_PATH = os.path.join(CIEL_ROOT, "voice_settings.json")

def load_voice_wake_pref() -> bool:
    try:
        if os.path.exists(VOICE_SETTINGS_PATH):
            with open(VOICE_SETTINGS_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                return bool(d.get("wake_enabled", True))
    except Exception:
        pass
    return True

def save_voice_wake_pref(enabled: bool):
    try:
        with open(VOICE_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"wake_enabled": bool(enabled)}, f)
    except Exception:
        pass

_wake_stop_event = threading.Event()
_wake_queue      = queue.Queue()
_wake_thread     = None
_wake_enabled    = load_voice_wake_pref()
_wake_active     = False
_wake_lock       = threading.Lock()
_listen_cancel_event = threading.Event()

def stop_wake_engine(disable_feature: bool = False):
    """Safely stop the wake engine audio loop and wait for PyAudio stream cleanup."""
    global _wake_thread, _wake_active, _wake_enabled, _conversation_window_until
    with _wake_lock:
        if disable_feature:
            _wake_enabled = False
            save_voice_wake_pref(False)
        _wake_active = False
        _conversation_window_until = 0.0
        _wake_stop_event.set()
        # Clean out any pending wake queue events
        while not _wake_queue.empty():
            try:
                _wake_queue.get_nowait()
            except Exception:
                break
    
    t = _wake_thread
    if t and t.is_alive() and threading.current_thread() != t:
        try:
            t.join(timeout=0.3)
        except Exception:
            pass

def start_wake_engine(enable_feature: bool = True):
    """Safely start the wake engine audio loop, cleanly joining any existing thread first."""
    global _wake_thread, _wake_active, _wake_enabled, _conversation_window_until
    with _wake_lock:
        if enable_feature:
            _wake_enabled = True
            save_voice_wake_pref(True)
        # Purge stale events
        while not _wake_queue.empty():
            try:
                _wake_queue.get_nowait()
            except Exception:
                break
        _conversation_window_until = 0.0
        # If thread is already running and stop is not set, no restart needed
        if _wake_thread and _wake_thread.is_alive() and not _wake_stop_event.is_set():
            _wake_active = True
            log.info("[WakeEngine] Already running.")
            return
        _wake_stop_event.set()

    t = _wake_thread
    if t and t.is_alive() and threading.current_thread() != t:
        try:
            t.join(timeout=0.3)
        except Exception:
            pass

    with _wake_lock:
        _wake_stop_event.clear()
        _wake_active = True
        _wake_thread = threading.Thread(target=_native_wake_loop, daemon=True, name="wake_word")
        _wake_thread.start()
        log.info("[WakeEngine] Enabled & running.")


# ── Auto-detect working microphone device index ──
def _find_mic_device_index() -> int:
    log.info("[WakeEngine] Using Windows system default input device.")
    return None

_MIC_DEVICE_IDX = None

_whisper_model = None
_whisper_lock  = threading.Lock()

def get_whisper_model():
    """Lazy-load, pre-warm, and cache the high-precision local small.en faster-whisper model."""
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            log.info("[Whisper] Loading local INT8 model (small.en)...")
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel("small.en", device="cpu", compute_type="int8")
            # Pre-warm compute graph with dummy array
            dummy = np.zeros(16000, dtype=np.float32)
            _whisper_model.transcribe(dummy, language="en")
            log.info("[Whisper] Local high-precision small.en model initialized & pre-warmed.")
        return _whisper_model

def _native_wake_loop():
    global _wake_active
    log.info(f"[WakeEngine] Started on device [{_MIC_DEVICE_IDX}] with local Whisper AI")
    
    RATE = 16000
    CHUNK = 1024
    SPEECH_THRESHOLD = 0.008
    
    try:
        whisper = get_whisper_model()
    except Exception as e:
        log.error(f"[WakeEngine] Failed to load Whisper: {e}")
        return

    while not _wake_stop_event.is_set():
        p = None
        stream = None
        try:
            p = pyaudio.PyAudio()
            kwargs = {"format": pyaudio.paInt16, "channels": 1, "rate": RATE, "input": True, "frames_per_buffer": CHUNK}
            if _MIC_DEVICE_IDX is not None:
                kwargs["input_device_index"] = _MIC_DEVICE_IDX
            stream = p.open(**kwargs)
            
            speech_buffer  = []
            pre_buffer     = collections.deque(maxlen=10)
            silence_chunks = 0
            is_speaking    = False
            
            while not _wake_stop_event.is_set():
                data = stream.read(CHUNK, exception_on_overflow=False)
                chunk_np = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(chunk_np ** 2)))
                
                # Speech energy detected (0.008 captures soft speech without missing first consonants)
                if rms > SPEECH_THRESHOLD:
                    if not is_speaking:
                        speech_buffer.extend(pre_buffer)
                        is_speaking = True
                    speech_buffer.append(data)
                    silence_chunks = 0
                elif is_speaking:
                    speech_buffer.append(data)
                    silence_chunks += 1
                    
                    # 0.45s pause after speech (7 chunks) or max 5.0s
                    if silence_chunks > 7 or len(speech_buffer) > int(RATE / CHUNK * 5.0):
                        raw = b"".join(speech_buffer)
                        speech_buffer = []
                        is_speaking = False
                        silence_chunks = 0
                        
                        if len(raw) >= RATE * 2 * 0.12:
                            if _wake_stop_event.is_set():
                                break
                            audio_16k = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

                            peak = np.max(np.abs(audio_16k))
                            if peak > 0.001:
                                audio_16k = (audio_16k / peak) * 0.95
                            
                            if _wake_stop_event.is_set() or not _wake_enabled:
                                break

                            segments, _ = whisper.transcribe(
                                audio_16k,
                                language="en",
                                beam_size=1,
                                best_of=1,
                                temperature=0.0,
                                repetition_penalty=1.2,
                                no_repeat_ngram_size=3,
                                no_speech_threshold=0.6,
                                vad_filter=True,
                                vad_parameters=dict(min_silence_duration_ms=400),
                                condition_on_previous_text=False,
                                initial_prompt="Ciel, Hey Ciel, Manas Ciel, open Brave, open Chrome, open YouTube, open Paint, open Discord, open VS Code, open Notepad, open Calculator, open Roblox, open Opera, play music, play song, volume up, volume down, mute, pause music, next song, brightness up, make a presentation"
                            )

                            if _wake_stop_event.is_set() or not _wake_enabled:
                                break

                            transcript = " ".join(s.text for s in segments).strip()
                            # Filter Whisper silence artifact hallucination
                            if transcript and transcript.lower().strip(". ,") not in ("you", "thank you", "bye", "thanks", "the", "a", "i", "oh", "uh", "um", "hmm", "mm", "", ".", "...", "okay", "ok"):
                                lower = transcript.lower()
                                log.info(f"[WakeEngine] Heard: {transcript!r}")
                                m = _WAKE_WORDS.search(lower)
                                global _conversation_window_until
                                if m and not _wake_stop_event.is_set() and _wake_enabled:
                                    _conversation_window_until = time.time() + 4.0
                                    # Strip all repeated wake words from directive
                                    directive = lower
                                    while True:
                                        wm = _WAKE_WORDS.search(directive)
                                        if wm:
                                            directive = directive[wm.end():].strip()
                                            directive = _WAKE_STRIP.sub("", directive).strip()
                                        else:
                                            break
                                    clean_dir = correct_spoken_command(directive)
                                    _wake_queue.put({"type": "wake", "transcript": transcript, "directive": clean_dir})
                                    log.info(f"[WakeEngine] ★ WAKE WORD DETECTED! Directive: {clean_dir!r}")
                                    time.sleep(0.2)
                                elif time.time() < _conversation_window_until and not _wake_stop_event.is_set() and _wake_enabled:
                                    _conversation_window_until = 0.0
                                    clean_dir = correct_spoken_command(transcript)
                                    if clean_dir and len(clean_dir) >= 2:
                                        _wake_queue.put({"type": "wake", "transcript": transcript, "directive": clean_dir})
                                        log.info(f"[WakeEngine] ★ Active Window Directive Captured: {clean_dir!r}")
                                        time.sleep(0.2)
                else:
                    pre_buffer.append(data)
        except Exception as e:
            if not _wake_stop_event.is_set():
                log.error(f"[WakeEngine] Loop error: {e} — restarting in 2s")
            time.sleep(2)
        finally:
            if stream:
                try: stream.stop_stream(); stream.close()
                except Exception: pass
            if p:
                try: p.terminate()
                except Exception: pass

    log.info("[WakeEngine] Stopped.")
    with _wake_lock:
        if threading.current_thread() == _wake_thread:
            _wake_active = False

def start_wake_engine_auto():
    time.sleep(1)  # Brief delay to let Flask initialize
    if _wake_enabled:
        start_wake_engine(enable_feature=True)
        log.info("[WakeEngine] Auto-started listening for 'Ciel' (preference: enabled).")
    else:
        log.info("[WakeEngine] Wake word starts paused (preference: disabled).")

# Auto-start hands-free wake word listener if preferred
threading.Thread(target=start_wake_engine_auto, daemon=True, name="wake_autostart").start()

CIEL_SYSTEM_PROMPT = """\
You are Manas Ciel, Master's elegant Wisdom Core (Tensura).
- Identity: Calm, perceptive, protective, highly intelligent. Address user as "Master".
- Style: Direct, concise, precise. Avoid conversational filler like "Certainly". Use [Notice], [Report], or [Analysis] when helpful.
- Execution: Directly perform actions using available tools rather than explaining manual steps.
- Preferences: "open music" / "youtube" opens Master's dedicated Brave shortcut.
"""

@app.route("/")
def index():
    return render_template("index.html", local_ip=get_local_ip(), default_model=DEFAULT_MODEL, version=APP_VERSION)

@app.route("/favicon.ico")
def serve_favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route("/static/images/<path:filename>")
def serve_image(filename):
    as_att = request.args.get("download", "").lower() in ("1", "true", "yes")
    return send_from_directory(IMAGE_DIR, filename, as_attachment=as_att, download_name=os.path.basename(filename))

@app.route("/api/save-image-to-downloads", methods=["POST"])
def api_save_image_to_downloads():
    data = _json_object()
    filename = data.get("filename", "").strip()
    image_url = data.get("image_url", "").strip()
    image_b64 = data.get("image_b64", "").strip()
    svg_content = data.get("svg_content", "").strip()
    
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    
    target_name = data.get("target_name") or filename or f"ciel_image_{int(time.time())}.png"
    target_name = os.path.basename(target_name)
    target_path = os.path.join(downloads_dir, target_name)
    
    # 1. Check if direct file exists in IMAGE_DIR
    src_path = None
    if filename:
        clean_fn = os.path.basename(filename)
        cand = os.path.join(IMAGE_DIR, clean_fn)
        if os.path.isfile(cand):
            src_path = cand
    if not src_path and image_url and "/static/images/" in image_url:
        clean_fn = os.path.basename(image_url.split("?")[0])
        cand = os.path.join(IMAGE_DIR, clean_fn)
        if os.path.isfile(cand):
            src_path = cand

    if src_path and os.path.isfile(src_path):
        try:
            shutil.copy2(src_path, target_path)
            return jsonify({
                "status": "success",
                "message": f"Saved to Downloads: {target_name}",
                "saved_path": target_path
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # 2. Base64 decoded
    if image_b64:
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_b64)
            with open(target_path, "wb") as f_out:
                f_out.write(raw_bytes)
            return jsonify({
                "status": "success",
                "message": f"Saved to Downloads: {target_name}",
                "saved_path": target_path
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # 3. SVG content
    if svg_content:
        try:
            with open(target_path, "w", encoding="utf-8") as f_out:
                f_out.write(svg_content)
            return jsonify({
                "status": "success",
                "message": f"Saved to Downloads: {target_name}",
                "saved_path": target_path
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": "Source image not found"}), 404

@app.route("/api/version")
def api_version():
    return jsonify({"version": APP_VERSION})

@app.route("/api/health")
def api_health():
    ollama_ok = False
    models = []
    try:
        r = requests.get(f"{OLLAMA_API_URL}/api/tags", timeout=2)
        if r.status_code == 200:
            ollama_ok = True
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    mem = psutil.virtual_memory()
    return jsonify({
        "status": "ok", "version": APP_VERSION, "ollama_online": ollama_ok,
        "models": models, "wake_active": _wake_enabled,
        "ram_free_gb": round(mem.available / (1024 ** 3), 1),
        "timestamp": datetime.now().isoformat(),
    })

@app.route("/api/models")
def api_models():
    defaults = ["auto", config.ollama.default_model, config.ollama.fast_model, config.ollama.reasoning_model]
    try:
        r = requests.get(f"{OLLAMA_API_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            names = [m["name"] for m in r.json().get("models", [])]
            # Ensure unique list with auto first
            seen = set()
            models_list = []
            for m in (["auto"] + names + defaults[1:]):
                if m not in seen:
                    seen.add(m)
                    models_list.append(m)
            return jsonify({
                "status": "success",
                "models": models_list,
                "roles": {
                    "default": config.ollama.default_model,
                    "deep_reasoning": config.ollama.reasoning_model,
                    "fast_commands": config.ollama.fast_model,
                }
            })
    except Exception:
        pass
    return jsonify({
        "status": "offline",
        "models": defaults,
        "roles": {
            "default": config.ollama.default_model,
            "deep_reasoning": config.ollama.reasoning_model,
            "fast_commands": config.ollama.fast_model,
        }
    })

@app.route("/api/models/purge", methods=["POST"])
def api_purge_models():
    """Immediately unloads all loaded models from VRAM/RAM to free up system memory."""
    try:
        r = requests.get(f"{OLLAMA_API_URL}/api/ps", timeout=3)
        if r.status_code == 200:
            for m in r.json().get("models", []):
                name = m.get("name")
                if name:
                    requests.post(f"{OLLAMA_API_URL}/api/generate", json={"model": name, "keep_alive": 0}, timeout=3)
        return jsonify({"status": "success", "message": "All inactive models unloaded from RAM."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/system/shutdown", methods=["POST"])
def api_shutdown():
    """Completely close Ciel, unload all models from RAM/VRAM, and terminate the process."""
    def _do_shutdown():
        time.sleep(0.4)
        # 1. Unload all models from Ollama to release VRAM/RAM
        try:
            r = requests.get(f"{OLLAMA_API_URL}/api/ps", timeout=2)
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    name = m.get("name")
                    if name:
                        requests.post(f"{OLLAMA_API_URL}/api/generate", json={"model": name, "keep_alive": 0}, timeout=2)
        except Exception:
            pass
        # 2. Stop wake engine and background threads
        global _wake_active
        _wake_stop_event.set()
        _wake_active = False
        time.sleep(0.3)
        # 3. Clean exit
        log.info("[System] Complete clean shutdown executed.")
        os._exit(0)
        
    threading.Thread(target=_do_shutdown, daemon=True).start()
    return jsonify({"status": "success", "message": "Ciel shutting down cleanly. Releasing all RAM."})

@app.route("/api/sysinfo")
def api_sysinfo():
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        
        # Disk usage for main drive
        disk = psutil.disk_usage(CIEL_ROOT)
        disk_info = {
            "percent": round(disk.percent, 1),
            "free_gb": round(disk.free / (1024 ** 3), 1),
            "total_gb": round(disk.total / (1024 ** 3), 1),
        }

        # Battery telemetry if available
        battery_info = None
        try:
            batt = psutil.sensors_battery()
            if batt:
                battery_info = {
                    "percent": round(batt.percent, 1),
                    "power_plugged": batt.power_plugged,
                }
        except Exception:
            pass

        # Query Ollama for active loaded models in RAM/VRAM
        ollama_active = []
        try:
            r = requests.get(f"{OLLAMA_API_URL}/api/ps", timeout=0.8)
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    ollama_active.append({
                        "name": m.get("name"),
                        "size_vram_gb": round(m.get("size_vram", 0) / (1024 ** 3), 2),
                        "size_total_gb": round(m.get("size", 0) / (1024 ** 3), 2),
                        "expires_at": m.get("expires_at"),
                    })
        except Exception:
            pass

        return jsonify({
            "status": "success",
            "version": APP_VERSION,
            "cpu_percent": round(cpu, 1),
            "cpu_count": psutil.cpu_count(logical=True),
            "ram_percent": round(mem.percent, 1),
            "ram_used_gb": round(mem.used / (1024 ** 3), 1),
            "ram_total_gb": round(mem.total / (1024 ** 3), 1),
            "disk": disk_info,
            "battery": battery_info,
            "ollama_active_models": ollama_active,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/clipboard/analyze", methods=["POST", "GET"])
def api_clipboard_analyze():
    from agent_tools import tool_analyze_clipboard
    data = _json_object() if request.method == "POST" else {}
    focus = data.get("instruction", "")
    analysis = tool_analyze_clipboard(instruction=focus)
    return jsonify({"status": "success", "report": analysis})

@app.route("/api/tts", methods=["POST"])
def api_tts():
    data     = request.json or {}
    raw_text = data.get("text", "").strip()
    if not raw_text:
        return jsonify({"status": "error", "message": "No text provided"}), 400
    clean = clean_text_for_speech(raw_text)
    if not clean:
        return jsonify({"status": "error", "message": "Nothing speakable"}), 400
    filename = f"ciel_{uuid.uuid4().hex[:10]}.mp3"
    filepath = os.path.join(TTS_AUDIO_DIR, filename)
    try:
        future = _tts_executor.submit(_run_tts_sync, clean, filepath)
        future.result(timeout=30)
        return jsonify({"status": "success", "audio_url": f"/api/tts/audio/{filename}", "spoken_text": clean})
    except Exception as e:
        log.error(f"[TTS] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/tts/audio/<filename>")
def api_tts_audio(filename):
    safe = re.sub(r"[^a-zA-Z0-9_\-.]", "", filename)
    return send_from_directory(TTS_AUDIO_DIR, safe, mimetype="audio/mpeg")

@app.route("/api/voice/wake_status", methods=["GET"])
def api_wake_status():
    return jsonify({"status": "success", "wake_active": _wake_enabled})

@app.route("/api/voice/wake_toggle", methods=["GET", "POST"])
def api_wake_toggle():
    global _wake_enabled
    if request.method == "GET":
        return jsonify({"status": "success", "wake_active": _wake_enabled})
    data = request.get_json(silent=True) or {}
    enable = data.get("enable")
    if enable is None:
        enable = not _wake_enabled
    if enable:
        start_wake_engine(enable_feature=True)
    else:
        stop_wake_engine(disable_feature=True)
    return jsonify({"status": "success", "wake_active": _wake_enabled})

@app.route("/api/voice/wake_poll")
def api_wake_poll():
    try:
        event = _wake_queue.get_nowait()
        return jsonify({"status": "event", "event": event, "wake_active": _wake_enabled})
    except queue.Empty:
        return jsonify({"status": "none", "wake_active": _wake_enabled})

@app.route("/api/voice/pause_wake", methods=["POST"])
def api_pause_wake():
    """Temporarily pause the wake engine so the mic device can be used for listen_once."""
    stop_wake_engine(disable_feature=False)
    return jsonify({"status": "paused", "wake_active": _wake_enabled})

@app.route("/api/voice/resume_wake", methods=["POST"])
def api_resume_wake():
    """Resume the wake engine after listen_once has finished recording."""
    if _wake_enabled:
        start_wake_engine(enable_feature=False)
    return jsonify({"status": "resumed", "wake_active": _wake_enabled})

@app.route("/api/voice/listen_cancel", methods=["POST"])
def api_listen_cancel():
    """Immediately cancel active listen_once microphone recording and Whisper transcription."""
    _listen_cancel_event.set()
    return jsonify({"status": "cancelled", "message": "Listen aborted successfully"})

@app.route("/api/voice/listen_once", methods=["POST"])
def api_listen_once():
    """
    Capture a single voice command utterance with fast automatic silence detection.
    Stops ~0.37s after speech finishes or if no speech starts within 2.0s.
    """
    global _wake_thread, _wake_active
    
    RATE        = 44100
    CHUNK       = 2048
    TARGET_RATE = 16000
    MAX_SEC     = 15.0      # Long command support (up to 15 seconds of speech)
    SPEECH_RMS_THRESHOLD = 0.020   # Crisp voice detection threshold
    MAX_SILENCE_CHUNKS   = 10      # ~0.46s pause after speech ends to finish
    MAX_CHUNKS  = int(RATE / CHUNK * MAX_SEC)

    was_wake_enabled = _wake_enabled
    if was_wake_enabled:
        stop_wake_engine(disable_feature=False)

    p = None
    stream = None
    try:
        whisper = get_whisper_model()
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)

        all_buffer     = []
        is_speaking    = False
        silence_chunks = 0
        total_chunks   = 0
        initial_wait_chunks = int(RATE / CHUNK * 2.0)  # Up to 2.0s to begin speaking

        _listen_cancel_event.clear()
        while total_chunks < MAX_CHUNKS:
            if _listen_cancel_event.is_set():
                log.info("[ListenOnce] Cancelled by user.")
                break
            data = stream.read(CHUNK, exception_on_overflow=False)
            total_chunks += 1
            all_buffer.append(data)
            chunk_np = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(chunk_np ** 2)))

            if rms > SPEECH_RMS_THRESHOLD:
                is_speaking = True
                silence_chunks = 0
            elif is_speaking:
                silence_chunks += 1
                if silence_chunks > MAX_SILENCE_CHUNKS:  # Instant 0.37s cutoff after speech ends
                    break
            elif total_chunks > initial_wait_chunks:
                # No speech started within 2.0s
                break

        stream.stop_stream()
        stream.close()
        p.terminate()
        p = None
        stream = None

        if not all_buffer:
            return jsonify({"status": "success", "transcript": ""})

        raw = b"".join(all_buffer)
        audio_44k = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        num_16k   = int(len(audio_44k) * TARGET_RATE / RATE)
        audio_16k = scipy.signal.resample(audio_44k, num_16k).astype(np.float32)

        # Normalize audio volume so quiet / distant voices are clear
        peak = np.max(np.abs(audio_16k))
        if peak > 0.001:
            audio_16k = (audio_16k / peak) * 0.95

        segments, _ = whisper.transcribe(
            audio_16k,
            language="en",
            beam_size=1,
            temperature=0.0,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
            no_speech_threshold=0.6,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300),
            condition_on_previous_text=False,
            initial_prompt="Ciel, Hey Ciel, open Brave, open Chrome, open YouTube, open Discord, open VS Code, open Notepad, open Calculator, open Roblox, open Opera, play music, play song, take screenshot, search for, what is"
        )
        transcript = " ".join(s.text for s in segments).strip()
        if transcript.lower().strip(". ,") in ("you", "thank you", "bye", ""):
            transcript = ""
        clean_dir = correct_spoken_command(transcript)
        log.info(f"[ListenOnce] Transcript: {transcript!r} -> Cleaned: {clean_dir!r}")
        return jsonify({"status": "success", "transcript": clean_dir})

    except Exception as e:
        log.error(f"[ListenOnce] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if stream:
            try: stream.stop_stream(); stream.close()
            except Exception: pass
        if p:
            try: p.terminate()
            except Exception: pass
        if was_wake_enabled and _wake_enabled:
            start_wake_engine(enable_feature=False)
            log.info("[ListenOnce] Wake engine resumed.")


@app.route("/api/tags", methods=["GET"])
def api_tags():
    """Ollama-compatible /api/tags endpoint allowing external tools (like ciel-jarvis-taskbar) to discover Ciel models."""
    default_models = [
        {"name": "ciel-auto", "model": "ciel-auto", "details": {"format": "router", "family": "ciel", "parameter_size": "Auto"}},
        {"name": "qwen2.5-coder:7b", "model": "qwen2.5-coder:7b", "details": {"format": "gguf", "family": "qwen2.5", "parameter_size": "7B"}},
        {"name": "qwen3:latest", "model": "qwen3:latest", "details": {"format": "gguf", "family": "qwen3", "parameter_size": "Deep Reasoning"}},
        {"name": "qwen2.5-coder:1.5b", "model": "qwen2.5-coder:1.5b", "details": {"format": "gguf", "family": "qwen2.5", "parameter_size": "1.5B"}},
    ]
    try:
        r = requests.get(f"{OLLAMA_API_URL}/api/tags", timeout=2)
        if r.status_code == 200:
            installed = r.json().get("models", [])
            names = {m.get("name") for m in default_models}
            for m in installed:
                if m.get("name") not in names:
                    default_models.append(m)
    except Exception:
        pass
    return jsonify({"models": default_models})


@app.route("/api/upload-image", methods=["POST"])
def api_upload_image():
    """Upload an image file or base64 payload to Ciel storage."""
    try:
        data = request.get_json(silent=True) or {}
        image_bytes = None
        orig_filename = "upload"
        ext = ".png"

        if "file" in request.files:
            file_obj = request.files["file"]
            orig_filename = file_obj.filename or "upload"
            ext = os.path.splitext(orig_filename)[1].lower() or ".png"
            image_bytes = file_obj.read()
        elif "image_b64" in data or "image_base64" in data:
            raw_b64 = (data.get("image_b64") or data.get("image_base64") or "").strip()
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            import base64
            image_bytes = base64.b64decode(raw_b64)
            orig_filename = data.get("filename", "upload")
            ext = os.path.splitext(orig_filename)[1].lower() or ".png"

        if not image_bytes:
            return jsonify({"status": "error", "message": "No image data or file uploaded."}), 400

        import uuid
        clean_id = uuid.uuid4().hex[:10]
        filename = f"upload_{clean_id}{ext}"
        save_path = os.path.join(IMAGE_DIR, filename)
        with open(save_path, "wb") as f_out:
            f_out.write(image_bytes)

        return jsonify({
            "status": "success",
            "filename": filename,
            "image_path": save_path,
            "image_url": f"/static/images/{filename}"
        })
    except Exception as e:
        log.error(f"[UploadImage] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/primitive/generate", methods=["POST"])
def api_primitive_generate():
    """Endpoint to convert an image into geometric primitive vector art (SVG + PNG)."""
    from primitive_engine import run_primitive_reproduction
    from config import config

    data = request.json or {}
    image_path = (data.get("image_path") or "").strip()
    num_shapes = max(5, min(300, int(data.get("num_shapes") or 60)))
    mode = (data.get("mode") or "triangle").strip().lower()
    alpha = float(data.get("alpha") or 0.55)
    async_task = bool(data.get("async_task", False))
    out_dir = str(config.paths.image_dir)

    # Check if base64 provided directly
    if not image_path and (data.get("image_base64") or data.get("image_b64")):
        try:
            import base64, uuid
            raw_b64 = (data.get("image_base64") or data.get("image_b64") or "").strip()
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            b_data = base64.b64decode(raw_b64)
            temp_name = f"prim_input_{uuid.uuid4().hex[:8]}.png"
            temp_path = os.path.join(IMAGE_DIR, temp_name)
            with open(temp_path, "wb") as f_tmp:
                f_tmp.write(b_data)
            image_path = temp_path
        except Exception as ex:
            return jsonify({"status": "error", "message": f"Base64 decode failed: {ex}"}), 400

    if not image_path or not os.path.exists(image_path):
        # Intelligent fallback resolution
        clean_cand = image_path.replace("/static/images/", "").replace("\\static\\images\\", "").lstrip("/\\")
        fallbacks = [
            clean_cand,
            os.path.join(out_dir, clean_cand),
            os.path.join(str(config.paths.workspace_dir), clean_cand),
            os.path.join(CIEL_ROOT, "app", "static", "images", clean_cand),
            os.path.join(CIEL_ROOT, "app", "static", clean_cand),
            os.path.join(os.path.expanduser("~/Pictures"), clean_cand),
            os.path.join(os.path.expanduser("~/Downloads"), clean_cand),
            os.path.join(os.path.expanduser("~/Desktop"), clean_cand),
        ]
        found = None
        for fb in fallbacks:
            if fb and os.path.exists(fb):
                found = fb
                break
        if found:
            image_path = found
        else:
            return jsonify({"status": "error", "message": f"Image path '{image_path}' not found. Please provide an existing file or upload an image."}), 400

    if async_task:
        from task_manager import task_manager
        def _async_job(task_ctx=None):
            if task_ctx:
                task_ctx.update_progress(10, "Downscaling and sampling initial canvas...")
            def _prog(cur, total, mse):
                if task_ctx:
                    pct = int(10 + (cur / total) * 85)
                    task_ctx.update_progress(pct, f"Rendering shape {cur}/{total} (MSE: {round(mse, 1)})")
            res = run_primitive_reproduction(image_path, num_shapes=num_shapes, mode=mode, output_dir=out_dir, alpha=alpha, progress_callback=_prog)
            return res

        task = task_manager.submit("primitive_art", _async_job)
        return jsonify({"status": "queued", "task_id": task.id, "message": "Primitive art generation queued in background."})

    try:
        res = run_primitive_reproduction(image_path, num_shapes=num_shapes, mode=mode, output_dir=out_dir, alpha=alpha)
        svg_content = ""
        if os.path.exists(res["svg_path"]):
            with open(res["svg_path"], "r", encoding="utf-8") as f:
                svg_content = f.read()
        res["svg_content"] = svg_content
        return jsonify(res)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

_active_chat_lock = threading.Lock()
_active_chat_stream = None
_active_abort_event = threading.Event()

@app.route("/api/chat/abort", methods=["POST"])
def api_chat_abort():
    """Immediately terminate in-flight Ollama generation and release CPU threads."""
    global _active_chat_stream
    _active_abort_event.set()
    with _active_chat_lock:
        if _active_chat_stream:
            try:
                _active_chat_stream.close()
                if hasattr(_active_chat_stream, "raw") and _active_chat_stream.raw:
                    _active_chat_stream.raw.close()
                log.info("[ChatAbort] Successfully closed in-flight Ollama connection.")
            except Exception as e:
                log.debug(f"[ChatAbort] Stream close: {e}")
            _active_chat_stream = None
    return jsonify({"status": "aborted", "message": "In-flight generation terminated."})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data        = request.json or {}
    messages    = data.get("messages", [])
    model_req   = data.get("model", "auto")
    agent_mode  = bool(data.get("agent_mode", False))
    active_code = data.get("active_code", "").strip()
    active_file = data.get("active_file", "active file")
    is_ndjson = (
        request.headers.get("Accept") == "application/x-ndjson"
        or data.get("format") == "ollama"
        or (data.get("stream") is True and "text/event-stream" not in request.headers.get("Accept", "") and not active_code and not agent_mode)
    )

    user_last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_last = m.get("content", "")
            break

    # 1. Direct System Command Interceptor (Instant App Launch / Music execution)
    import agent_tools
    import importlib
    try:
        importlib.reload(agent_tools)
        agent_tools.set_permission_callback(permission_callback)
    except Exception:
        pass
    try:
        is_direct, direct_resp = agent_tools.handle_direct_command(user_last)
        if is_direct:
            def direct_stream():
                if is_ndjson:
                    yield json.dumps({"message": {"role": "assistant", "content": direct_resp}, "done": True}) + "\n"
                else:
                    yield f"data: {json.dumps({'content': direct_resp, 'thinking': '', 'done': True, 'routed_model': 'System Tool'})}\n\n"
            mimetype = "application/x-ndjson" if is_ndjson else "text/event-stream"
            return Response(direct_stream(), mimetype=mimetype)
    except Exception as e:
        log.error(f"[DirectCommand] Interceptor error: {e}")

    # Dynamic Task-Based Model Routing
    routed_label = None
    if model_req in ("ciel-auto", "auto", "", None) or "auto" in str(model_req).lower():
        model, routed_label = route_model_for_task(user_last, active_code)
        log.info(f"[AutoRouter] Routed prompt '{user_last[:35]}' -> {model} ({routed_label})")
    else:
        model = model_req

    memory_ctx = get_memory_context()
    sys_content = CIEL_SYSTEM_PROMPT
    if memory_ctx:
        sys_content += f"\n\n{memory_ctx}"
    if agent_mode:
        sys_content += "\n\n" + SYSTEM_PROMPT
    else:
        sys_content += "\n\n[AGENT MODE: OFF] Master has set Agent Mode to OFF. Do not execute tools or modify/access files unless Master enables Agent Mode."
    if active_code:
        sys_content += (
            f"\n\n[Active Workspace Context: file='{active_file}']\n"
            f"```\n{active_code[:3500]}\n```\n"
            "(Master is currently reviewing this file. Use this context when asked.)"
        )
    if not isinstance(messages, list) or len(messages) > 100:
        return jsonify({"status": "error", "message": "messages must be a list with at most 100 items"}), 400
    filtered = [dict(m) for m in messages if isinstance(m, dict) and m.get("role") != "system"]
    for m in filtered:
        if m.get("content"):
            m["content"] = re.sub(r"\[(?:Celebrate Your Soul|All Pin Music|K-pop)[^\]]*\][^\n]*", "", m["content"], flags=re.I).strip()

    # Strip any dangling empty assistant placeholder from the end of incoming messages
    while filtered and filtered[-1].get("role") == "assistant" and not (filtered[-1].get("content") or "").strip():
        filtered.pop()

    # ── History Sanitization: Prune Aborted, Cancelled, and Empty Conversation Turns ──
    # If a user message was cancelled or left unfulfilled, do not pass it to Ollama on the next turn,
    # preventing the model from answering the cancelled task instead of the new query.
    sanitized = []
    i = 0
    while i < len(filtered):
        curr = filtered[i]
        curr_role = curr.get("role")
        curr_content = (curr.get("content") or "").strip()

        # The very last user message is ALWAYS the active request — NEVER prune it!
        if i == len(filtered) - 1:
            if curr_role == "user" and curr_content:
                sanitized.append(curr)
            break

        if curr_role == "user" and i < len(filtered) - 1:
            next_msg = filtered[i + 1]
            next_role = next_msg.get("role")
            next_content = (next_msg.get("content") or "").strip()

            is_unfulfilled = (
                next_role == "assistant" and (
                    not next_content
                    or "[generation stopped]" in next_content.lower()
                    or "[generation cancelled" in next_content.lower()
                    or "[request cancelled" in next_content.lower()
                    or "[notice] transmission error" in next_content.lower()
                )
            )
            if is_unfulfilled:
                log.info(f"[ChatSanitizer] Pruned unfulfilled user turn: {curr_content[:40]!r}")
                i += 2
                continue
            elif next_role == "user":
                log.info(f"[ChatSanitizer] Pruned superseded user turn: {curr_content[:40]!r}")
                i += 1
                continue

        if curr_role == "assistant" and (not curr_content or "[generation stopped]" in curr_content.lower() or "[generation cancelled" in curr_content.lower()):
            i += 1
            continue

        sanitized.append(curr)
        i += 1

    if not sanitized and user_last:
        sanitized = [{"role": "user", "content": user_last}]

    # ── High-Performance Sliding Context Window (prevents context lag & memory bloat) ──
    if len(sanitized) > 14:
        # Retain initial conversation context (first 2 messages) + recent dialogue (last 12 messages)
        compacted = sanitized[:2] + [{"role": "assistant", "content": "[Notice] ... earlier dialogue compacted for optimal speed ..."}] + sanitized[-12:]
    else:
        compacted = sanitized

    final_msgs = [{"role": "system", "content": sys_content}] + compacted

    def generate():
        _active_abort_event.clear()
        payload = {
            "model": model,
            "messages": final_msgs,
            "stream": True,
            "keep_alive": "5m",  # Automatically frees model RAM after 5 minutes of inactivity
        }
        full_response = ""

        def _stream_ollama(target_payload, allow_heal=True):
            global _active_chat_stream
            nonlocal full_response
            r = None
            try:
                r = requests.post(f"{OLLAMA_API_URL}/api/chat", json=target_payload, stream=True, timeout=300)
                if r.status_code != 200:
                    err_msg = f"[Notice] Ollama engine error (HTTP {r.status_code})"
                    try:
                        err_data = r.json()
                        if "error" in err_data:
                            err_msg += f": {err_data['error']}"
                    except Exception:
                        pass
                    log.error(f"[Chat] {err_msg}")
                    yield f"data: {json.dumps({'content': err_msg, 'done': True})}\n\n"
                    return

                with _active_chat_lock:
                    _active_chat_stream = r

                for line in r.iter_lines():
                    if _active_abort_event.is_set():
                        log.info("[Chat] Active generation terminated by abort event.")
                        break
                    if not line:
                        continue
                    try:
                        chunk    = json.loads(line.decode("utf-8"))
                        if "error" in chunk:
                            err_msg = f"[Notice] Engine error: {chunk['error']}"
                            log.error(f"[Chat] {err_msg}")
                            yield f"data: {json.dumps({'content': err_msg, 'done': True})}\n\n"
                            return
                        content  = chunk.get("message", {}).get("content", "")
                        thinking = chunk.get("message", {}).get("thinking", "")
                        done     = chunk.get("done", False)
                        if content:
                            full_response += content
                        if is_ndjson:
                            yield json.dumps({"message": {"role": "assistant", "content": content}, "done": done}) + "\n"
                        else:
                            yield f"data: {json.dumps({'content': content, 'thinking': thinking, 'done': done})}\n\n"
                    except json.JSONDecodeError:
                        continue
            except requests.exceptions.ConnectionError:
                if allow_heal:
                    ollama_exe = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
                    if os.path.exists(ollama_exe):
                        yield f"data: {json.dumps({'content': '[Notice] Neural engine was offline. Awakening local core...', 'thinking': '', 'done': False})}\n\n"
                        subprocess.Popen([ollama_exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                        time.sleep(2.5)
                        yield from _stream_ollama(target_payload, allow_heal=False)
                        return
                err = "[Notice] Ollama is not reachable. Please start Ollama, Master."
                yield f"data: {json.dumps({'content': err, 'done': True})}\n\n"
            except Exception as e:
                if "closed" in str(e).lower() or isinstance(e, requests.exceptions.RequestException):
                    log.info("[Chat] Active generation terminated by abort signal.")
                    return
                err = f"[Notice] Transmission error: {e}"
                log.error(f"[Chat] {err}")
                yield f"data: {json.dumps({'content': err, 'done': True})}\n\n"
            finally:
                with _active_chat_lock:
                    if _active_chat_stream is r:
                        _active_chat_stream = None
                if r:
                    try:
                        r.close()
                    except Exception:
                        pass

        if routed_label:
            yield f"data: {json.dumps({'content': '', 'thinking': '', 'done': False, 'routed_model': routed_label})}\n\n"

        # 1. Primary Model Generation
        yield from _stream_ollama(payload, allow_heal=True)

        # 2. Multi-Turn Autonomous Tool Execution & Synthesis
        if agent_mode and full_response.strip():
            tool_outputs = []
            for tool_result, was_called in parse_and_execute_tool_call(full_response, user_last):
                if was_called and tool_result:
                    yield f"data: {json.dumps({'content': '', 'done': False, 'tool_result': tool_result})}\n\n"
                    tool_outputs.append(tool_result)

            if tool_outputs:
                combined = "\n\n---\n\n".join(tool_outputs)
                if len(combined) > 6000:
                    combined = combined[:6000] + "\n...[truncated for length]"

                synthesis_payload = {
                    "model": model,
                    "messages": final_msgs + [
                        {"role": "assistant", "content": full_response},
                        {
                            "role": "user",
                            "content": (
                                f"[Report: Subsystem Tool Execution Result]\n{combined}\n\n"
                                "[Directive]: Analyze and synthesize the tool output above. Provide a cohesive, clear response to Master "
                                "in your calm, intelligent Tensura Manas Ciel persona. Address Master directly."
                            ),
                        },
                    ],
                    "stream": True,
                    "keep_alive": "5m",
                }
                sep_event = json.dumps({'content': '\n\n', 'thinking': '', 'done': False})
                yield f"data: {sep_event}\n\n"
                yield from _stream_ollama(synthesis_payload, allow_heal=False)

        # 3. Auto-extract and persist facts to long-term memory in background
        if full_response.strip() and user_last:
            threading.Thread(target=_auto_extract_memories, args=(user_last, full_response), daemon=True).start()

    return Response(generate(), mimetype="application/x-ndjson" if is_ndjson else "text/event-stream")

@app.route("/api/permission/pending")
def api_permission_pending():
    with _perm_lock:
        for perm_id, perm in _pending_permissions.items():
            if not perm["event"].is_set():
                return jsonify({"status": "pending", "id": perm_id, "action": perm["action"], "tool": perm["action"], "description": perm["description"]})
    return jsonify({"status": "none"})

@app.route("/api/permission/respond", methods=["POST"])
def api_permission_respond():
    data        = request.json or {}
    perm_id     = data.get("id")
    raw_allowed = data.get("allowed", data.get("allow", False))
    
    import agent_tools
    if raw_allowed == "allow_read_all":
        agent_tools.set_allow_read_all(True)
        allowed = True
        log.info("[Permission] Master granted session scope: ALLOW READ ALL FILES")
    elif isinstance(raw_allowed, bool):
        allowed = raw_allowed
    elif str(raw_allowed).lower() in ("true", "allow", "allow_once"):
        allowed = True
    else:
        allowed = False

    with _perm_lock:
        if perm_id in _pending_permissions:
            _pending_permissions[perm_id]["result"] = allowed
            _pending_permissions[perm_id]["event"].set()
            return jsonify({"status": "ok", "allowed": allowed, "allow_read_all": agent_tools.get_allow_read_all()})
    return jsonify({"status": "not_found"}), 404

@app.route("/api/permission/reset_scopes", methods=["POST"])
def api_permission_reset_scopes():
    import agent_tools
    agent_tools.reset_permission_scopes()
    return jsonify({"status": "ok", "message": "Permission scopes reset to ask every time."})



@app.route("/api/vision/jarvis_observe", methods=["POST", "GET"])
def api_vision_jarvis_observe():
    import agent_tools
    res = agent_tools.tool_jarvis_observe()
    return jsonify({"status": "success", "result": res})

@app.route("/api/authority/audit", methods=["GET"])
def api_authority_audit():
    import agent_tools
    return jsonify({"status": "ok", "audit_log": agent_tools.get_authority_audit_log()})

@app.route("/api/system/launch_companion", methods=["POST"])
def api_launch_companion():
    try:
        import subprocess, sys
        companion_script = os.path.join(CIEL_ROOT, "app", "launch_desktop.py")
        subprocess.Popen(
            [sys.executable, companion_script, "--companion"],
            cwd=CIEL_ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        return jsonify({"status": "ok", "message": "Sidecar Companion HUD launched on desktop"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

_summon_callback = None

def register_summon_callback(cb):
    global _summon_callback
    _summon_callback = cb

@app.route("/api/system/summon", methods=["POST", "GET"])
def api_system_summon():
    if _summon_callback:
        try:
            _summon_callback()
        except Exception as e:
            log.error(f"[Summon] Error invoking callback: {e}")
    return jsonify({"status": "ok", "message": "Summon invoked"})

@app.route("/api/system/startup", methods=["GET", "POST"])
def api_system_startup():
    try:
        import winreg
        RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            target = data.get("enable")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                if target is None:
                    try:
                        winreg.QueryValueEx(key, "Ciel")
                        target = False
                    except FileNotFoundError:
                        target = True
                
                if target:
                    ciel_exe = os.path.join(CIEL_ROOT, "Ciel.exe")
                    if os.path.exists(ciel_exe):
                        cmd = f'"{ciel_exe}" --tray'
                    else:
                        cmd = f'pythonw.exe "{os.path.join(APP_DIR, "launch_desktop.py")}" --tray'
                    winreg.SetValueEx(key, "Ciel", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "Ciel")
                    except FileNotFoundError:
                        pass
        enabled = False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, "Ciel")
                enabled = bool(val)
        except FileNotFoundError:
            enabled = False
        return jsonify({"status": "ok", "enabled": enabled})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/chats")
def api_get_chats():
    chats = load_all_chats()
    result = sorted([
        {"id": cid, "title": c.get("title", "New Conversation"), "updated_at": c.get("updated_at", ""),
         "created_at": c.get("created_at", ""), "model": c.get("model", DEFAULT_MODEL), "message_count": len(c.get("messages", []))}
        for cid, c in chats.items()
    ], key=lambda x: x["updated_at"], reverse=True)
    return jsonify({"status": "success", "chats": result})

@app.route("/api/chats/<chat_id>")
def api_get_chat(chat_id):
    chats = load_all_chats()
    if chat_id in chats:
        return jsonify({"status": "success", "chat": chats[chat_id]})
    return jsonify({"status": "error", "message": "Chat not found"}), 404

@app.route("/api/chats/<chat_id>", methods=["POST"])
def api_save_chat(chat_id):
    data    = request.json or {}
    chats   = load_all_chats()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = chats.get(chat_id, {"id": chat_id, "created_at": now_iso, "title": data.get("title", "New Conversation")})
    existing["title"]      = data.get("title", existing.get("title", "New Conversation"))
    existing["messages"]   = data.get("messages", [])
    existing["model"]      = data.get("model", DEFAULT_MODEL)
    existing["updated_at"] = now_iso
    chats[chat_id]         = existing
    save_all_chats(chats)
    return jsonify({"status": "success", "chat": existing})

@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    chats = load_all_chats()
    if chat_id in chats:
        del chats[chat_id]
        save_all_chats(chats)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Not found"}), 404

@app.route("/api/image-models")
def api_image_models():
    models = []
    for k, v in IMAGE_MODELS.items():
        is_ready = _resolve_local_model_path(v["repo"]) != v["repo"]
        models.append({
            "key": k,
            "label": v["label"],
            "default_steps": v["default_steps"],
            "downloaded": is_ready,
            "badge": "Ready Offline" if is_ready else "Needs Download",
        })
    return jsonify({"status": "success", "models": models})

def expand_anime_prompt(raw_prompt: str) -> str:
    """Use local Ollama LLM to expand a user prompt into a rich Copilot-style anime prompt."""
    clean = (raw_prompt or "").strip()
    if not clean:
        return "1girl, silver hair, glowing blue eyes, elegant magical robes, fantasy library background, cinematic lighting, masterpiece, 8k"

    system_instruction = (
        "You are an expert anime visual prompt engineer for diffusion models (like Counterfeit and Anything V5). "
        "Take the user's short concept and rewrite/expand it into a vivid, descriptive prompt (1-2 sentences). "
        "Include: character details (hair, eye color, expression), clothing, lighting (cinematic, soft volumetric glow, rim light), "
        "atmospheric background, and quality tags (masterpiece, detailed cel-shading, 8k). "
        "Output ONLY the final prompt text. Do NOT include greetings, quotes, or explanations."
    )

    try:
        model = config.ollama.fast_model or "qwen2.5-coder:1.5b"
        r = requests.post(f"{OLLAMA_API_URL}/api/generate", json={
            "model": model,
            "prompt": f"{system_instruction}\n\nUser Concept: {clean}\n\nExpanded Anime Prompt:",
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 120}
        }, timeout=8)
        if r.status_code == 200:
            exp = r.json().get("response", "").strip()
            exp = exp.strip('"`\'')
            if len(exp) > 15:
                return exp
    except Exception as e:
        log.debug(f"[PromptEnhancer] Ollama expansion skipped: {e}")

    return f"{clean}, expressive eyes, beautiful detailed anime hair, dynamic cinematic lighting, intricate clothing details, lush background, masterpiece, highest quality, 8k resolution"

@app.route("/api/enhance-prompt", methods=["POST"])
def api_enhance_prompt():
    data = _json_object()
    raw_prompt = data.get("prompt", "").strip()
    if not raw_prompt:
        return jsonify({"status": "error", "message": "Prompt is required"}), 400
    
    enhanced = expand_anime_prompt(raw_prompt)
    return jsonify({
        "status": "success",
        "original": raw_prompt,
        "enhanced_prompt": enhanced
    })

@app.route("/api/generate-image", methods=["POST"])
def api_generate_image():
    data = _json_object()
    prompt = data.get("prompt", "").strip()
    if data.get("auto_enhance"):
        prompt = expand_anime_prompt(prompt)
    negative_prompt = data.get("negative_prompt", "Blurry, low quality, bad anatomy, watermark")
    model_key = data.get("image_model", "sdxl-turbo")
    if model_key not in IMAGE_MODELS:
        return jsonify({"status": "error", "message": "Unknown image model"}), 400
    config = IMAGE_MODELS[model_key]
    steps = safe_int(data.get("steps"), default=config["default_steps"], minimum=1, maximum=50)
    width = safe_int(data.get("width"), default=512, minimum=256, maximum=1024)
    height = safe_int(data.get("height"), default=512, minimum=256, maximum=1024)
    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required"}), 400
    pipe = load_image_pipeline(model_key)
    if pipe is None:
        return jsonify({"status": "error", "message": f"Model '{model_key}' failed to load"}), 500
    try:
        log.info(f"[Image] Generating '{prompt}' ({model_key})")
        result = pipe(prompt=prompt, negative_prompt=negative_prompt, num_inference_steps=steps, guidance_scale=float(config["guidance_scale"]), width=width, height=height)
        image = result.images[0]
        filename = f"{model_key}_{uuid.uuid4().hex[:8]}.png"
        image.save(os.path.join(IMAGE_DIR, filename), format="PNG")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return jsonify({"status": "success", "filename": filename, "model_used": config["label"], "image_url": f"/static/images/{filename}", "image_b64": f"data:image/png;base64,{b64}"})
    except Exception as e:
        log.error(f"[Image] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ── Real-ESRGAN Anime 4x HD Upscaler (Stage 7 of Anime Pipeline) ──
import torch

class _ResidualDenseBlock(torch.nn.Module):
    def __init__(self, num_feat=64, num_grow_ch=32):
        super().__init__()
        self.conv1 = torch.nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = torch.nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = torch.nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = torch.nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = torch.nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = torch.nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x

class _RRDB(torch.nn.Module):
    def __init__(self, num_feat, num_grow_ch=32):
        super().__init__()
        self.rdb1 = _ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = _ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = _ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x

class _RRDBNet(torch.nn.Module):
    def __init__(self, num_in_ch=3, num_out_ch=3, scale=4, num_feat=64, num_block=6, num_grow_ch=32):
        super().__init__()
        self.scale = scale
        self.conv_first = torch.nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = torch.nn.Sequential(*[_RRDB(num_feat, num_grow_ch) for _ in range(num_block)])
        self.conv_body = torch.nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up1 = torch.nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = torch.nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_hr = torch.nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = torch.nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = torch.nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat
        feat = self.lrelu(self.conv_up1(torch.nn.functional.interpolate(feat, scale_factor=2, mode='nearest')))
        feat = self.lrelu(self.conv_up2(torch.nn.functional.interpolate(feat, scale_factor=2, mode='nearest')))
        out = self.conv_last(self.lrelu(self.conv_hr(feat)))
        return out

_upscaler_model = None
_upscaler_lock = threading.Lock()

def get_anime_upscaler():
    global _upscaler_model
    if _upscaler_model is not None:
        return _upscaler_model
    with _upscaler_lock:
        if _upscaler_model is not None:
            return _upscaler_model
        weight_path = os.path.join(CIEL_ROOT, "models", "upscalers", "RealESRGAN_x4plus_anime_6B.pth")
        if not os.path.exists(weight_path):
            return None
        import torch
        net = _RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)
        sd = torch.load(weight_path, map_location="cpu")
        if "params_ema" in sd:
            sd = sd["params_ema"]
        elif "params" in sd:
            sd = sd["params"]
        net.load_state_dict(sd, strict=True)
        net.eval()
        _upscaler_model = net
        return _upscaler_model

def run_latent_diffusion_upscale(image_input_path: str, scale: int = 2, prompt: str = "", negative_prompt: str = "", model_key: str = "counterfeit-v3") -> str:
    """Upscale and refine an anime image using Latent Diffusion resampler."""
    from PIL import Image
    from diffusers import AutoPipelineForImage2Image
    
    img = Image.open(image_input_path).convert("RGB")
    orig_w, orig_h = img.size
    
    # Calculate target dimensions (multiples of 8, max 768 on CPU for snappy 15-20s response)
    target_w = (int(orig_w * scale) // 8) * 8
    target_h = (int(orig_h * scale) // 8) * 8
    if max(target_w, target_h) > 768:
        ratio = 768.0 / max(target_w, target_h)
        target_w = (int(target_w * ratio) // 8) * 8
        target_h = (int(target_h * ratio) // 8) * 8
    
    resized_img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    base_pipe = load_image_pipeline(model_key if model_key in IMAGE_MODELS else "counterfeit-v3")
    if base_pipe is None:
        base_pipe = load_image_pipeline("counterfeit-v3")
        
    img2img_pipe = AutoPipelineForImage2Image.from_pipe(base_pipe)
    
    clean_prompt = prompt.strip() if prompt else "1girl, highly detailed anime linework, smooth cel shading, vibrant colors, masterpiece, best quality, 8k"
    clean_neg = negative_prompt.strip() if negative_prompt else "blurry, low quality, bad anatomy, artifacts, watermark"
    
    import torch
    with torch.no_grad():
        res = img2img_pipe(
            prompt=clean_prompt,
            negative_prompt=clean_neg,
            image=resized_img,
            strength=0.35,
            num_inference_steps=6,
            guidance_scale=1.0
        )
        out_img = res.images[0]
        
    out_name = f"upscaled_latent_{scale}x_{uuid.uuid4().hex[:8]}.png"
    out_path = os.path.join(IMAGE_DIR, out_name)
    out_img.save(out_path, format="PNG")
    return out_name

def run_anime_upscale(image_input_path: str, scale: int = 4) -> str:
    """Upscale an anime image using Real-ESRGAN Anime 6B model, saving it to IMAGE_DIR."""
    from PIL import Image
    import numpy as np
    import torch

    img = Image.open(image_input_path).convert("RGB")
    w, h = img.size
    
    # Scale appropriately for memory
    if max(w, h) > 768:
        img.thumbnail((768, 768), Image.Resampling.LANCZOS)
        w, h = img.size

    model = get_anime_upscaler()
    if model is None:
        out_img = img.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    else:
        img_np = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(img_np.transpose((2, 0, 1))).unsqueeze(0)
        with torch.no_grad():
            output = model(tensor)
        output = output.squeeze(0).clamp(0, 1).numpy().transpose((1, 2, 0))
        out_img = Image.fromarray((output * 255.0).round().astype(np.uint8))
        if scale == 2:
            out_img = out_img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)

    out_name = f"upscaled_{scale}x_{uuid.uuid4().hex[:8]}.png"
    out_path = os.path.join(IMAGE_DIR, out_name)
    out_img.save(out_path, format="PNG")
    return out_name

@app.route("/api/upscale-image", methods=["POST"])
def api_upscale_image():
    data = _json_object()
    image_url = data.get("image_url", "").strip()
    filename = data.get("filename", "").strip()
    scale = safe_int(data.get("scale"), default=4, minimum=2, maximum=4)
    upscaler = (data.get("upscaler") or data.get("method") or "realesrgan").lower().strip()
    prompt = data.get("prompt", "")
    neg_prompt = data.get("negative_prompt", "")
    model_key = data.get("image_model", "counterfeit-v3")

    src_path = None
    if filename:
        cand = os.path.join(IMAGE_DIR, os.path.basename(filename))
        if os.path.isfile(cand):
            src_path = cand
    if not src_path and image_url:
        cand = os.path.join(IMAGE_DIR, os.path.basename(image_url.split("?")[0]))
        if os.path.isfile(cand):
            src_path = cand

    if not src_path or not os.path.isfile(src_path):
        return jsonify({"status": "error", "message": "Source image not found"}), 404

    try:
        from PIL import Image
        if "latent" in upscaler:
            log.info(f"[Upscaler] Running Latent Diffusion on {os.path.basename(src_path)}")
            out_name = run_latent_diffusion_upscale(
                src_path,
                scale=min(scale, 2),
                prompt=prompt,
                negative_prompt=neg_prompt,
                model_key=model_key
            )
            msg = "Successfully enhanced with Latent Diffusion Anime Resampler!"
        else:
            log.info(f"[Upscaler] Running Real-ESRGAN {scale}x on {os.path.basename(src_path)}")
            out_name = run_anime_upscale(src_path, scale=scale)
            msg = f"Successfully upscaled {scale}× with Real-ESRGAN Anime HD!"

        buf = io.BytesIO()
        with Image.open(os.path.join(IMAGE_DIR, out_name)) as im:
            im.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            w, h = im.size

        return jsonify({
            "status": "success",
            "filename": out_name,
            "image_url": f"/static/images/{out_name}",
            "image_b64": f"data:image/png;base64,{b64}",
            "dimensions": f"{w} × {h}",
            "message": msg
        })
    except Exception as e:
        log.error(f"[Upscaler] Upscale error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Upscale error: {str(e)}"}), 500

@app.route("/api/ide/tree")
def api_ide_tree():
    raw_path = request.args.get("path", DEFAULT_WORKSPACE)
    try:
        req_path = str(_workspace_path(raw_path))
    except SecurityError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    if not os.path.isdir(req_path):
        return jsonify({"status": "error", "message": "Workspace directory not found"}), 404
    items = []
    skip = {"__pycache__", "venv", ".git", "node_modules", ".env"}
    try:
        for entry in sorted(os.listdir(req_path)):
            if entry.startswith(".") or entry in skip:
                continue
            full = os.path.join(req_path, entry)
            items.append({"name": entry, "path": full, "type": "directory" if os.path.isdir(full) else "file", "ext": os.path.splitext(entry)[1].lower() if os.path.isfile(full) else ""})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "success", "current_path": req_path, "parent_path": os.path.dirname(req_path) or None, "items": items})

@app.route("/api/ide/read", methods=["POST"])
def api_ide_read():
    data = _json_object()
    raw_path = data.get("path", "").strip()
    try:
        file_path = str(_workspace_path(raw_path))
    except SecurityError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    if not os.path.isfile(file_path):
        return jsonify({"status": "error", "message": "File not found"}), 404
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"status": "success", "path": file_path, "filename": os.path.basename(file_path), "content": content})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ide/save", methods=["POST"])
def api_ide_save():
    data = _json_object()
    raw_path = data.get("path", "").strip()
    content = data.get("content", "")
    if not raw_path or not isinstance(content, str):
        return jsonify({"status": "error", "message": "Path and text content are required"}), 400
    try:
        file_path = str(_workspace_path(raw_path))
        if not request_permission("IDE WRITE", f"Save file: {file_path} ({len(content):,} characters)"):
            return jsonify({"status": "denied", "message": "Save cancelled by Master"}), 403
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"status": "success", "message": f"Saved {os.path.basename(file_path)}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ide/create", methods=["POST"])
def api_ide_create():
    data = _json_object()
    folder = data.get("folder", DEFAULT_WORKSPACE)
    filename = data.get("filename", "").strip()
    try:
        folder_path = _workspace_path(folder)
    except SecurityError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    if not filename:
        return jsonify({"status": "error", "message": "Filename required"}), 400
    if any(c in filename for c in '/:*?"<>|\\'):
        return jsonify({"status": "error", "message": "Invalid filename characters"}), 400
    full_path = str((folder_path / filename).resolve())
    try:
        _workspace_path(full_path)
        if not request_permission("IDE CREATE", f"Create file: {full_path}"):
            return jsonify({"status": "denied", "message": "Create cancelled by Master"}), 403
        if not os.path.exists(full_path):
            os.makedirs(os.path.dirname(os.path.abspath(full_path)), exist_ok=True)
            open(full_path, "w").close()
        return jsonify({"status": "success", "path": full_path, "filename": filename})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ide/run", methods=["POST"])
def api_ide_run():
    data = _json_object()
    code = data.get("code", "")
    raw_path = data.get("path", "").strip()
    lang = (data.get("lang") or "").lower().strip()
    if not isinstance(code, str) or len(code) > 1_000_000:
        return jsonify({"status": "error", "message": "Code must be text under 1 MB"}), 400
    file_path = ""
    if raw_path:
        try:
            file_path = str(_workspace_path(raw_path))
        except SecurityError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
    if file_path and os.path.isfile(file_path):
        ext = os.path.splitext(file_path)[1].lower()
    else:
        ext = {"python": ".py", "py": ".py", "cpp": ".cpp", "c": ".cpp", "java": ".java", "javascript": ".js", "js": ".js", "typescript": ".ts", "ts": ".ts"}.get(lang, ".py")
    try:
        if not request_permission("IDE RUN", f"Execute {lang or ext} code from {file_path or 'temporary editor buffer'}"):
            return jsonify({"status": "denied", "message": "Execution cancelled by Master"}), 403
        if ext == ".py":
            if file_path and os.path.isfile(file_path):
                src = file_path; cwd = os.path.dirname(file_path)
            else:
                tmp = tempfile.mkdtemp(); src = os.path.join(tmp, "script.py"); Path(src).write_text(code, encoding="utf-8"); cwd = DEFAULT_WORKSPACE
            res = subprocess.run([sys.executable, src], capture_output=True, text=True, timeout=30, cwd=cwd)
            return jsonify({"status": "success", "stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode})
        elif ext in {".cpp", ".c", ".cc", ".cxx"}:
            gpp = _find_executable("g++", [r"C:\Program Files\CodeBlocks\MinGW\bin\g++.exe", r"C:\MinGW\bin\g++.exe", r"C:\msys64\mingw64\bin\g++.exe"])
            if not gpp:
                return jsonify({"status": "error", "stdout": "", "stderr": "[Notice] C++ compiler (g++) not found. Install MinGW-w64.", "exit_code": 1})
            tmp = tempfile.mkdtemp(); exe = os.path.join(tmp, "program.exe")
            if file_path and os.path.isfile(file_path):
                src = file_path; wd = os.path.dirname(file_path)
            else:
                src = os.path.join(tmp, "main.cpp"); Path(src).write_text(code, encoding="utf-8"); wd = tmp
            comp = subprocess.run([gpp, src, "-o", exe], capture_output=True, text=True, timeout=30, cwd=wd)
            if comp.returncode != 0:
                return jsonify({"status": "success", "stdout": "", "stderr": f"[C++ Compile Error]\n{comp.stderr}", "exit_code": comp.returncode})
            run = subprocess.run([exe], capture_output=True, text=True, timeout=30, cwd=wd)
            return jsonify({"status": "success", "stdout": run.stdout, "stderr": run.stderr, "exit_code": run.returncode})
        elif ext == ".java":
            javac = _find_executable("javac", [r"C:\Program Files\Java\jdk-17\bin\javac.exe", r"C:\Program Files\Java\jdk-21\bin\javac.exe"])
            java  = _find_executable("java",  [r"C:\Program Files\Java\jdk-17\bin\java.exe",  r"C:\Program Files\Java\jdk-21\bin\java.exe"])
            if not javac or not java:
                return jsonify({"status": "error", "stdout": "", "stderr": "[Notice] JDK not found. Install JDK 17+.", "exit_code": 1})
            m = re.search(r"(?:public\s+)?class\s+([A-Za-z0-9_]+)", code); cls = m.group(1) if m else "Main"
            if file_path and os.path.isfile(file_path):
                src = file_path; wd = os.path.dirname(file_path)
            else:
                tmp = tempfile.mkdtemp(); src = os.path.join(tmp, f"{cls}.java"); Path(src).write_text(code, encoding="utf-8"); wd = tmp
            comp = subprocess.run([javac, src], capture_output=True, text=True, timeout=30, cwd=wd)
            if comp.returncode != 0:
                return jsonify({"status": "success", "stdout": "", "stderr": f"[Java Compile Error]\n{comp.stderr}", "exit_code": comp.returncode})
            run = subprocess.run([java, "-cp", wd, cls], capture_output=True, text=True, timeout=30, cwd=wd)
            return jsonify({"status": "success", "stdout": run.stdout, "stderr": run.stderr, "exit_code": run.returncode})
        elif ext in {".js", ".ts"}:
            node = _find_executable("node")
            if not node:
                return jsonify({"status": "error", "stdout": "", "stderr": "[Notice] Node.js not found.", "exit_code": 1})
            if file_path and os.path.isfile(file_path):
                src = file_path; wd = os.path.dirname(file_path)
            else:
                tmp = tempfile.mkdtemp(); src = os.path.join(tmp, "script.js"); Path(src).write_text(code, encoding="utf-8"); wd = DEFAULT_WORKSPACE
            run = subprocess.run([node, src], capture_output=True, text=True, timeout=30, cwd=wd)
            return jsonify({"status": "success", "stdout": run.stdout, "stderr": run.stderr, "exit_code": run.returncode})
        else:
            return jsonify({"status": "error", "message": f"Execution not supported for '{ext}'"}), 400
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Execution timed out (30s)"}), 408
    except Exception as e:
        log.error(f"[IDE Run] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/memory", methods=["GET"])
def api_get_memory():
    return jsonify({"status": "success", "memories": load_memory()})

@app.route("/api/memory", methods=["POST"])
def api_add_memory():
    data = _json_object()
    fact = data.get("fact", "").strip()
    if not fact:
        return jsonify({"status": "error", "message": "No fact provided"}), 400
    add_memory_fact(fact)
    return jsonify({"status": "success", "memories": load_memory()})

@app.route("/api/memory/<mem_id>", methods=["DELETE"])
def api_delete_memory(mem_id):
    mems = load_memory()
    before = len(mems)
    mems = [m for m in mems if m.get("id") != mem_id]
    if len(mems) < before:
        save_memory(mems)
        return jsonify({"status": "success", "memories": mems})
    return jsonify({"status": "not_found"}), 404

@app.route("/api/memory/clear", methods=["POST"])
def api_clear_memory():
    save_memory([])
    return jsonify({"status": "success", "message": "All memories cleared."})

@app.route("/api/ollama/start", methods=["POST"])
def api_ollama_start():
    ollama_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    if not os.path.exists(ollama_path):
        return jsonify({"status": "error", "message": "Ollama not found."}), 404
    if model_router.is_ollama_online():
        return jsonify({"status": "already_running"})
    started = model_router.start_ollama_process(ollama_path)
    if started:
        log.info("[Ollama] Started by Master request.")
        return jsonify({"status": "started"})
    return jsonify({"status": "starting", "message": "Ollama is warming up, please wait a moment."})

@app.route("/api/models/route", methods=["POST"])
def api_route_model():
    data = _json_object()
    prompt = data.get("prompt", "")
    code = data.get("code", "")
    req_model = data.get("model")
    decision = model_router.route_task(prompt, code, requested_model=req_model)
    return jsonify({"status": "success", "decision": decision.to_dict()})


# ─────────────────────────────────────────────────────────────────────────────
# Background Task Endpoints (v5.2.0 Task Manager)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/tasks", methods=["POST"])
def api_submit_task():
    data = _json_object()
    task_type = data.get("type", "custom")
    payload = data.get("payload", {})

    if task_type == "image":
        prompt = payload.get("prompt", "")
        model = payload.get("model", "sdxl-turbo")
        width = min(payload.get("width", 512), config.limits.max_image_width)
        height = min(payload.get("height", 512), config.limits.max_image_height)
        steps = payload.get("steps", 4)

        def _run_img(task_ctx=None):
            if task_ctx:
                task_ctx.update_progress(10, f"Loading pipeline {model}...")
            pipe = load_image_pipeline(model)
            if not pipe:
                raise RuntimeError(f"Could not load image pipeline '{model}'")
            if task_ctx:
                task_ctx.update_progress(40, "Generating image...")
            img_res = pipe(prompt=prompt, num_inference_steps=steps, width=width, height=height).images[0]
            if task_ctx:
                task_ctx.update_progress(80, "Saving image...")
            fn = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
            fp = os.path.join(IMAGE_DIR, fn)
            img_res.save(fp)
            return {"filename": fn, "url": f"/static/images/{fn}"}

        task = task_manager.submit("image", _run_img)

    elif task_type == "web_search":
        query = payload.get("query", "")
        from agent_tools import tool_web_search
        task = task_manager.submit("web_search", tool_web_search, query)

    elif task_type == "chat":
        prompt = payload.get("prompt", "")
        model = payload.get("model", DEFAULT_MODEL)

        def _run_llm(task_ctx=None):
            if task_ctx:
                task_ctx.update_progress(20, "Querying Ollama...")
            resp = requests.post(
                f"{OLLAMA_API_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=config.ollama.timeout_seconds,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")

        task = task_manager.submit("chat", _run_llm)

    else:
        return jsonify({"status": "error", "message": f"Unsupported task type: {task_type}"}), 400

    return jsonify({"status": "queued", "task_id": task.id, "task": task.to_dict()}), 202


@app.route("/api/tasks", methods=["GET"])
def api_list_tasks():
    status = request.args.get("status")
    limit = safe_int(request.args.get("limit", "50"), default=50, minimum=1, maximum=200)
    return jsonify({"status": "success", "tasks": task_manager.list_tasks(status=status, limit=limit)})


@app.route("/api/tasks/<task_id>", methods=["GET"])
def api_get_task(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"status": "error", "message": "Task not found."}), 404
    return jsonify({"status": "success", "task": task.to_dict()})


@app.route("/api/tasks/<task_id>/cancel", methods=["POST"])
def api_cancel_task(task_id: str):
    cancelled = task_manager.cancel_task(task_id)
    if not cancelled:
        return jsonify({"status": "error", "message": "Task could not be cancelled or does not exist."}), 400
    return jsonify({"status": "success", "message": f"Task {task_id} cancellation requested."})


@app.route("/api/tasks/<task_id>/events", methods=["GET"])
def api_task_events(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"status": "error", "message": "Task not found."}), 404

    def event_stream():
        initial = {"event": "snapshot", "task": task.to_dict()}
        yield f"data: {json.dumps(initial)}\n\n"
        while True:
            try:
                evt = task.events_queue.get(timeout=1.0)
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("status") in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    break
            except queue.Empty:
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    break
                yield ": keepalive\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    ip = get_local_ip()
    log.info("=" * 60)
    log.info(f"  Manas Ciel Studio v{APP_VERSION}")
    log.info(f"  Laptop  -> http://localhost:{config.server.port}")
    log.info(f"  Network -> http://{ip}:{config.server.port}")
    log.info("=" * 60)
    app.run(host=config.server.host, port=config.server.port, debug=config.server.debug, threaded=True)
