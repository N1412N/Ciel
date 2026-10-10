"""
model_router.py -- Dynamic Ollama Model Router for Ciel Desktop Assistant
Performs real-time availability checks, capability mapping, task classification,
and graceful fallback routing without blocking threads.
"""

from dataclasses import dataclass
import logging
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from config import config

log = logging.getLogger("ciel.router")


@dataclass
class RouteDecision:
    model: str
    reason: str
    fallback_used: bool
    available: bool
    label: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "reason": self.reason,
            "fallback_used": self.fallback_used,
            "available": self.available,
            "label": self.label,
        }


class ModelRouter:
    """
    Intelligently routes tasks to the best Ollama model:
    - Speed Engine (e.g. qwen2.5:1.5b) for short commands, greetings, basic math
    - Reasoning Engine (e.g. deepseek-r1:7b) for deep mathematical / multi-step logic
    - Primary Intelligence Engine (e.g. qwen2.5-coder:7b) for coding, autonomous tasks, computer ops
    """

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or config.ollama.api_url
        self._cache_lock = threading.Lock()
        self._installed_models_cache: Set[str] = set()
        self._last_cache_time: float = 0.0
        self._cache_ttl_seconds: float = 15.0
        self._start_lock = threading.Lock()

    def is_ollama_online(self, timeout: float = 1.5) -> bool:
        """Check if Ollama local server is responding to HTTP requests."""
        try:
            resp = requests.get(f"{self.api_url}/api/tags", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    def get_installed_models(self, force_refresh: bool = False, timeout: float = 2.0) -> Set[str]:
        """Return the set of installed model tags in Ollama with short TTL caching."""
        with self._cache_lock:
            now = time.time()
            if not force_refresh and (now - self._last_cache_time < self._cache_ttl_seconds):
                return set(self._installed_models_cache)

            try:
                resp = requests.get(f"{self.api_url}/api/tags", timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    models = set()
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        if name:
                            models.add(name.lower())
                            if name.endswith(":latest"):
                                models.add(name[:-7].lower())
                    self._installed_models_cache = models
                    self._last_cache_time = now
                    return set(models)
            except Exception as e:
                log.debug(f"[ModelRouter] Could not query Ollama tags: {e}")

            return set(self._installed_models_cache)

    def is_model_installed(self, model_name: str) -> bool:
        """Check if a specific model is installed and ready."""
        if not model_name or not isinstance(model_name, str):
            return False
        clean = model_name.strip().lower()
        installed = self.get_installed_models()
        return clean in installed or f"{clean}:latest" in installed

    def classify_task(self, prompt: str, active_code: str = "") -> Tuple[str, str, str]:
        """
        Classifies prompt according to master routing rule:
        - Deep mathematical proof / complex logic -> "qwen3:latest" (Reasoning Engine)
        - Heavy coding, multi-file software engineering -> "qwen2.5-coder:7b" (Primary Intelligence Engine)
        - Conversational questions, greetings, desktop queries, and general chat -> "qwen2.5-coder:1.5b" (Speed Engine, ~0.6s latency)
        """
        text = (prompt or "").strip().lower()

        # 1. Deep reasoning -> "qwen3:latest"
        deep_keywords = [
            "think deeply", "step by step proof", "complex reasoning",
            "mathematical proof", "deep analysis", "prove that", "derive"
        ]
        if any(k in text for k in deep_keywords):
            return "qwen3:latest", "Deep reasoning", "Qwen 3 (Reasoning Engine)"

        # 2. Heavy software engineering, refactoring, backend building -> "qwen2.5-coder:7b"
        coding_signals = [
            "build a", "write a python", "write a class", "create a backend", "fastapi",
            "refactor", "debug this", "implement an algorithm", "unit test", "write code",
            "pull request", "django", "flask app", "react component", "fullstack"
        ]
        has_heavy_code = bool(active_code) or any(s in text for s in coding_signals) or (len(text.split()) > 25 and any(w in text for w in ["code", "function", "class", "script", "file"]))
        if has_heavy_code:
            return "qwen2.5-coder:7b", "General coding and desktop intelligence task", "7B Coder (Primary Intelligence Engine)"

        # 3. All conversational inquiries, greetings, desktop tasks, and short questions -> "qwen2.5-coder:1.5b" (Speed Engine)
        return "qwen2.5-coder:1.5b", "Simple command", "1.5B Coder (Speed Engine)"

    def route_task(self, prompt: str, active_code: str = "", requested_model: Optional[str] = None) -> RouteDecision:
        """
        Selects the best model, checks Ollama connectivity and installed models,
        and applies fallback routing if unavailable.
        """
        online = self.is_ollama_online()

        if requested_model:
            preferred = requested_model.strip()
            reason = f"Explicitly requested model: {requested_model}"
            label = f"Custom ({requested_model})"
        else:
            preferred, reason, label = self.classify_task(prompt, active_code)

        if not online:
            log.warning(f"[ModelRouter] Ollama is currently offline. Chosen: {preferred}")
            return RouteDecision(
                model=preferred,
                reason=f"{reason} (Ollama appears offline)",
                fallback_used=False,
                available=False,
                label=label,
            )

        installed = self.get_installed_models()
        is_available = self.is_model_installed(preferred)

        if is_available:
            # Memory optimization: unload other inactive models if system RAM is tight to prevent disk swapping
            try:
                import psutil
                if psutil.virtual_memory().available / (1024 ** 3) < 2.5:
                    resp_ps = requests.get(f"{self.api_url}/api/ps", timeout=0.8)
                    if resp_ps.status_code == 200:
                        for m in resp_ps.json().get("models", []):
                            m_name = m.get("name", "")
                            if m_name and m_name.lower() != preferred.lower():
                                requests.post(f"{self.api_url}/api/generate", json={"model": m_name, "keep_alive": 0}, timeout=1.0)
                                log.info(f"[ModelRouter] Unloaded inactive model '{m_name}' to free RAM.")
            except Exception as e:
                log.debug(f"[ModelRouter] RAM optimize check skipped: {e}")

            log.info(f"[ModelRouter] Selected '{preferred}' for '{reason}'")
            return RouteDecision(
                model=preferred,
                reason=reason,
                fallback_used=False,
                available=True,
                label=label,
            )

        # Fallback: if preferred is not installed, find best installed fallback
        fallback = None
        for candidate in [config.ollama.default_model, config.ollama.fast_model]:
            if self.is_model_installed(candidate):
                fallback = candidate
                break

        if not fallback and installed:
            fallback = sorted(installed)[0]

        if fallback:
            log.warning(f"[ModelRouter] Preferred model '{preferred}' not found. Falling back to '{fallback}'.")
            return RouteDecision(
                model=fallback,
                reason=f"{reason} (Fallback: '{preferred}' not installed)",
                fallback_used=True,
                available=True,
                label=f"Fallback: {fallback}",
            )

        # Neither preferred nor fallbacks found in tags, use preferred as best effort
        return RouteDecision(
            model=preferred,
            reason=f"{reason} (Model not confirmed in local tags)",
            fallback_used=False,
            available=False,
            label=label,
        )

    def start_ollama_process(self, ollama_executable_path: str) -> bool:
        """Starts Ollama in background with singleton process lock."""
        with self._start_lock:
            if self.is_ollama_online(timeout=1.0):
                return True
            try:
                subprocess.Popen(
                    [ollama_executable_path, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                time.sleep(2)
                return self.is_ollama_online(timeout=3.0)
            except Exception as e:
                log.error(f"[ModelRouter] Failed to start Ollama process: {e}")
                return False


model_router = ModelRouter()
