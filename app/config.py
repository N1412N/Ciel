"""
config.py -- Central Typed Configuration for Ciel Desktop Assistant
Loads configuration from environment variables (or optional .env file)
with safe defaults and validates settings at startup.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

APP_DIR = Path(__file__).resolve().parent
CIEL_ROOT = APP_DIR.parent


def _load_dotenv(dotenv_path: Path):
    """Simple, zero-dependency .env reader that populates os.environ if not already set."""
    if not dotenv_path.is_file():
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


# Automatically load .env if present at project root
_load_dotenv(CIEL_ROOT / ".env")


def _get_env_str(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


def _get_env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


def _get_env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class ServerConfig:
    host: str = field(default_factory=lambda: _get_env_str("CIEL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _get_env_int("CIEL_PORT", 5000))
    debug: bool = field(default_factory=lambda: _get_env_bool("CIEL_DEBUG", False))
    version: str = "5.4.0"
    log_level: str = field(default_factory=lambda: _get_env_str("CIEL_LOG_LEVEL", "INFO").upper())


@dataclass
class PathConfig:
    app_dir: Path = APP_DIR
    ciel_root: Path = CIEL_ROOT
    workspace_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("CIEL_WORKSPACE", str(CIEL_ROOT))).resolve()
    )
    chats_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("CIEL_CHATS_DIR", str(CIEL_ROOT / "chats"))).resolve()
    )
    image_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("CIEL_IMAGE_DIR", str(APP_DIR / "static" / "images"))).resolve()
    )
    hf_home: Path = field(
        default_factory=lambda: Path(os.environ.get("HF_HOME", str(CIEL_ROOT / "models" / "huggingface"))).resolve()
    )
    ollama_models: Path = field(
        default_factory=lambda: Path(os.environ.get("OLLAMA_MODELS", str(CIEL_ROOT / "models" / "ollama"))).resolve()
    )

    @property
    def conversations_file(self) -> Path:
        return self.chats_dir / "conversations.json"

    @property
    def memory_file(self) -> Path:
        return self.chats_dir / "memory.json"

    @property
    def pinned_items_file(self) -> Path:
        return self.chats_dir / "pinned_items.json"


@dataclass
class OllamaConfig:
    api_url: str = field(default_factory=lambda: _get_env_str("OLLAMA_API_URL", "http://127.0.0.1:11434"))
    default_model: str = field(default_factory=lambda: _get_env_str("OLLAMA_DEFAULT_MODEL", "qwen2.5-coder:7b"))
    fast_model: str = field(default_factory=lambda: _get_env_str("OLLAMA_FAST_MODEL", "qwen2.5-coder:1.5b"))
    reasoning_model: str = field(default_factory=lambda: _get_env_str("OLLAMA_REASONING_MODEL", "qwen3:latest"))
    vision_model: str = field(default_factory=lambda: _get_env_str("OLLAMA_VISION_MODEL", "llava:7b"))
    timeout_seconds: int = field(default_factory=lambda: _get_env_int("OLLAMA_TIMEOUT_SECONDS", 120))


@dataclass
class VoiceConfig:
    tts_voice: str = field(default_factory=lambda: _get_env_str("CIEL_TTS_VOICE", "en-US-AriaNeural"))
    tts_pitch: str = field(default_factory=lambda: _get_env_str("CIEL_TTS_PITCH", "+14Hz"))
    tts_rate: str = field(default_factory=lambda: _get_env_str("CIEL_TTS_RATE", "+5%"))
    wake_timeout_seconds: int = field(default_factory=lambda: _get_env_int("CIEL_WAKE_TIMEOUT", 10))
    whisper_model: str = field(default_factory=lambda: _get_env_str("CIEL_WHISPER_MODEL", "base.en"))


@dataclass
class LimitsConfig:
    command_timeout_seconds: int = field(default_factory=lambda: _get_env_int("CIEL_COMMAND_TIMEOUT", 30))
    permission_timeout_seconds: int = field(default_factory=lambda: _get_env_int("CIEL_PERMISSION_TIMEOUT", 120))
    max_image_width: int = field(default_factory=lambda: _get_env_int("CIEL_MAX_IMAGE_WIDTH", 1024))
    max_image_height: int = field(default_factory=lambda: _get_env_int("CIEL_MAX_IMAGE_HEIGHT", 1024))
    max_code_size_chars: int = field(default_factory=lambda: _get_env_int("CIEL_MAX_CODE_SIZE", 500_000))
    max_output_length_chars: int = field(default_factory=lambda: _get_env_int("CIEL_MAX_OUTPUT_LENGTH", 100_000))


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)

    def validate(self) -> List[str]:
        errors = []
        if self.server.port < 1024 or self.server.port > 65535:
            errors.append(f"Invalid server port: {self.server.port} (must be between 1024 and 65535)")
        if not self.ollama.api_url.startswith(("http://", "https://")):
            errors.append(f"Invalid Ollama URL: {self.ollama.api_url} (must start with http:// or https://)")
        if self.limits.command_timeout_seconds <= 0:
            errors.append("Command timeout must be > 0 seconds")
        if self.limits.permission_timeout_seconds <= 0:
            errors.append("Permission timeout must be > 0 seconds")
        return errors

    def ensure_directories(self):
        for p in (self.paths.chats_dir, self.paths.image_dir, self.paths.workspace_dir):
            p.mkdir(parents=True, exist_ok=True)


config = AppConfig()
config.ensure_directories()
