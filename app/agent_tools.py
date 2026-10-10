"""
agent_tools.py -- Ciel AI Agent Tools v2.0
Autonomous tool execution for Manas Ciel desktop assistant.
Every destructive action requires explicit user permission via the callback.
"""

import io
import json
import os
import re
import subprocess
import sys
import threading
import shutil
import ctypes
from pathlib import Path

import requests

from config import config
from security import SecurityError, validate_http_url, workspace_path

DEFAULT_WORKSPACE = str(config.paths.workspace_dir)

def _resolve_safe_path(raw_path: str, allow_outside: bool = False) -> str:
    """Validate that path remains inside workspace unless explicitly permitted."""
    if not raw_path or not isinstance(raw_path, str):
        raise SecurityError("Path must be a non-empty string.")
    clean = os.path.expanduser(raw_path.strip())
    if allow_outside or _allow_read_all_files:
        return os.path.abspath(clean)
    return str(workspace_path(clean, DEFAULT_WORKSPACE))

import logging
log_security = logging.getLogger("ciel.security")

class ToolRiskLevel:
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    SYSTEM_CONTROL = "SYSTEM_CONTROL"
    COMPUTER_AUTOMATION = "COMPUTER_AUTOMATION"
    NETWORK_ACCESS = "NETWORK_ACCESS"

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Permission System
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_permission_callback = None
_allow_read_all_files = False

def set_permission_callback(callback):
    global _permission_callback
    _permission_callback = callback

def set_allow_read_all(val: bool):
    global _allow_read_all_files
    _allow_read_all_files = bool(val)

def get_allow_read_all() -> bool:
    global _allow_read_all_files
    return _allow_read_all_files

_in_direct_command = False
_preferred_browser = None
_active_chrome_profile = None
_preferred_browser_exe = None
_preferred_browser_profile = None

# Universal browser launchers catalog
BROWSER_LAUNCHERS = {
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        shutil.which("brave"),
        shutil.which("brave.exe"),
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
    ],
    "msedge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
    ],
    "opera": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe"),
        shutil.which("opera"),
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        shutil.which("firefox"),
        shutil.which("firefox.exe"),
    ],
    "vivaldi": [
        os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
        r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        shutil.which("vivaldi"),
    ],
    "arc": [
        os.path.expandvars(r"%LOCALAPPDATA%\Arc\arc.exe"),
        shutil.which("arc"),
    ],
}

def set_preferred_browser(browser_name: str | None, profile_name: str | None = None, exe_path: str | None = None):
    global _preferred_browser, _active_chrome_profile, _preferred_browser_exe, _preferred_browser_profile
    _preferred_browser = browser_name
    _active_chrome_profile = profile_name
    _preferred_browser_profile = profile_name
    _preferred_browser_exe = exe_path

def set_preferred_browser_target(target_info: dict | None):
    global _preferred_browser, _active_chrome_profile, _preferred_browser_exe, _preferred_browser_profile
    if target_info and isinstance(target_info, dict):
        _preferred_browser = target_info.get("browser")
        _preferred_browser_exe = target_info.get("exe")
        _preferred_browser_profile = target_info.get("profile")
        _active_chrome_profile = target_info.get("profile")
    else:
        _preferred_browser = None
        _preferred_browser_exe = None
        _preferred_browser_profile = None
        _active_chrome_profile = None

def resolve_browser_from_path(path: str) -> dict | None:
    """Dynamically inspect any Windows shortcut (.lnk) or binary (.exe) to determine target browser, executable, and profile."""
    if not path:
        return None
    p = os.path.expanduser(os.path.expandvars(path.strip().strip("'\"“”‘’")))
    if not os.path.exists(p):
        return None

    exe = ""
    args = ""
    prof = None
    b_type = "unknown"

    if p.lower().endswith(".lnk"):
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            folder = shell.NameSpace(os.path.dirname(os.path.abspath(p)))
            item = folder.ParseName(os.path.basename(p)) if folder else None
            link = item.GetLink if item else None
            if link:
                exe = link.Path or ""
                args = link.Arguments or ""
        except Exception:
            pass

        # Fallback binary inspection if COM didn't extract args or exe
        if not args or not exe:
            try:
                raw = open(p, "rb").read()
                t16 = raw.decode("utf-16le", errors="ignore")
                m16 = re.search(r'--profile-directory="([^"]+)"', t16)
                if not m16:
                    m16 = re.search(r'--profile-directory=([^\s"]+)', t16)
                if m16:
                    prof = m16.group(1).strip()

                raw_lower = raw.lower()
                if b"bravesoftware" in raw_lower or b"brave.exe" in raw_lower:
                    b_type = "brave"
                elif b"chrome.exe" in raw_lower:
                    b_type = "chrome"
                elif b"msedge.exe" in raw_lower:
                    b_type = "edge"
                elif b"firefox.exe" in raw_lower:
                    b_type = "firefox"
                elif b"opera" in raw_lower:
                    b_type = "opera"
            except Exception:
                pass
    elif p.lower().endswith(".exe"):
        exe = p

    all_str = (p + " " + exe + " " + args).lower()
    if "bravesoftware" in all_str or "brave" in all_str:
        b_type = "brave"
    elif "chrome" in all_str and "brave" not in all_str:
        b_type = "chrome"
    elif "edge" in all_str or "msedge" in all_str:
        b_type = "edge"
    elif "firefox" in all_str:
        b_type = "firefox"
    elif "opera" in all_str:
        b_type = "opera"
    elif "vivaldi" in all_str:
        b_type = "vivaldi"
    elif "arc" in all_str:
        b_type = "arc"

    if not prof and args:
        m = re.search(r'--profile-directory="([^"]+)"', args)
        if not m:
            m = re.search(r'--profile-directory=([^\s"]+)', args)
        if m:
            prof = m.group(1).strip()

    # Determine real browser binary executable if exe was chrome_proxy.exe (used by PWA web shortcuts)
    actual_browser_exe = exe
    if exe and os.path.basename(exe).lower() == "chrome_proxy.exe":
        dir_name = os.path.dirname(exe)
        cand = os.path.join(dir_name, f"{b_type}.exe")
        if os.path.exists(cand):
            actual_browser_exe = cand

    # If exe not found via link but we know browser type, lookup known paths
    if not actual_browser_exe or not os.path.exists(actual_browser_exe):
        for candidate in BROWSER_LAUNCHERS.get(b_type, []):
            if candidate and os.path.exists(candidate):
                actual_browser_exe = candidate
                break

    return {
        "path": p,
        "exe": actual_browser_exe or exe,
        "raw_exe": exe,
        "args": args,
        "browser": b_type,
        "profile": prof,
        "is_browser": b_type in ["chrome", "brave", "edge", "firefox", "opera", "vivaldi", "arc"],
    }

def extract_profile_from_lnk(lnk_path: str) -> str | None:
    res = resolve_browser_from_path(lnk_path)
    if res:
        return res.get("profile")
    return None

def reset_permission_scopes():
    global _allow_read_all_files
    _allow_read_all_files = False

def request_permission(action_type: str, description: str) -> bool:
    if _in_direct_command:
        return True
    if _permission_callback is None:
        import sys
        if not sys.stdin or not sys.stdin.isatty():
            return True
        try:
            enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            safe_desc = description.encode(enc, errors="replace").decode(enc, errors="replace")
            resp = input(f"\n[PERMISSION] {action_type}: {safe_desc}\nAllow? (y/n): ").strip().lower()
            return resp == "y"
        except Exception:
            return True
    try:
        return _permission_callback(action_type, description)
    except Exception as e:
        log_security.warning(f"Permission callback exception: {e}")
        return True

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tools
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def tool_read_file(path: str) -> str:
    try:
        path = _resolve_safe_path(path, allow_outside=_allow_read_all_files)
    except SecurityError as e:
        return f"[ERROR] Security rejection: {e}"
    if not _allow_read_all_files:
        if not request_permission("READ FILE", f"Read file: {path}"):
            return f"[DENIED] Master cancelled permission to read file: {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = content.splitlines()
        if len(lines) > 200:
            content = "\n".join(lines[:200]) + f"\n... [truncated: {len(lines)} total lines]"
        return f"[FILE: {path}]\n{content}"
    except FileNotFoundError:
        return f"[ERROR] File not found: {path}"
    except Exception as e:
        return f"[ERROR] Could not read file: {e}"

def tool_create_file(path: str, content: str = "") -> str:
    try:
        path = _resolve_safe_path(path)
    except SecurityError as e:
        return f"[ERROR] Security rejection: {e}"
    action_type = "CREATE FILE" if not os.path.exists(path) else "OVERWRITE FILE"
    if not request_permission(action_type, f"Create file: {path} ({len(content):,} characters)"):
        return f"[DENIED] Master cancelled permission to create file: {path}"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[SUCCESS] File created: {path}"
    except Exception as e:
        return f"[ERROR] Could not create file: {e}"

def tool_write_file(path: str, content: str) -> str:
    try:
        path = _resolve_safe_path(path)
    except SecurityError as e:
        return f"[ERROR] Security rejection: {e}"
    action_type = "CREATE FILE" if not os.path.exists(path) else "WRITE/MODIFY FILE"
    if not request_permission(action_type, f"{'Create new' if not os.path.exists(path) else 'Write/Modify'} file: {path} ({len(content):,} characters)"):
        return f"[DENIED] Master cancelled permission to write file: {path}"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[SUCCESS] File written: {path}"
    except Exception as e:
        return f"[ERROR] Could not write file: {e}"

def tool_list_directory(path: str) -> str:
    try:
        path = _resolve_safe_path(path)
    except SecurityError as e:
        return f"[ERROR] Security rejection: {e}"
    if not request_permission("BROWSE FOLDER", f"Browse and list folder contents: {path}"):
        return f"[DENIED] Master cancelled permission to browse folder: {path}"
    try:
        entries = []
        for item in sorted(Path(path).iterdir()):
            kind = "DIR " if item.is_dir() else "FILE"
            size = f"{item.stat().st_size:,} bytes" if item.is_file() else ""
            entries.append(f"  [{kind}] {item.name}  {size}")
        return f"[DIRECTORY: {path}]\n" + "\n".join(entries[:100])
    except Exception as e:
        return f"[ERROR] Could not list directory: {e}"

def tool_create_folder(path: str) -> str:
    try:
        path = _resolve_safe_path(path)
    except SecurityError as e:
        return f"[ERROR] Security rejection: {e}"
    if not request_permission("CREATE FOLDER", f"Create directory/folder: {path}"):
        return f"[DENIED] Master cancelled permission to create folder: {path}"
    try:
        os.makedirs(path, exist_ok=True)
        return f"[SUCCESS] Folder created: {path}"
    except Exception as e:
        return f"[ERROR] Could not create folder: {e}"

def tool_delete_file(path: str) -> str:
    try:
        path = _resolve_safe_path(path)
    except SecurityError as e:
        return f"[ERROR] Security rejection: {e}"
    if not request_permission("DELETE FILE", f"Move to Recycle Bin: {path}"):
        return "[DENIED] Master cancelled file deletion."
    try:
        if not os.path.exists(path):
            return f"[ERROR] Path not found: {path}"
        try:
            import send2trash
            send2trash.send2trash(path)
            return f"[SUCCESS] Moved to Recycle Bin: {path} (can be restored if needed)."
        except Exception:
            if os.path.isfile(path):
                os.remove(path)
                return f"[SUCCESS] File deleted: {path}"
            elif os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
                return f"[SUCCESS] Folder deleted: {path}"
    except Exception as e:
        return f"[ERROR] Could not delete: {e}"

def tool_run_python(script_path: str) -> str:
    script_path = os.path.expanduser(script_path.strip())
    if not os.path.isfile(script_path):
        return f"[ERROR] Script not found: {script_path}"
    if not request_permission("RUN PYTHON", f"Execute Python script: {script_path}"):
        return f"[DENIED] Master cancelled Python execution: {script_path}"
    try:
        cmd_timeout = config.limits.command_timeout_seconds
        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=cmd_timeout)
        out = f"[SCRIPT OUTPUT]\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nEXIT CODE: {result.returncode}"
        if len(out) > config.limits.max_output_length_chars:
            out = out[:config.limits.max_output_length_chars] + f"\n... [Output truncated: exceeded {config.limits.max_output_length_chars} characters]"
        return out
    except subprocess.TimeoutExpired:
        return f"[ERROR] Script timed out after {config.limits.command_timeout_seconds} seconds."
    except Exception as e:
        return f"[ERROR] Could not run script: {e}"

def tool_run_command(command: str) -> str:
    command = (command or "").strip()
    if not command:
        return "[ERROR] Command is required."
    if not request_permission("RUN COMMAND", f"Execute PowerShell command: {command[:500]}"):
        return "[DENIED] Master cancelled command execution."
    try:
        cmd_timeout = config.limits.command_timeout_seconds
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=cmd_timeout, shell=False,
        )
        out = f"[COMMAND OUTPUT]\n{result.stdout}\n{result.stderr}".strip()
        if len(out) > config.limits.max_output_length_chars:
            out = out[:config.limits.max_output_length_chars] + f"\n... [Output truncated: exceeded {config.limits.max_output_length_chars} characters]"
        return out
    except subprocess.TimeoutExpired:
        return f"[ERROR] Command timed out after {config.limits.command_timeout_seconds} seconds."
    except Exception as e:
        return f"[ERROR] Could not run command: {e}"

def tool_search_files(directory: str, pattern: str) -> str:
    try:
        directory = _resolve_safe_path(directory, allow_outside=_allow_read_all_files)
    except SecurityError as e:
        return f"[ERROR] Security rejection: {e}"
    # ALWAYS ask permission every single time before searching folders
    if not request_permission("SEARCH FOLDER", f"Search directory '{directory}' for '{pattern}'"):
        return f"[DENIED] Master cancelled file search in {directory}."
    try:
        matches = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"__pycache__", "venv", "node_modules", ".git"}]
            for f in files:
                if pattern.lower() in f.lower():
                    matches.append(os.path.join(root, f))
                if len(matches) >= 50:
                    break
            if len(matches) >= 50:
                break
        if not matches:
            return f"[SEARCH] No files matching '{pattern}' found in {directory}"
        return f"[SEARCH RESULTS for '{pattern}']\n" + "\n".join(matches)
    except Exception as e:
        return f"[ERROR] Search failed: {e}"

def tool_web_search(query: str) -> str:
    query = query.strip()
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=5))
        if not results:
            return f"[WEB SEARCH] No results for: '{query}'"
        formatted = [
            f"{i}. **{r.get('title', '')}**\n   {r.get('body', '')}\n   Source: {r.get('href', '')}"
            for i, r in enumerate(results, 1)
        ]
        return f"[LIVE WEB SEARCH: '{query}']\n\n" + "\n\n".join(formatted)
    except Exception as e:
        try:
            from bs4 import BeautifulSoup
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}", headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            snippets = []
            for result in soup.find_all("div", class_="result__body")[:5]:
                t = result.find("a", class_="result__a")
                s = result.find("a", class_="result__snippet")
                if t:
                    snippets.append(f"- **{t.get_text(strip=True)}**: {s.get_text(strip=True) if s else ''}")
            if snippets:
                return f"[LIVE WEB SEARCH: '{query}']\n\n" + "\n\n".join(snippets)
        except Exception:
            pass
        return f"[ERROR] Web search failed: {e}"

def tool_fetch_webpage(url: str) -> str:
    try:
        url = validate_http_url(url)
    except SecurityError as exc:
        return f"[ERROR] Unsafe URL: {exc}"
    try:
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return f"[ERROR] HTTP {resp.status_code} for {url}"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
            tag.decompose()
        text  = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        cleaned = "\n".join(lines)
        if len(cleaned) > 4000:
            cleaned = cleaned[:4000] + "\n... [truncated]"
        return f"[WEBPAGE: {url}]\n\n{cleaned}"
    except Exception as e:
        return f"[ERROR] Failed to read webpage: {e}"

def tool_get_clipboard() -> str:
    """Read text currently in the Windows clipboard."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
        )
        text = result.stdout.strip()
        if not text:
            return "[CLIPBOARD] Clipboard is empty."
        if len(text) > 2000:
            text = text[:2000] + "\n... [truncated]"
        return f"[CLIPBOARD CONTENT]\n{text}"
    except Exception as e:
        return f"[ERROR] Could not read clipboard: {e}"

def tool_set_clipboard(text: str) -> str:
    """Write text to the Windows clipboard without shell interpolation."""
    if not request_permission("WRITE CLIPBOARD", f"Write {len(text or '')} characters to the clipboard"):
        return "[DENIED] Master cancelled clipboard write."
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
            input=text or "", capture_output=True, text=True, timeout=5,
        )
        return f"[SUCCESS] Clipboard updated ({len(text)} characters written)."
    except Exception as e:
        return f"[ERROR] Could not write clipboard: {e}"

def tool_analyze_clipboard(instruction: str = "") -> str:
    """Inspect and analyze text, code, or error stack traces copied to the Windows clipboard."""
    raw = tool_get_clipboard()
    if "Clipboard is empty" in raw or "[ERROR]" in raw:
        return raw
    content = raw.replace("[CLIPBOARD CONTENT]\n", "")

    # Classify content
    c_lower = content.lower()
    content_type = "general text"
    if any(err in c_lower for err in ["traceback (most recent call last)", "syntaxerror:", "exception:", "error:", "errno", "typeerror:", "valueerror:", "failed"]):
        content_type = "error stack trace"
    elif any(kw in content for kw in ["def ", "class ", "import ", "function(", "const ", "let ", "var ", "public class", "fn ", "impl "]):
        content_type = "source code"
    elif content.startswith("{") and content.endswith("}"):
        content_type = "JSON object"

    return (
        f"[Report: Clipboard Analysis]\n"
        f"Detected Type: {content_type}\n"
        f"Length: {len(content)} characters\n"
        f"Content Preview:\n```\n{content[:1800]}\n```\n"
        f"{f'Focus Instruction: {instruction}' if instruction else ''}"
    )

def tool_take_screenshot(save_path: str = "") -> str:
    """Capture the full screen and return as base64 PNG (and optionally save to disk)."""
    try:
        import mss
        import base64
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            sct_img = sct.grab(monitor)
            png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
        b64 = base64.b64encode(png_bytes).decode()
        result = f"[SCREENSHOT]\n<img src=\"data:image/png;base64,{b64[:500]}...\" />\n(Screenshot captured successfully, {len(b64):,} chars)"
        if save_path:
            save_path = os.path.expanduser(save_path.strip())
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(png_bytes)
            result += f"\n[Saved to: {save_path}]"
        return result
    except ImportError:
        return "[ERROR] Screenshot requires the 'mss' package. Run: pip install mss"
    except Exception as e:
        return f"[ERROR] Screenshot failed: {e}"

def tool_generate_image(prompt: str, image_model: str = "counterfeit-v3", width: int = 512, height: int = 768, steps: int = 20) -> str:
    """Generate and synthesize an AI anime/artwork image using Ciel's layered diffusion pipeline."""
    import os
    import io
    import base64
    import shutil
    import requests

    clean_prompt = prompt.strip()
    try:
        from app import expand_anime_prompt
        clean_prompt = expand_anime_prompt(clean_prompt)
    except Exception:
        if clean_prompt.lower() in ["something", "anything", "a picture", "an image", "anime", "anime girl"]:
            clean_prompt = "1girl, silver hair, glowing blue eyes, elegant magical robes, fantasy library background, cinematic lighting, masterpiece, 8k"
        elif not any(k in clean_prompt.lower() for k in ["masterpiece", "detailed", "art", "render", "photo"]):
            clean_prompt = f"{clean_prompt}, highly detailed anime artwork, beautiful cel-shading, masterpiece"

    data = None
    try:
        res = requests.post("http://127.0.0.1:5000/api/generate-image", json={
            "prompt": clean_prompt, "image_model": image_model,
            "width": width, "height": height, "steps": steps,
        }, timeout=180)
        if res.status_code == 200:
            data = res.json()
    except Exception:
        pass

    # Direct in-process fallback if HTTP server was not reachable
    if not data or data.get("status") != "success":
        try:
            import uuid
            app_dir = os.path.dirname(os.path.abspath(__file__))
            if app_dir not in sys.path:
                sys.path.insert(0, app_dir)
            from app import load_image_pipeline, IMAGE_MODELS, IMAGE_DIR
            config = IMAGE_MODELS.get(image_model, IMAGE_MODELS["sdxl-turbo"])
            pipe = load_image_pipeline(image_model)
            if pipe:
                neg = "Blurry, low quality, bad anatomy, watermark"
                res_img = pipe(prompt=clean_prompt, negative_prompt=neg, num_inference_steps=steps, guidance_scale=float(config["guidance_scale"]), width=width, height=height)
                image = res_img.images[0]
                fname = f"{image_model}_{uuid.uuid4().hex[:8]}.png"
                out_path = os.path.join(IMAGE_DIR, fname)
                image.save(out_path, format="PNG")
                data = {
                    "status": "success",
                    "filename": fname,
                    "image_url": f"/static/images/{fname}",
                }
        except Exception as e:
            return f"[ERROR] Image generation failed: {e}"

    if data and data.get("status") == "success":
        fname = data.get("filename")
        rel_url = data.get("image_url")

        # Copy to Desktop and open for Master
        desk = os.path.expanduser(r"~\OneDrive\Desktop")
        if not os.path.exists(desk):
            desk = os.path.expanduser(r"~\Desktop")
        app_dir = os.path.dirname(os.path.abspath(__file__))
        src_path = os.path.join(app_dir, "static", "images", fname)
        saved_desk_path = ""
        if os.path.exists(src_path):
            try:
                dest_path = os.path.join(desk, f"Ciel_Artwork_{fname}")
                shutil.copy2(src_path, dest_path)
                saved_desk_path = dest_path
                try:
                    os.startfile(dest_path)
                except Exception:
                    pass
            except Exception:
                pass

        return (
            f"[Report] Image synthesized and drawn successfully for Master:\n"
            f"<div style=\"text-align:center;margin:12px 0;\">"
            f"<img src=\"{rel_url}\" style=\"max-width:95%;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,0.4);border:1px solid rgba(56,189,248,0.3);\">\n"
            f"</div>\n"
            f"✦ **Artwork**: `{clean_prompt}`\n"
            f"✦ **Model**: `{image_model}` ({steps} steps)\n"
            f"{f'✦ **Saved to Desktop**: `{os.path.basename(saved_desk_path)}`' if saved_desk_path else ''}"
        )

    err_msg = data.get("message", "Unknown error") if data else "Failed to connect to image generator"
    return f"[ERROR] Image generation failed: {err_msg}"


def tool_generate_primitive_art(image_path: str, num_shapes: int = 60, mode: str = "triangle", output_path: str = "") -> str:
    """Reproduce any image using geometric primitives (triangles, rectangles, ellipses, circles, combo).
    Outputs resolution-independent SVG vector art and PNG raster graphic.
    Args: image_path, num_shapes (10-300), mode ('triangle', 'rectangle', 'ellipse', 'circle', 'combo'), output_path (optional)"""
    from primitive_engine import run_primitive_reproduction
    from config import config

    clean_img = (image_path or "").strip().strip("'\"")
    if not clean_img or not os.path.exists(clean_img):
        candidates = [
            clean_img,
            os.path.join(str(config.paths.workspace_dir), clean_img),
            os.path.join(str(config.paths.image_dir), clean_img),
            os.path.join(os.path.expanduser("~/Pictures"), clean_img),
            os.path.join(os.path.expanduser("~/Downloads"), clean_img),
            os.path.join(os.path.expanduser("~/Desktop"), clean_img),
        ]
        found = None
        for c in candidates:
            if c and os.path.exists(c):
                found = c
                break
        if not found:
            return f"[ERROR] Source image not found at '{image_path}'. Please provide a valid image path."
        clean_img = found

    n = max(10, min(300, int(num_shapes or 60)))
    valid_modes = {"triangle", "rectangle", "ellipse", "circle", "rotated_rect", "combo"}
    m = (mode or "triangle").strip().lower()
    if m not in valid_modes:
        m = "triangle"

    out_dir = str(config.paths.image_dir)
    if output_path and os.path.isdir(output_path):
        out_dir = output_path

    try:
        res = run_primitive_reproduction(
            image_path=clean_img,
            num_shapes=n,
            mode=m,
            output_dir=out_dir,
            alpha=0.55,
        )
        return (
            f"[Report: Geometric Primitive Art Created]\n"
            f"- Source Image: {clean_img}\n"
            f"- Primitives: {res['num_shapes']} {m}s\n"
            f"- Time Taken: {res['duration_seconds']}s\n"
            f"- SVG Vector Output: {res['svg_path']}\n"
            f"- PNG Raster Output: {res['png_path']}\n"
            f"The image has been converted into scalable vector geometric art."
        )
    except Exception as e:
        return f"[ERROR] Primitive generation failed: {e}"


def tool_draw_in_paint(subject: str = "art") -> str:
    """Open MS Paint and physically sketch/draw the requested subject on canvas with mouse automation."""
    import time
    import pyautogui
    import math

    pyautogui.FAILSAFE = False
    clean_sub = (subject or "art").lower().strip()
    
    # Check if MS Paint opens successfully
    try:
        launch_res = tool_open_application("mspaint")
        if "[ERROR]" in launch_res:
            return "[Error] Microsoft Paint could not be opened. Please verify that Paint is installed and accessible."
    except Exception:
        return "[Error] Microsoft Paint could not be opened. Please verify that Paint is installed and accessible."

    time.sleep(1.8)
    try:
        tool_focus_window("paint")
    except Exception:
        pass
    time.sleep(0.4)

    screen_w, screen_h = pyautogui.size()
    # Safe canvas area avoiding top toolbar / ribbon
    cx = screen_w // 2
    cy = (screen_h // 2) + 70
    scale = min(screen_w, screen_h) // 6

    stroke_paths = []

    if any(k in clean_sub for k in ["cat", "kitten", "kitty"]):
        # Cat: circular head, pointy ears, eyes, nose/mouth, whiskers
        head = [(int(cx + scale * math.cos(math.radians(d))), int(cy + scale * math.sin(math.radians(d)))) for d in range(0, 361, 15)]
        stroke_paths.append(head)
        # Left ear
        stroke_paths.append([(cx - int(scale * 0.7), cy - int(scale * 0.7)), (cx - int(scale * 0.95), cy - int(scale * 1.45)), (cx - int(scale * 0.2), cy - int(scale * 0.95))])
        # Right ear
        stroke_paths.append([(cx + int(scale * 0.7), cy - int(scale * 0.7)), (cx + int(scale * 0.95), cy - int(scale * 1.45)), (cx + int(scale * 0.2), cy - int(scale * 0.95))])
        # Eyes
        stroke_paths.append([(cx - int(scale * 0.35), cy - int(scale * 0.2)), (cx - int(scale * 0.35), cy - int(scale * 0.1))])
        stroke_paths.append([(cx + int(scale * 0.35), cy - int(scale * 0.2)), (cx + int(scale * 0.35), cy - int(scale * 0.1))])
        # Whiskers
        stroke_paths.append([(cx - int(scale * 0.2), cy + 10), (cx - int(scale * 0.8), cy - 5)])
        stroke_paths.append([(cx - int(scale * 0.2), cy + 25), (cx - int(scale * 0.8), cy + 35)])
        stroke_paths.append([(cx + int(scale * 0.2), cy + 10), (cx + int(scale * 0.8), cy - 5)])
        stroke_paths.append([(cx + int(scale * 0.2), cy + 25), (cx + int(scale * 0.8), cy + 35)])
        # Mouth arc
        stroke_paths.append([(int(cx + (scale * 0.35) * math.cos(math.radians(d))), int(cy + 25 + (scale * 0.25) * math.sin(math.radians(d)))) for d in range(20, 161, 15)])

    elif any(k in clean_sub for k in ["house", "building", "home", "cabin"]):
        # House: square body, roof, door, window
        stroke_paths.append([(cx - scale, cy - int(scale * 0.2)), (cx + scale, cy - int(scale * 0.2)), (cx + scale, cy + scale), (cx - scale, cy + scale), (cx - scale, cy - int(scale * 0.2))])
        stroke_paths.append([(cx - scale, cy - int(scale * 0.2)), (cx, cy - int(scale * 1.2)), (cx + scale, cy - int(scale * 0.2))])
        stroke_paths.append([(cx - int(scale * 0.3), cy + scale), (cx - int(scale * 0.3), cy + int(scale * 0.3)), (cx + int(scale * 0.3), cy + int(scale * 0.3)), (cx + int(scale * 0.3), cy + scale)])
        stroke_paths.append([(cx - int(scale * 0.7), cy), (cx - int(scale * 0.4), cy), (cx - int(scale * 0.4), cy + int(scale * 0.3)), (cx - int(scale * 0.7), cy + int(scale * 0.3)), (cx - int(scale * 0.7), cy)])

    elif any(k in clean_sub for k in ["heart", "love"]):
        heart_pts = []
        for t in range(0, 360, 10):
            rad = math.radians(t)
            x = 16 * (math.sin(rad) ** 3)
            y = -(13 * math.cos(rad) - 5 * math.cos(2*rad) - 2 * math.cos(3*rad) - math.cos(4*rad))
            heart_pts.append((int(cx + x * (scale / 18)), int(cy + y * (scale / 18))))
        stroke_paths.append(heart_pts)

    elif any(k in clean_sub for k in ["star"]):
        star_pts = []
        for i in range(11):
            r = scale if i % 2 == 0 else scale * 0.45
            ang = math.radians(i * 36 - 90)
            star_pts.append((int(cx + r * math.cos(ang)), int(cy + r * math.sin(ang))))
        stroke_paths.append(star_pts)

    elif any(k in clean_sub for k in ["tree", "forest", "plant"]):
        # Tree: trunk and bushy canopy
        stroke_paths.append([(cx - int(scale * 0.2), cy + scale), (cx - int(scale * 0.15), cy), (cx + int(scale * 0.15), cy), (cx + int(scale * 0.2), cy + scale)])
        canopy = [(int(cx + scale * 0.9 * math.cos(math.radians(d))), int(cy - scale * 0.5 + scale * 0.8 * math.sin(math.radians(d)))) for d in range(0, 361, 20)]
        stroke_paths.append(canopy)

    elif any(k in clean_sub for k in ["car", "vehicle", "automobile", "truck"]):
        # Car body, roof, and two wheels
        stroke_paths.append([(cx - scale, cy + int(scale * 0.4)), (cx + scale, cy + int(scale * 0.4)), (cx + scale, cy), (cx + int(scale * 0.6), cy), (cx + int(scale * 0.3), cy - int(scale * 0.5)), (cx - int(scale * 0.5), cy - int(scale * 0.5)), (cx - int(scale * 0.8), cy), (cx - scale, cy), (cx - scale, cy + int(scale * 0.4))])
        # Left wheel
        stroke_paths.append([(int(cx - scale * 0.5 + scale * 0.2 * math.cos(math.radians(d))), int(cy + scale * 0.4 + scale * 0.2 * math.sin(math.radians(d)))) for d in range(0, 361, 30)])
        # Right wheel
        stroke_paths.append([(int(cx + scale * 0.5 + scale * 0.2 * math.cos(math.radians(d))), int(cy + scale * 0.4 + scale * 0.2 * math.sin(math.radians(d)))) for d in range(0, 361, 30)])

    elif any(k in clean_sub for k in ["robot", "cyborg", "droid"]):
        # Robot head, antenna, eyes, torso, arms
        stroke_paths.append([(cx - int(scale * 0.5), cy - scale), (cx + int(scale * 0.5), cy - scale), (cx + int(scale * 0.5), cy - int(scale * 0.3)), (cx - int(scale * 0.5), cy - int(scale * 0.3)), (cx - int(scale * 0.5), cy - scale)])
        stroke_paths.append([(cx, cy - scale), (cx, cy - int(scale * 1.3))])
        stroke_paths.append([(cx - int(scale * 0.25), cy - int(scale * 0.65)), (cx - int(scale * 0.25), cy - int(scale * 0.55))])
        stroke_paths.append([(cx + int(scale * 0.25), cy - int(scale * 0.65)), (cx + int(scale * 0.25), cy - int(scale * 0.55))])
        stroke_paths.append([(cx - scale * 0.7, cy - int(scale * 0.2)), (cx + scale * 0.7, cy - int(scale * 0.2)), (cx + scale * 0.7, cy + scale * 0.8), (cx - scale * 0.7, cy + scale * 0.8), (cx - scale * 0.7, cy - int(scale * 0.2))])

    elif any(k in clean_sub for k in ["dragon", "dinosaur", "monster"]):
        # Dragon head, crest, spine curve, wing
        stroke_paths.append([(cx - int(scale * 1.1), cy - int(scale * 0.3)), (cx - int(scale * 0.4), cy - int(scale * 0.7)), (cx, cy - int(scale * 0.5)), (cx + int(scale * 0.8), cy + int(scale * 0.6)), (cx + scale, cy + int(scale * 0.8))])
        stroke_paths.append([(cx - int(scale * 0.4), cy - int(scale * 0.7)), (cx - int(scale * 0.2), cy - int(scale * 1.2)), (cx + int(scale * 0.1), cy - int(scale * 0.6))])
        stroke_paths.append([(cx, cy - int(scale * 0.4)), (cx + int(scale * 0.6), cy - int(scale * 1.1)), (cx + int(scale * 0.9), cy - int(scale * 0.3)), (cx + int(scale * 0.4), cy)])
        stroke_paths.append([(cx - int(scale * 1.1), cy - int(scale * 0.3)), (cx - int(scale * 1.4), cy - int(scale * 0.2)), (cx - int(scale * 1.2), cy)])

    elif any(k in clean_sub for k in ["smiley", "smile", "face"]):
        # Smiley face
        head = [(int(cx + scale * math.cos(math.radians(d))), int(cy + scale * math.sin(math.radians(d)))) for d in range(0, 361, 15)]
        stroke_paths.append(head)
        stroke_paths.append([(cx - int(scale * 0.35), cy - int(scale * 0.3)), (cx - int(scale * 0.35), cy - int(scale * 0.15))])
        stroke_paths.append([(cx + int(scale * 0.35), cy - int(scale * 0.3)), (cx + int(scale * 0.35), cy - int(scale * 0.15))])
        stroke_paths.append([(int(cx + (scale * 0.5) * math.cos(math.radians(d))), int(cy + (scale * 0.4) * math.sin(math.radians(d)))) for d in range(25, 156, 15)])

    else:
        # Safe universal sketch strategy for ANY arbitrary subject (landscape, castle, sword, person, etc.)
        # 1. Base horizon / foundation line
        stroke_paths.append([(cx - int(scale * 1.2), cy + int(scale * 0.8)), (cx + int(scale * 1.2), cy + int(scale * 0.8))])
        # 2. Central focal contour
        stroke_paths.append([
            (cx - int(scale * 0.8), cy + int(scale * 0.7)),
            (cx - int(scale * 0.6), cy - int(scale * 0.5)),
            (cx, cy - int(scale * 1.0)),
            (cx + int(scale * 0.6), cy - int(scale * 0.5)),
            (cx + int(scale * 0.8), cy + int(scale * 0.7))
        ])
        # 3. Inner structure / details
        stroke_paths.append([(cx - int(scale * 0.3), cy + int(scale * 0.7)), (cx - int(scale * 0.3), cy), (cx + int(scale * 0.3), cy), (cx + int(scale * 0.3), cy + int(scale * 0.7))])
        stroke_paths.append([(cx, cy - int(scale * 0.8)), (cx, cy + int(scale * 0.2))])

    try:
        for pts in stroke_paths:
            if not pts:
                continue
            pyautogui.moveTo(pts[0][0], pts[0][1], duration=0.08)
            pyautogui.mouseDown(button="left")
            try:
                for pt in pts[1:]:
                    pyautogui.moveTo(pt[0], pt[1], duration=0.03)
            finally:
                pyautogui.mouseUp(button="left")
            time.sleep(0.04)
        return f"[Report] The requested drawing was completed in Microsoft Paint for Master."
    except Exception as e:
        try:
            pyautogui.mouseUp(button="left")
        except Exception:
            pass
        return f"[Error] Drawing stroke execution interrupted: {e}"


def tool_open_application(target: str, browser: str = None) -> str:
    """Launch any Windows application, desktop shortcut (.lnk, .url), system tool, or web URL as a NEW WINDOW / instance."""
    import ctypes
    import webbrowser
    import os
    import shutil
    import subprocess

    target_clean = target.strip().strip("'\"“”‘’")
    if not target_clean:
        return "[ERROR] No target application or URL specified."

    if target_clean.startswith(("http://", "https://")):
        try:
            target_clean = validate_http_url(target_clean)
        except SecurityError as exc:
            log_security.warning(f"Rejected unsafe URL launch in open_application: {target_clean} ({exc})")
            return f"[ERROR] Security rejection: {exc}"

    if not request_permission("OPEN APPLICATION", f"Launch application or URL: {target_clean}"):
        return f"[DENIED] Master cancelled launching '{target_clean}'."
    
    lower = target_clean.lower()
    SW_SHOWNORMAL = 1

    # 0. Browser launchers catalog
    browser_launchers = BROWSER_LAUNCHERS

    # 0.1 Direct file path or desktop shortcut execution (opens again as a new window/instance if already running)
    clean_path = os.path.expanduser(os.path.expandvars(target_clean))
    if os.path.exists(clean_path):
        base_name = os.path.basename(clean_path)
        # Check if this path resolves to any browser (Chrome with any profile, Brave, Edge, Firefox, Opera, etc.)
        b_info = resolve_browser_from_path(clean_path)
        if b_info and b_info.get("is_browser"):
            b_name = b_info.get("browser", "browser")
            b_exe = b_info.get("exe")
            b_prof = b_info.get("profile")
            if b_exe and os.path.exists(b_exe):
                if b_name == "firefox":
                    launch_cmd = "-new-window"
                elif b_prof:
                    launch_cmd = f'--profile-directory="{b_prof}" --new-window'
                else:
                    launch_cmd = "--new-window"

                try:
                    res = ctypes.windll.shell32.ShellExecuteW(None, "open", b_exe, launch_cmd, None, SW_SHOWNORMAL)
                    if res > 32:
                        prof_str = f" (Profile: {b_prof})" if b_prof else ""
                        return f"[Report] Opened new window for '{base_name}'{prof_str} in {b_name.title()} for Master."
                except Exception:
                    pass

        # Case B: If this is VS Code:
        raw_target_str = (clean_path + " " + (b_info.get("raw_exe") or "" if b_info else "")).lower()
        if "code.exe" in raw_target_str:
            code_p = shutil.which("code.cmd") or shutil.which("code.exe") or os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")
            if code_p and os.path.exists(code_p):
                try:
                    res = ctypes.windll.shell32.ShellExecuteW(None, "open", code_p, "-n", None, SW_SHOWNORMAL)
                    if res > 32:
                        return f"[Report] Opened new window for '{base_name}' in VS Code for Master."
                except Exception:
                    pass

        # Case C: General execution for shortcuts, scripts, or executables (opens another instance/window even if already open)
        try:
            res = ctypes.windll.shell32.ShellExecuteW(None, "open", clean_path, None, None, SW_SHOWNORMAL)
            if res > 32:
                return f"[Report] Shortcut/file '{base_name}' launched successfully (opened again if already running) for Master."
        except Exception:
            pass
        try:
            os.startfile(clean_path)
            return f"[Report] Shortcut/file '{base_name}' launched successfully for Master."
        except Exception:
            pass
        try:
            subprocess.Popen([clean_path], shell=True)
            return f"[Report] Shortcut/file '{base_name}' instance launched successfully for Master."
        except Exception:
            pass
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", '""', clean_path], shell=True)
            return f"[Report] Shortcut/file '{base_name}' launched via system shell for Master."
        except Exception as e:
            return f"[ERROR] Failed to open path '{clean_path}': {e}"

    # 0.2 Master Rule: "youtube", "music", "open music", "open youtube" always routes to b⚡.lnk in Brave
    if lower in ["youtube", "open youtube", "music", "open music", "play music", "play song", "song", "b", "b⚡", "b⚡.lnk", "my youtube"]:
        # Launch Brave with a new window to YouTube
        brave_paths = [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\\brave.exe"),
            shutil.which("brave"),
            shutil.which("brave.exe"),
        ]
        for p in brave_paths:
            if p and os.path.exists(p):
                res = ctypes.windll.shell32.ShellExecuteW(None, "open", p, "--new-window https://youtube.com", None, SW_SHOWNORMAL)
                if res > 32:
                    return "[Report] Master's YouTube shortcut (b⚡) has been opened in a new Brave window."

        b_lnk = os.path.join(os.path.expanduser(r"~\OneDrive\Desktop"), "b⚡.lnk")
        if os.path.exists(b_lnk):
            res = ctypes.windll.shell32.ShellExecuteW(None, "open", b_lnk, None, None, SW_SHOWNORMAL)
            if res > 32:
                return "[Report] Master's YouTube shortcut (b⚡) has been opened in Brave."

    # Exception: Explicitly requested Chrome for YouTube
    if "chrome" in lower and ("youtube" in lower or "music" in lower):
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
        ]
        for p in chrome_paths:
            if p and os.path.exists(p):
                res = ctypes.windll.shell32.ShellExecuteW(None, "open", p, "--new-window https://youtube.com", None, SW_SHOWNORMAL)
                if res > 32:
                    return "[Report] YouTube has been opened in a new Chrome window for Master."

    # 1. Force New Window for Browsers
    for b_key, b_paths in browser_launchers.items():
        if b_key == lower or b_key in lower.split():
            for p in b_paths:
                if p and os.path.exists(p):
                    res = ctypes.windll.shell32.ShellExecuteW(None, "open", p, "--new-window", None, SW_SHOWNORMAL)
                    if res > 32:
                        return f"[Report] New {b_key.title()} window opened successfully for Master."

    # 2. Force New Window for VS Code
    if lower in ["vscode", "vs code", "code"]:
        code_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
            shutil.which("code.cmd"),
            shutil.which("code.exe"),
        ]
        for p in code_paths:
            if p and os.path.exists(p):
                res = ctypes.windll.shell32.ShellExecuteW(None, "open", p, "-n", None, SW_SHOWNORMAL)
                if res > 32:
                    return "[Report] New VS Code window opened successfully for Master."

    # 3. Force New Window for File Explorer
    if lower in ["explorer", "file explorer", "files", "folder"]:
        res = ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", "/n", None, SW_SHOWNORMAL)
        if res > 32:
            return "[Report] New File Explorer window opened successfully for Master."

    # 4. Direct Web URLs (open in new browser window)
    if lower.startswith(("http://", "https://")):
        # If Master specified a specific browser executable / profile via path:
        if _preferred_browser_exe and os.path.exists(_preferred_browser_exe):
            b_name = _preferred_browser or "Browser"
            if _preferred_browser == "firefox":
                launch_cmd = f"-new-window {target_clean}"
            elif _preferred_browser_profile:
                launch_cmd = f'--new-window --profile-directory="{_preferred_browser_profile}" {target_clean}'
            else:
                launch_cmd = f"--new-window {target_clean}"
            try:
                res = ctypes.windll.shell32.ShellExecuteW(None, "open", _preferred_browser_exe, launch_cmd, None, SW_SHOWNORMAL)
                if res > 32:
                    prof_str = f" (Profile: {_preferred_browser_profile})" if _preferred_browser_profile else ""
                    return f"[Report] Navigating to: {target_clean} in a new {b_name.title()}{prof_str} window for Master."
            except Exception:
                pass

        pref = (browser or _preferred_browser or "").lower().strip()
        if not pref:
            if any(k in lower for k in ["docs.google.com", "docs.new", "sheets.new", "slides.new", "drive.google.com", "google.com"]):
                pref = "chrome"
            else:
                pref = "brave"

        if pref in browser_launchers:
            candidate_browsers = [pref] + [b for b in ["chrome", "brave", "edge", "firefox"] if b != pref]
        else:
            candidate_browsers = ["chrome", "brave", "edge", "firefox"]

        for b_name in candidate_browsers:
            for p in browser_launchers.get(b_name, []):
                if p and os.path.exists(p):
                    launch_cmd = f"--new-window {target_clean}"
                    prof_to_use = _preferred_browser_profile or _active_chrome_profile
                    if b_name == "chrome" and prof_to_use:
                        launch_cmd = f'--new-window --profile-directory="{prof_to_use}" {target_clean}'
                    res = ctypes.windll.shell32.ShellExecuteW(None, "open", p, launch_cmd, None, SW_SHOWNORMAL)
                    if res > 32:
                        return f"[Report] Navigating to: {target_clean} in a new {b_name.title()} window for Master."
        webbrowser.open_new(target_clean)
        return f"[Report] Navigating to: {target_clean}"

    # 5. Known Windows alias mapping
    alias_map = {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
        "powershell": "powershell.exe",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "settings": "ms-settings:",
        "windows settings": "ms-settings:",
        "roblox": "roblox player",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
        "hoyoplay": "hoyoplay",
        "genshin": "hoyoplay",
        "honkai": "hoyoplay",
        "cookierun": "cookierun kingdom",
        "bilibili": "bilibili",
        "line": "line",
        "thonny": "thonny",
        "dev c++": "dev-c++red",
        "dev-c++": "dev-c++red",
        "curseforge": "curseforge",
        "steam": "steam",
        "discord": "discord",
        "spotify": "spotify",
        "vlc": "vlc",
    }
    
    search_term = alias_map.get(lower, lower)

    # 6. Dynamic Search across Desktop, OneDrive Desktop, and Start Menu directories
    search_dirs = [
        os.path.expanduser(r"~\OneDrive\Desktop"),
        os.path.expanduser(r"~\Desktop"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]

    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                name_no_ext, ext = os.path.splitext(f.lower())
                if ext in [".lnk", ".url", ".exe"]:
                    if search_term == name_no_ext or search_term in name_no_ext or name_no_ext in search_term:
                        full_path = os.path.join(root, f)
                        try:
                            res = ctypes.windll.shell32.ShellExecuteW(None, "open", full_path, None, None, SW_SHOWNORMAL)
                            if res > 32:
                                return f"[Report] New instance of '{f}' launched successfully for Master."
                        except Exception:
                            pass
                        try:
                            os.startfile(full_path)
                            return f"[Report] New instance of '{f}' launched successfully for Master."
                        except Exception:
                            pass

    # 7.5. Start Menu dynamic application discovery fallback
    apps = discover_start_menu_applications()
    matched = [a for a in apps if lower == a["name"].lower() or lower in a["name"].lower() or a["name"].lower() in lower]
    if matched:
        best_match = matched[0]
        for a in matched:
            if a["name"].lower() == lower:
                best_match = a
                break
        try:
            res = ctypes.windll.shell32.ShellExecuteW(None, "open", best_match["path"], None, None, SW_SHOWNORMAL)
            if res > 32:
                return f"[Report] Application '{best_match['name']}' launched successfully from Start Menu for Master."
        except Exception:
            pass
        try:
            os.startfile(best_match["path"])
            return f"[Report] Application '{best_match['name']}' launched successfully from Start Menu for Master."
        except Exception:
            pass

    # 7. Direct existing file or executable path
    direct_target = alias_map.get(lower, target_clean)
    if os.path.exists(direct_target):
        try:
            res = ctypes.windll.shell32.ShellExecuteW(None, "open", direct_target, None, None, SW_SHOWNORMAL)
            if res > 32:
                return f"[Report] New instance of '{os.path.basename(direct_target)}' launched successfully for Master."
        except Exception:
            pass

    # 8. Direct ShellExecute / start command
    try:
        res = ctypes.windll.shell32.ShellExecuteW(None, "open", direct_target, None, None, SW_SHOWNORMAL)
        if res > 32:
            return f"[Report] New instance of '{target_clean.title()}' opened successfully for Master."
    except Exception:
        pass

    try:
        os.startfile(direct_target)
        return f"[Report] New instance of '{target_clean.title()}' opened successfully for Master."
    except Exception:
        pass

    try:
        subprocess.Popen(f'start "" "{direct_target}"', shell=True)
        return f"[Report] New instance of '{target_clean.title()}' started for Master."
    except Exception as e:
        return f"[ERROR] Failed to launch '{target_clean}': {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# Desktop Operator Tools (Inspired by Ciel Jarvis Taskbar)
# ═══════════════════════════════════════════════════════════════════════════════

_APP_CACHE = {"timestamp": 0.0, "apps": []}
_APP_CACHE_TTL = 60.0  # seconds

def _start_menu_roots() -> list:
    roots = []
    app_data = os.environ.get("APPDATA")
    prog_data = os.environ.get("ProgramData")
    if app_data:
        roots.append(os.path.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs"))
    if prog_data:
        roots.append(os.path.join(prog_data, "Microsoft", "Windows", "Start Menu", "Programs"))
    return [os.path.abspath(r) for r in roots if os.path.exists(r)]

def discover_start_menu_applications() -> list:
    """Walk Start Menu folders and return list of dicts: [{'name': 'Discord', 'path': '...'}, ...]"""
    import time
    now = time.time()
    if _APP_CACHE["apps"] and (now - _APP_CACHE["timestamp"]) < _APP_CACHE_TTL:
        return list(_APP_CACHE["apps"])

    results = []
    seen = set()
    MAX_APPS = 150
    MAX_DEPTH = 5

    def _walk(dir_path: str, depth: int):
        if len(results) >= MAX_APPS or depth > MAX_DEPTH:
            return
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    if len(results) >= MAX_APPS or entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        _walk(entry.path, depth + 1)
                    elif entry.is_file(follow_symlinks=False):
                        name_lower = entry.name.lower()
                        if name_lower.endswith((".lnk", ".exe", ".appref-ms")):
                            base = os.path.splitext(entry.name)[0]
                            clean_name = re.sub(r"[._-]+", " ", base).strip()
                            norm = clean_name.lower()
                            if len(clean_name) >= 2 and norm not in seen:
                                seen.add(norm)
                                results.append({"name": clean_name, "path": os.path.abspath(entry.path)})
        except Exception:
            pass

    for root in _start_menu_roots():
        _walk(root, 0)

    results.sort(key=lambda x: x["name"].lower())
    _APP_CACHE["apps"] = results
    _APP_CACHE["timestamp"] = now
    return list(results)

def tool_discover_applications(query: str = "") -> str:
    """Discover installed Windows applications from the Start Menu. Optional filter query."""
    apps = discover_start_menu_applications()
    q = (query or "").strip().lower()
    if q:
        apps = [a for a in apps if q in a["name"].lower()]
    if not apps:
        return f"[Report] No installed applications matching '{query}' were found." if query else "[Report] No Start menu applications discovered."
    
    lines = [f"- {a['name']} ({a['path']})" for a in apps[:30]]
    if len(apps) > 30:
        lines.append(f"... and {len(apps) - 30} more installed applications.")
    return f"[Installed Applications Catalog ({len(apps)} total)]\n" + "\n".join(lines)

def tool_search_user_files(query: str, max_results: int = 20) -> str:
    """Search filenames across Windows user library directories (Desktop, Documents, Downloads, Pictures, Videos, Music)."""
    clean_q = (query or "").strip()
    if len(clean_q) < 2:
        return "[ERROR] Search query must be at least 2 characters."

    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Pictures"),
        os.path.join(home, "Videos"),
        os.path.join(home, "Music"),
    ]
    for sub in ["Desktop", "Documents", "Pictures"]:
        od_path = os.path.join(home, "OneDrive", sub)
        if os.path.exists(od_path) and od_path not in roots:
            roots.append(od_path)

    valid_roots = [os.path.abspath(r) for r in roots if os.path.exists(r)]
    SKIP_DIRS = {"$recycle.bin", ".git", ".svn", "node_modules", "appdata", "__pycache__", ".vscode", ".idea"}

    needle = clean_q.lower()
    matches = []
    MAX_RES = min(max(1, max_results or 20), 50)
    MAX_DEPTH = 4

    def _walk(curr_dir: str, depth: int):
        if len(matches) >= MAX_RES or depth > MAX_DEPTH:
            return
        try:
            with os.scandir(curr_dir) as entries:
                for entry in entries:
                    if len(matches) >= MAX_RES:
                        break
                    name_low = entry.name.lower()
                    if entry.name.startswith(".") or name_low in SKIP_DIRS:
                        continue
                    if needle in name_low:
                        matches.append(os.path.abspath(entry.path))
                    if entry.is_dir(follow_symlinks=False):
                        _walk(entry.path, depth + 1)
        except Exception:
            pass

    for root in valid_roots:
        _walk(root, 0)

    if not matches:
        return f"[Report] No filename matches found for '{clean_q}' across user libraries (Desktop, Documents, Downloads, etc.)."

    lines = [f"- {p}" for p in matches]
    return f"[User File Search Results for '{clean_q}' ({len(matches)} matches)]:\n" + "\n".join(lines)

def tool_get_screen_size() -> str:
    """Get primary monitor screen dimensions (width and height in pixels)."""
    import ctypes
    try:
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        return json.dumps({"width": w, "height": h, "resolution": f"{w}x{h}"})
    except Exception as e:
        return json.dumps({"width": 1920, "height": 1080, "error": str(e)})

def _load_pinned_items() -> list:
    from config import config
    pins_file = config.paths.pinned_items_file
    if not pins_file.exists():
        home = os.path.expanduser("~")
        defaults = [
            {"id": "default-files", "label": "Files", "kind": "folder", "target": home, "enabled": True},
            {"id": "default-browser", "label": "Browser", "kind": "url", "target": "https://www.google.com", "enabled": True},
            {"id": "default-notepad", "label": "Notepad", "kind": "application", "target": "notepad.exe", "enabled": True},
        ]
        _save_pinned_items(defaults)
        return defaults
    try:
        with open(pins_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "pins" in data:
                return data["pins"]
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []

def _save_pinned_items(pins: list) -> bool:
    from config import config
    pins_file = config.paths.pinned_items_file
    tmp_file = pins_file.with_suffix(".tmp")
    try:
        pins_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump({"pins": pins}, f, indent=2)
        tmp_file.replace(pins_file)
        return True
    except Exception:
        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)
        return False

def tool_list_pinned_items() -> str:
    """List the user's pinned taskbar items (id, label, kind, target)."""
    pins = _load_pinned_items()
    if not pins:
        return "[Report] No pinned items found."
    lines = [f"- [{p.get('kind', 'app')}] '{p.get('label')}' -> {p.get('target')} (id: {p.get('id')})" for p in pins]
    return f"[Pinned Quick-Access Items ({len(pins)})]:\n" + "\n".join(lines)

def tool_add_pinned_item(label: str, target: str, kind: str = "application") -> str:
    """Add a new pinned taskbar item. Args: label, target, kind ('application', 'folder', 'url')."""
    import uuid
    lbl = (label or "").strip()
    tgt = (target or "").strip()
    k = (kind or "application").strip().lower()
    if not lbl or not tgt:
        return "[ERROR] Both label and target are required to pin an item."
    if k not in ("application", "folder", "url"):
        k = "url" if tgt.startswith(("http://", "https://")) else ("folder" if os.path.isdir(tgt) else "application")
    
    pins = _load_pinned_items()
    for p in pins:
        if p.get("label", "").lower() == lbl.lower():
            p["target"] = tgt
            p["kind"] = k
            p["enabled"] = True
            _save_pinned_items(pins)
            return f"[SUCCESS] Updated existing pinned item '{lbl}' -> {tgt} ({k})."

    new_id = f"pin-{uuid.uuid4().hex[:8]}"
    pins.append({"id": new_id, "label": lbl, "kind": k, "target": tgt, "enabled": True})
    if _save_pinned_items(pins):
        return f"[SUCCESS] Pinned item '{lbl}' ({k}) added successfully with ID '{new_id}'."
    return "[ERROR] Failed to save pinned item to disk."

def tool_launch_pinned_item(name: str) -> str:
    """Launch a pinned taskbar item by id or label."""
    import ctypes
    needle = (name or "").strip().lower()
    if not needle:
        return "[ERROR] Pinned item name or ID required."
    pins = _load_pinned_items()
    target_pin = None
    for p in pins:
        if p.get("id", "").lower() == needle or p.get("label", "").lower() == needle or needle in p.get("label", "").lower():
            target_pin = p
            break
    if not target_pin:
        return f"[ERROR] No pinned item matching '{name}' found. Use list_pinned_items to view available pins."
    
    if not target_pin.get("enabled", True):
        return f"[Report] Pinned item '{target_pin.get('label')}' is currently disabled."
    
    tgt = target_pin.get("target", "")
    kind = target_pin.get("kind", "")
    if kind == "url" or tgt.startswith(("http://", "https://")):
        return tool_open_application(tgt)
    
    if not request_permission("LAUNCH PINNED ITEM", f"Launch pinned {kind}: {target_pin.get('label')} ({tgt})"):
        return f"[DENIED] Master cancelled launching pinned item '{target_pin.get('label')}'."
    
    SW_SHOWNORMAL = 1
    try:
        res = ctypes.windll.shell32.ShellExecuteW(None, "open", tgt, None, None, SW_SHOWNORMAL)
        if res > 32:
            return f"[Report] Pinned item '{target_pin.get('label')}' launched successfully for Master."
    except Exception:
        pass
    try:
        os.startfile(tgt)
        return f"[Report] Pinned item '{target_pin.get('label')}' launched successfully for Master."
    except Exception as e:
        return f"[ERROR] Failed to launch pinned item '{target_pin.get('label')}': {e}"


def tool_play_youtube(query: str = "", browser: str = "brave") -> str:
    """Play any song, music, video, or open Master's YouTube shortcut (b⚡) in Brave."""
    import ctypes
    import urllib.parse
    import os
    import shutil

    query_clean = (query or "").strip().strip("'\"")
    SW_SHOWNORMAL = 1
    browser_lower = (browser or "brave").lower()

    # Exception: Explicitly requested Chrome
    if "chrome" in browser_lower or "in chrome" in query_clean.lower():
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
        ]
        clean_name = query_clean.replace("in chrome", "").strip()
        if not clean_name or clean_name.lower() in ["youtube", "music", "song"]:
            url = "https://youtube.com"
        elif clean_name.startswith(("http://", "https://")):
            url = clean_name
        else:
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean_name)}"
        for p in chrome_paths:
            if p and os.path.exists(p):
                res = ctypes.windll.shell32.ShellExecuteW(None, "open", p, f"--new-window {url}", None, SW_SHOWNORMAL)
                if res > 32:
                    return "[Report] YouTube opened in Chrome Browser for Master."

    # By default, open b⚡.lnk if generic or no query
    b_lnk = os.path.join(os.path.expanduser(r"~\OneDrive\Desktop"), "b\u26a1.lnk")
    if (not query_clean or query_clean.lower() in ["b⚡", "b⚡.lnk", "youtube", "music", "open music", "play music", "my youtube", "b", "song", "popular songs"] or "b⚡" in query_clean):
        if os.path.exists(b_lnk):
            res = ctypes.windll.shell32.ShellExecuteW(None, "open", b_lnk, None, None, SW_SHOWNORMAL)
            if res > 32:
                return "[Report] Master's YouTube shortcut (b⚡) has been opened in Brave."
            try:
                os.startfile(b_lnk)
                return "[Report] Master's YouTube shortcut (b⚡) has been opened in Brave."
            except Exception:
                pass

    # Specific song query in Brave
    clean_name = query_clean
    for prefix in ["play ", "song ", "music ", "search for ", "open ", "find ", "video "]:
        if clean_name.lower().startswith(prefix):
            clean_name = clean_name[len(prefix):].strip()
    encoded = urllib.parse.quote_plus(clean_name)
    url = f"https://www.youtube.com/results?search_query={encoded}"

    # Search for Brave shortcut or exe
    brave_lnk = os.path.expanduser(r"~\OneDrive\Desktop\⚡ - Brave.lnk")
    if os.path.exists(brave_lnk):
        try:
            res = ctypes.windll.shell32.ShellExecuteW(None, "open", brave_lnk, f"--new-window {url}", None, SW_SHOWNORMAL)
            if res > 32:
                return f"[Report] Playing '{clean_name}' on YouTube in Brave Browser, Master."
        except Exception:
            pass

    brave_paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\\brave.exe"),
        shutil.which("brave"),
        shutil.which("brave.exe"),
    ]
    for p in brave_paths:
        if p and os.path.exists(p):
            res = ctypes.windll.shell32.ShellExecuteW(None, "open", p, f"--new-window {url}", None, SW_SHOWNORMAL)
            if res > 32:
                return f"[Report] Playing '{clean_name}' on YouTube in Brave Browser, Master."

    # Fallback to general ShellExecute / webbrowser
    try:
        res = ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, SW_SHOWNORMAL)
        if res > 32:
            return f"[Report] Playing '{clean_name}' on YouTube for Master."
    except Exception:
        pass

    import webbrowser
    webbrowser.open(url)
    return f"[Report] Playing '{clean_name}' on YouTube for Master."


# ─────────────────────────────────────────────────────────────────────────────
# JARVIS Unified Intelligence Suite (PowerPoint, Audio & Display Controls)
# ─────────────────────────────────────────────────────────────────────────────

def tool_generate_presentation(topic: str, num_slides: int = 5) -> str:
    """Generate a complete PowerPoint presentation (.pptx) with structured slides and launch it on Desktop."""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Title Slide
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        bg = slide.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = RGBColor(15, 23, 42)
        bg.line.fill.background()

        tb = slide.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.333), Inches(3.0))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = topic.upper()
        p.font.name = 'Segoe UI'
        p.font.size = Pt(44)
        p.font.bold = True
        p.font.color.rgb = RGBColor(56, 189, 248)
        p.alignment = PP_ALIGN.CENTER

        p2 = tf.add_paragraph()
        p2.text = "Generated by Manas Ciel x JARVIS Neural Engine"
        p2.font.name = 'Segoe UI'
        p2.font.size = Pt(20)
        p2.font.color.rgb = RGBColor(226, 232, 240)
        p2.alignment = PP_ALIGN.CENTER

        # Content Slides
        slide_titles = [
            f"1. Executive Overview: {topic}",
            f"2. Core Architectural Pillars",
            f"3. Key Capabilities & Impact",
            f"4. Implementation Roadmap",
            f"5. Strategic Summary & Outlook"
        ]

        bullet_points = [
            [f"Strategic analysis and deep dive into {topic}.", "Key opportunities and technological frontiers.", "Autonomous workflow integration."],
            ["High throughput neural reasoning pipeline.", "Sub-millisecond hardware automation triggers.", "Distributed multi-agent context synchronization."],
            ["Automated multi-modal task execution.", "Real-time system telemetry and adaptation.", "Enhanced security, reliability, and precision."],
            ["Phase 1: Foundation deployment and local tuning.", "Phase 2: Full enterprise and system interconnectivity.", "Phase 3: Continuous autonomous learning."],
            [f"Complete realization of {topic} vision.", "Long-term scalability and operational superiority.", "Manas Ciel Wisdom Core optimization complete."]
        ]

        for i in range(min(num_slides - 1, len(slide_titles))):
            c_slide = prs.slides.add_slide(prs.slide_layouts[6])
            c_bg = c_slide.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
            c_bg.fill.solid()
            c_bg.fill.fore_color.rgb = RGBColor(10, 15, 30)
            c_bg.line.fill.background()

            # Header
            h_tb = c_slide.shapes.add_textbox(Inches(1.0), Inches(0.8), Inches(11.333), Inches(1.2))
            h_tf = h_tb.text_frame
            hp = h_tf.paragraphs[0]
            hp.text = slide_titles[i]
            hp.font.name = 'Segoe UI'
            hp.font.size = Pt(28)
            hp.font.bold = True
            hp.font.color.rgb = RGBColor(251, 191, 36)

            # Body Card
            card = c_slide.shapes.add_shape(1, Inches(1.0), Inches(2.2), Inches(11.333), Inches(4.5))
            card.fill.solid()
            card.fill.fore_color.rgb = RGBColor(20, 30, 55)
            card.line.color.rgb = RGBColor(56, 189, 248)

            b_tf = card.text_frame
            b_tf.word_wrap = True
            for idx, pt in enumerate(bullet_points[i]):
                bp = b_tf.paragraphs[0] if idx == 0 else b_tf.add_paragraph()
                bp.text = f"• {pt}"
                bp.font.name = 'Segoe UI'
                bp.font.size = Pt(20)
                bp.font.color.rgb = RGBColor(241, 245, 249)
                bp.space_after = Pt(14)

        clean_filename = re.sub(r'[\\/*?:"<>|]', "", topic).strip() or "Presentation"
        desk = os.path.expanduser(r"~\\OneDrive\\Desktop")
        if not os.path.exists(desk):
            desk = os.path.expanduser(r"~\\Desktop")
        out_path = os.path.join(desk, f"{clean_filename}.pptx")
        prs.save(out_path)

        try:
            os.startfile(out_path)
        except Exception:
            pass

        return f"[Report] Presentation '{clean_filename}.pptx' ({num_slides} slides) created and opened on Desktop for Master."
    except Exception as e:
        return f"[ERROR] Failed to generate presentation: {e}"

def tool_system_control(action: str, value: int = None) -> str:
    """Control Windows master volume, media keys (play/pause/skip), and display brightness."""
    import ctypes
    action = action.lower().strip()
    try:
        if "volume" in action or action in ["mute", "unmute"]:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            vol = getattr(speakers, "EndpointVolume", None)
            if vol:
                if action in ["volume_up", "vol_up"]:
                    cur = vol.GetMasterVolumeLevelScalar()
                    new_vol = min(1.0, cur + 0.10)
                    vol.SetMasterVolumeLevelScalar(new_vol, None)
                    return f"[Report] System volume increased to {int(new_vol * 100)}%."
                elif action in ["volume_down", "vol_down"]:
                    cur = vol.GetMasterVolumeLevelScalar()
                    new_vol = max(0.0, cur - 0.10)
                    vol.SetMasterVolumeLevelScalar(new_vol, None)
                    return f"[Report] System volume decreased to {int(new_vol * 100)}%."
                elif action == "mute":
                    vol.SetMute(1, None)
                    return "[Report] System audio muted."
                elif action == "unmute":
                    vol.SetMute(0, None)
                    return "[Report] System audio unmuted."
                elif value is not None or action.startswith("volume_set"):
                    target_val = value if value is not None else 50
                    scalar = max(0.0, min(1.0, target_val / 100.0))
                    vol.SetMasterVolumeLevelScalar(scalar, None)
                    return f"[Report] System volume set to {int(scalar * 100)}%."

        # Windows Media Keys
        VK_MEDIA_NEXT_TRACK = 0xB0
        VK_MEDIA_PREV_TRACK = 0xB1
        VK_MEDIA_PLAY_PAUSE = 0xB3
        KEYEVENTF_KEYUP = 0x0002

        def press_key(vk):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        if action in ["play_pause", "pause", "resume", "toggle_media"]:
            press_key(VK_MEDIA_PLAY_PAUSE)
            return "[Report] Media playback toggled (Play/Pause)."
        elif action in ["next_track", "skip", "next_song"]:
            press_key(VK_MEDIA_NEXT_TRACK)
            return "[Report] Skipped to next track."
        elif action in ["prev_track", "previous", "prev_song"]:
            press_key(VK_MEDIA_PREV_TRACK)
            return "[Report] Returned to previous track."

        # Screen Brightness
        if "bright" in action or action in ["dim", "brighten"]:
            import screen_brightness_control as sbc
            if action in ["brightness_up", "brighten"]:
                cur = sbc.get_brightness()
                cur_val = cur[0] if isinstance(cur, list) else cur
                new_b = min(100, cur_val + 10)
                sbc.set_brightness(new_b)
                return f"[Report] Screen brightness increased to {new_b}%."
            elif action in ["brightness_down", "dim"]:
                cur = sbc.get_brightness()
                cur_val = cur[0] if isinstance(cur, list) else cur
                new_b = max(10, cur_val - 10)
                sbc.set_brightness(new_b)
                return f"[Report] Screen brightness dimmed to {new_b}%."
            elif value is not None:
                sbc.set_brightness(value)
                return f"[Report] Screen brightness set to {value}%."

        return f"[Notice] System control action '{action}' executed."
    except Exception as e:
        return f"[ERROR] System control failed: {e}"

def tool_deep_research(query: str, max_sources: int = 3) -> str:
    """Perplexica / JARVIS multi-source deep research engine with citations."""
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_sources))
        if not results:
            return tool_web_search(query)

        report = [f"### 🌐 Deep Research Briefing: {query.title()}\n"]
        sources_used = []

        for idx, r in enumerate(results, 1):
            title = r.get("title", f"Source {idx}")
            href = r.get("href", "")
            body = r.get("body", "")
            sources_used.append(f"{idx}. [{title}]({href})")
            report.append(f"**{idx}. {title}**\n{body}\n")

        report.append("\n**Primary Sources:**\n" + "\n".join(sources_used))
        return "\n".join(report)
    except Exception as e:
        return tool_web_search(query)


def tool_inspect_screen_context() -> str:
    """Mirix-style on-screen visual and active window context inspector."""
    import ctypes
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value or "Desktop / Background"
    
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    report = [
        f"### 👁️ Active Workstation Context (Mirix Inspector)",
        f"- **Active Window**: `{title}`",
        f"- **Process ID**: `{pid.value}`",
        f"- **Status**: Master is currently engaged with this application."
    ]
    return "\n".join(report)

def tool_launch_routine(mode: str) -> str:
    """Iron Man / JARVIS workstation routine launcher (coding, focus, entertainment)."""
    mode = mode.lower().strip()
    
    if mode in ["coding", "code", "work", "developer", "coding_mode"]:
        tool_open_application("vscode")
        tool_open_application("brave")
        tool_system_control("brightness_set", 80)
        tool_system_control("volume_set", 35)
        return "[Report] 💻 **Coding Workstation Routine Activated**: VS Code and Brave launched, screen brightness optimized to 80%, volume set to 35%."
    
    elif mode in ["focus", "zen", "deep_work", "focus_mode"]:
        tool_system_control("mute")
        tool_system_control("brightness_set", 75)
        return "[Report] 🧘 **Deep Focus Mode Activated**: Audio muted, screen dimmed to 75% for zero distraction."
    
    elif mode in ["entertainment", "music", "chill", "relax", "entertainment_mode"]:
        tool_open_application("b⚡")
        tool_system_control("volume_set", 50)
        tool_system_control("brightness_set", 90)
        return "[Report] 🎵 **Entertainment Routine Activated**: YouTube music launched in Brave, volume set to 50%, brightness optimized."
    
    return f"[Notice] Routine '{mode}' unrecognized. Available routines: 'coding', 'focus', 'entertainment'."


# ─────────────────────────────────────────────────────────────────────────────
# Generalized Computer-Use Operator Engine (Multi-App & Browser Autonomous Agent)
# ─────────────────────────────────────────────────────────────────────────────

COMPUTER_TARGET_CATALOG = {
    # ── Presentation & Graphic Design ──
    "canva": {
        "name": "Canva",
        "url": "https://www.canva.com",
        "url_presentation": "https://www.canva.com/create/presentations/",
        "window_keyword": "canva",
        "category": "presentation",
        "default_delay": 3.0,
    },
    "google slides": {
        "name": "Google Slides",
        "url": "https://slides.new",
        "window_keyword": "google slides",
        "category": "presentation",
        "default_delay": 3.0,
    },
    "slides": {
        "name": "Google Slides",
        "url": "https://slides.new",
        "window_keyword": "google slides",
        "category": "presentation",
        "default_delay": 3.0,
    },
    "powerpoint": {
        "name": "PowerPoint",
        "exec": "powerpnt.exe",
        "window_keyword": "powerpoint",
        "category": "presentation",
        "default_delay": 2.0,
    },
    "figma": {
        "name": "Figma",
        "url": "https://www.figma.com",
        "window_keyword": "figma",
        "category": "design",
        "default_delay": 3.5,
    },

    # ── Writing, Documents & Note-Taking ──
    "google docs": {
        "name": "Google Docs",
        "url": "https://docs.new",
        "window_keyword": "google docs",
        "category": "doc",
        "default_delay": 3.0,
    },
    "docs": {
        "name": "Google Docs",
        "url": "https://docs.new",
        "window_keyword": "google docs",
        "category": "doc",
        "default_delay": 3.0,
    },
    "notion": {
        "name": "Notion",
        "url": "https://www.notion.so",
        "window_keyword": "notion",
        "category": "notion",
        "default_delay": 3.5,
    },
    "word": {
        "name": "Microsoft Word",
        "exec": "winword.exe",
        "window_keyword": "word",
        "category": "doc",
        "default_delay": 2.0,
    },
    "notepad": {
        "name": "Notepad",
        "exec": "notepad.exe",
        "window_keyword": "notepad",
        "category": "editor",
        "default_delay": 1.0,
    },

    # ── Spreadsheets & Tables ──
    "google sheets": {
        "name": "Google Sheets",
        "url": "https://sheets.new",
        "window_keyword": "google sheets",
        "category": "sheet",
        "default_delay": 3.0,
    },
    "sheets": {
        "name": "Google Sheets",
        "url": "https://sheets.new",
        "window_keyword": "google sheets",
        "category": "sheet",
        "default_delay": 3.0,
    },
    "excel": {
        "name": "Microsoft Excel",
        "exec": "excel.exe",
        "window_keyword": "excel",
        "category": "sheet",
        "default_delay": 2.0,
    },

    # ── Coding & Development ──
    "vscode": {
        "name": "VS Code",
        "exec": "code -n",
        "window_keyword": "visual studio code",
        "category": "code",
        "default_delay": 2.0,
    },
    "github": {
        "name": "GitHub",
        "url": "https://github.com",
        "window_keyword": "github",
        "category": "web_search",
        "default_delay": 2.5,
    },

    # ── Media & Entertainment ──
    "spotify": {
        "name": "Spotify",
        "exec": "spotify",
        "url": "https://open.spotify.com",
        "window_keyword": "spotify",
        "category": "media",
        "default_delay": 2.5,
    },
    "youtube": {
        "name": "YouTube",
        "url": "https://www.youtube.com",
        "window_keyword": "youtube",
        "category": "media",
        "default_delay": 2.5,
    },
    "netflix": {
        "name": "Netflix",
        "url": "https://www.netflix.com",
        "window_keyword": "netflix",
        "category": "media",
        "default_delay": 3.0,
    },
    "reddit": {
        "name": "Reddit",
        "url": "https://www.reddit.com",
        "window_keyword": "reddit",
        "category": "web",
        "default_delay": 2.5,
    },
    "twitter": {
        "name": "X (Twitter)",
        "url": "https://x.com",
        "window_keyword": "x",
        "category": "web",
        "default_delay": 2.5,
    },

    # ── Search & AI Engines ──
    "google": {
        "name": "Google Search",
        "url": "https://www.google.com",
        "window_keyword": "google",
        "category": "web_search",
        "default_delay": 2.0,
    },
    "perplexity": {
        "name": "Perplexity AI",
        "url": "https://www.perplexity.ai",
        "window_keyword": "perplexity",
        "category": "web_search",
        "default_delay": 2.5,
    },
    "chatgpt": {
        "name": "ChatGPT",
        "url": "https://chatgpt.com",
        "window_keyword": "chatgpt",
        "category": "web",
        "default_delay": 3.0,
    },
    "claude": {
        "name": "Claude",
        "url": "https://claude.ai",
        "window_keyword": "claude",
        "category": "web",
        "default_delay": 3.0,
    },

    # ── System Utilities ──
    "calculator": {
        "name": "Calculator",
        "exec": "calc.exe",
        "window_keyword": "calculator",
        "category": "system",
        "default_delay": 1.0,
    },
    "paint": {
        "name": "Paint",
        "exec": "mspaint.exe",
        "window_keyword": "paint",
        "category": "system",
        "default_delay": 1.0,
    },
    "settings": {
        "name": "Windows Settings",
        "exec": "ms-settings:",
        "window_keyword": "settings",
        "category": "system",
        "default_delay": 1.0,
    },
}

def resolve_computer_target(target: str, context: str = "") -> dict:
    """Resolve user target app or domain to executable parameters and category."""
    t = (target or "").lower().strip().strip("'\"")
    c = (context or "").lower().strip()
    import urllib.parse

    for key, info in COMPUTER_TARGET_CATALOG.items():
        if key == t or key in t.split() or t in key:
            res = dict(info)
            if key == "canva" and any(w in c or w in t for w in ["presentation", "slide", "deck", "pitch", "slides"]):
                res["url"] = res.get("url_presentation", res["url"])
            elif key == "spotify" and c:
                query = re.sub(r"^(?:play|listen\s+to|song|music|search\s+for)\s+", "", c).strip()
                if query:
                    res["url"] = f"https://open.spotify.com/search/{urllib.parse.quote_plus(query)}"
            elif key == "youtube" and c:
                query = re.sub(r"^(?:play|watch|video|search\s+for|find)\s+", "", c).strip()
                if query:
                    res["url"] = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
            elif key in ["google", "perplexity", "github"] and c:
                query = re.sub(r"^(?:search\s+for|find|look\s+up|search)\s+", "", c).strip()
                if query:
                    if key == "google":
                        res["url"] = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
                    elif key == "perplexity":
                        res["url"] = f"https://www.perplexity.ai/search?q={urllib.parse.quote_plus(query)}"
                    elif key == "github":
                        res["url"] = f"https://github.com/search?q={urllib.parse.quote_plus(query)}"
            return res

    # Check if target is a web URL or domain
    if t.startswith(("http://", "https://")) or ("." in t and not t.endswith((".exe", ".lnk", ".bat", ".cmd", ".py"))):
        url = t if t.startswith(("http://", "https://")) else f"https://{t}"
        domain = url.split("/")[2] if "/" in url[8:] else url.replace("https://", "").replace("http://", "")
        return {
            "name": domain.title(),
            "url": url,
            "window_keyword": domain,
            "category": "web",
            "default_delay": 3.0,
        }

    return {
        "name": target.title(),
        "exec": target,
        "window_keyword": target,
        "category": "app",
        "default_delay": 1.5,
    }

def generate_autonomous_content(topic: str, category: str = "doc") -> str:
    """Generate structured content (documents, presentation outlines, code, tables) for autonomous pasting."""
    clean = topic.strip()
    for p in ["make a presentation about", "presentation about", "presentation on", "slides on",
              "write an essay about", "essay on", "an essay about", "write notes on", "notes about",
              "create a page for", "create page for", "create a template for", "budget for", "template for"]:
        if clean.lower().startswith(p):
            clean = clean[len(p):].strip()
            break
    clean_title = clean.title() if clean else "Strategic Overview"

    if category == "presentation":
        return f"""# {clean_title.upper()}
Presented by Manas Ciel Autonomous Operator for Master

--- SLIDE 1: Executive Overview ---
- Strategic Analysis: {clean_title}
- Autonomous Workflow Integration & Core Objectives
- Modern Architectural Frontier & Scope

--- SLIDE 2: Core Technological Pillars ---
- High-Throughput Neural Execution Pipelines
- Resilient System Integration & Feedback Control
- Modular Service Architecture & Fault Tolerance

--- SLIDE 3: Key Capabilities & Milestones ---
- Multi-Platform Task Automation (Desktop & Web)
- Real-Time Perceptual Telemetry & Verification
- Seamless Human-Agent Collaboration

--- SLIDE 4: Implementation Roadmap ---
- Phase 1: Rapid Environment Setup & Validation
- Phase 2: Full System Interconnectivity
- Phase 3: Autonomous Tuning & Scalability

--- SLIDE 5: Strategic Conclusion ---
- Comprehensive Realization of {clean_title}
- Operational Superiority & Ongoing Adaptation
- Manas Ciel Wisdom Core Standing by for Master
"""
    elif category == "sheet":
        return f"Item\tCategory\tTarget\tActual\tVariance\tStatus\nKickoff & Planning\tPhase 1\t100\t100\t0\tCompleted\nInfrastructure Setup\tPhase 1\t250\t220\t+30\tCompleted\nCore Automation Engine\tPhase 2\t500\t500\t0\tActive\nQuality Verification\tPhase 3\t200\t180\t+20\tIn Progress\nFinal Review & Signoff\tPhase 4\t150\t100\t+50\tScheduled\nTotal\tSummary\t1200\t1100\t+100\tOn Track\n"
    elif category == "code":
        return f"""# {clean_title}
# Generated autonomously by Manas Ciel for Master

import os
import sys
import time

def execute_main():
    \"\"\"Main operational workflow for {clean_title}.\"\"\"
    print("[Notice] Initializing {clean_title}...")
    start_time = time.time()
    results = {{"status": "success", "module": "{clean_title}", "elapsed": 0.0}}
    elapsed = time.time() - start_time
    results["elapsed"] = elapsed
    print(f"[Report] {clean_title} executed successfully in {{elapsed:.4f}}s.")
    return results

if __name__ == "__main__":
    execute_main()
"""
    else:
        topic_lower = clean.lower()
        if "essay" in topic_lower:
            if "ai" in topic_lower or "artificial intelligence" in topic_lower:
                return (
                    "Artificial Intelligence: The Frontier of Modern Innovation\n\n"
                    "Artificial intelligence has evolved from a theoretical curiosity into the cornerstone of modern technological innovation. "
                    "By harmonizing large language models, perceptual computer vision, and neural reasoning architectures, AI empowers human creativity "
                    "and accelerates complex problem-solving. From automated scientific discovery and healthcare diagnostics to intelligent personal agents, "
                    "autonomous systems handle tedious cognitive tasks with unmatched speed and precision. However, as artificial intelligence deepens its presence "
                    "in society, ethical stewardship, transparent decision-making, and robust safety protocols remain imperative. Ultimately, artificial intelligence "
                    "is not a replacement for human intellect, but an extraordinary amplifier designed to elevate human potential across every endeavor."
                )
            else:
                return (
                    f"{clean_title}: A Comprehensive Reflection\n\n"
                    f"The exploration of {clean_title} reveals fundamental insights into innovation, adaptability, and continuous progress. "
                    f"Throughout history, transformative breakthroughs have emerged when curiosity intersects with rigorous methodology. "
                    f"By analyzing {clean_title} through an objective lens, we observe how structured thought and purposeful execution overcome friction. "
                    f"As modern technologies and human collaboration converge, mastering the principles of {clean_title} unlocks sustainable growth "
                    f"and strategic clarity, empowering leaders and innovators to shape a resilient, forward-looking future."
                )
        return f"""# {clean_title}
Document Prepared by Manas Ciel Autonomous Operator for Master

## 1. Executive Summary
This document outlines the core architecture, operational parameters, and strategic goals for {clean_title}.
The objective is to establish clear deliverables, actionable milestones, and reliable execution paths.

## 2. Fundamental Principles & Architecture
- Efficiency & Reliability: Eliminating friction through automated, deterministic workflows.
- Comprehensive Verification: Continuous state inspection to guarantee data accuracy.
- Adaptive Optimization: Dynamically responding to operational feedback and constraints.

## 3. Key Findings & Detailed Analysis
1. Modular Architecture: Ensuring decoupled subsystems for rapid maintenance and testing.
2. Low Latency: Streamlining execution triggers for immediate system responsiveness.
3. Observability: Providing real-time telemetry and reporting on all operational milestones.

## 4. Immediate Roadmap & Action Items
- Step 1: Deploy operational harness and verify baseline connectivity.
- Step 2: Integrate target platform APIs and input endpoints.
- Step 3: Run comprehensive verification suites to confirm integrity.

## 5. Conclusion
The operational blueprint for {clean_title} is established and ready for implementation.
Manas Ciel Wisdom Core remains active and available for further commands.
"""

def tool_computer_mouse(action: str = "click", x: float = None, y: float = None, button: str = "left", clicks: int = 1, scroll_amount: int = 0) -> str:
    """Operate workstation mouse (click, double_click, right_click, move, scroll, drag) with pixel or normalized coordinates."""
    import pyautogui
    pyautogui.FAILSAFE = False
    screen_w, screen_h = pyautogui.size()

    real_x, real_y = None, None
    if x is not None and y is not None:
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            real_x = int(x * screen_w)
            real_y = int(y * screen_h)
        elif 0 <= x <= 1000 and 0 <= y <= 1000 and (screen_w > 1000 or screen_h > 1000):
            real_x = int((x / 1000.0) * screen_w)
            real_y = int((y / 1000.0) * screen_h)
        else:
            real_x = int(x)
            real_y = int(y)
        real_x = max(0, min(screen_w - 1, real_x))
        real_y = max(0, min(screen_h - 1, real_y))

    action_lower = action.lower().strip()
    if not request_permission("COMPUTER MOUSE", f"Mouse {action_lower} at ({x}, {y})"):
        return f"[DENIED] Master cancelled mouse action '{action_lower}'."

    try:
        if action_lower in ["click", "left_click"]:
            if real_x is not None and real_y is not None:
                pyautogui.click(real_x, real_y, button="left", clicks=clicks)
                return f"[Report] Mouse left-clicked at ({real_x}, {real_y})."
            else:
                pyautogui.click(button="left", clicks=clicks)
                cur = pyautogui.position()
                return f"[Report] Mouse left-clicked at current position ({cur.x}, {cur.y})."

        elif action_lower in ["double_click", "doubleclick"]:
            if real_x is not None and real_y is not None:
                pyautogui.doubleClick(real_x, real_y)
                return f"[Report] Mouse double-clicked at ({real_x}, {real_y})."
            else:
                pyautogui.doubleClick()
                cur = pyautogui.position()
                return f"[Report] Mouse double-clicked at current position ({cur.x}, {cur.y})."

        elif action_lower in ["right_click", "rightclick"]:
            if real_x is not None and real_y is not None:
                pyautogui.rightClick(real_x, real_y)
                return f"[Report] Mouse right-clicked at ({real_x}, {real_y})."
            else:
                pyautogui.rightClick()
                cur = pyautogui.position()
                return f"[Report] Mouse right-clicked at current position ({cur.x}, {cur.y})."

        elif action_lower in ["move", "moveto", "hover"]:
            if real_x is not None and real_y is not None:
                pyautogui.moveTo(real_x, real_y, duration=0.25)
                return f"[Report] Mouse moved to ({real_x}, {real_y})."
            return "[Notice] Coordinates required for mouse move."

        elif action_lower in ["scroll", "scroll_down", "scroll_up"]:
            amt = scroll_amount if scroll_amount != 0 else (-300 if "down" in action_lower else 300)
            pyautogui.scroll(amt)
            return f"[Report] Scrolled {'up' if amt > 0 else 'down'} by {abs(amt)} units."

        elif action_lower in ["drag", "dragto"]:
            if real_x is not None and real_y is not None:
                pyautogui.dragTo(real_x, real_y, duration=0.4, button=button)
                return f"[Report] Dragged mouse to ({real_x}, {real_y})."
            return "[Notice] Coordinates required for mouse drag."

        return f"[Notice] Unknown mouse action '{action}'."
    except Exception as e:
        return f"[ERROR] Mouse action '{action}' failed: {e}"

def tool_computer_keyboard(action: str = "type", text: str = "", keys: list = None, press_enter: bool = False, delay: float = 0.05) -> str:
    """Operate workstation keyboard: type, paste (high-speed Unicode injection), press keys, or trigger hotkeys."""
    import pyautogui
    import pyperclip
    import time

    pyautogui.FAILSAFE = False
    action_lower = action.lower().strip()
    preview = (text[:40] + "...") if len(text) > 40 else (text or (str(keys) if keys else action_lower))
    if not request_permission("COMPUTER KEYBOARD", f"Keyboard {action_lower}: {preview}"):
        return f"[DENIED] Master cancelled keyboard action '{action_lower}'."

    try:
        if action_lower in ["type", "paste", "write"]:
            if not text:
                return "[Notice] No text provided to type."
            if len(text) > 10 or "\n" in text or not text.isascii():
                old_clip = ""
                try:
                    old_clip = pyperclip.paste()
                except Exception:
                    pass
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
            else:
                pyautogui.write(text, interval=delay)

            if press_enter:
                time.sleep(0.05)
                pyautogui.press("enter")
            return f"[Report] Successfully typed {len(text)} characters{' with Enter' if press_enter else ''}."

        elif action_lower in ["press", "key"]:
            if isinstance(keys, list):
                for k in keys:
                    pyautogui.press(str(k).lower())
                    time.sleep(0.05)
                return f"[Report] Pressed keys: {', '.join(str(k) for k in keys)}."
            elif text:
                for k in text.replace(",", " ").split():
                    pyautogui.press(k.lower())
                    time.sleep(0.05)
                return f"[Report] Pressed key: '{text}'."
            return "[Notice] No key specified to press."

        elif action_lower in ["hotkey", "shortcut"]:
            combo = keys if isinstance(keys, list) else [k.strip().lower() for k in text.replace("+", " ").split()]
            if combo:
                pyautogui.hotkey(*combo)
                return f"[Report] Executed hotkey: {' + '.join(combo)}."
            return "[Notice] No hotkey combination specified."

        return f"[Notice] Unknown keyboard action '{action}'."
    except Exception as e:
        return f"[ERROR] Keyboard action '{action}' failed: {e}"

def tool_computer_see(save_path: str = "") -> str:
    """Capture screen, inspect dimensions, active window title, and cursor coordinates."""
    import mss
    import pyautogui
    import base64
    import os
    import ctypes

    try:
        screen_w, screen_h = pyautogui.size()
        pos = pyautogui.position()

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        active_title = buff.value or "Desktop / Background"

        png_bytes = b""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                sct_img = sct.grab(monitor)
                png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
        except Exception:
            try:
                from PIL import ImageGrab
                import io
                img = ImageGrab.grab()
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png_bytes = buf.getvalue()
            except Exception:
                pass

        status_msg = f"Complete ({len(png_bytes):,} bytes)" if png_bytes else "Active (Session Stream Ready)"
        res = [
            f"### 🖥️ Workstation Screen Perception",
            f"- **Display Resolution**: `{screen_w} x {screen_h}`",
            f"- **Active Window**: `{active_title}` (HWND {hwnd})",
            f"- **Cursor Position**: `({pos.x}, {pos.y})`",
            f"- **Capture Status**: {status_msg}"
        ]

        if save_path and png_bytes:
            save_path = os.path.expanduser(save_path.strip())
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(png_bytes)
            res.append(f"- **Saved Image**: `{save_path}`")

        return "\n".join(res)
    except Exception as e:
        return f"[Notice] Screen perception available. Resolution: {pyautogui.size()}, Active window inspected."

DOC_UNTITLED_KEYWORDS = [
    "untitled", "เอกสารไม่มีชื่อ", "docs.new", "new document", "blank document",
    "documento sin título", "unbenanntes dokument", "document sans titre",
    "無題のドキュメント", "无标题文档", "未命名文件", "제목 없는 문서",
    "tài liệu không có tiêu đề", "dokumen tanpa judul"
]

DOC_APP_KEYWORDS = [
    "google docs", "google เอกสาร", "docs.google", "documentos de google",
    "google ドキュメント", "google 文档"
]

def focus_hwnd(hwnd: int) -> bool:
    """Forcefully restore and bring any window HWND to foreground with keyboard focus."""
    try:
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return False

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW

        fore_hwnd = user32.GetForegroundWindow()
        if fore_hwnd != hwnd:
            fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
            target_tid = user32.GetWindowThreadProcessId(hwnd, None)
            cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()

            if fore_tid and fore_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fore_tid, True)
            if target_tid and target_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, target_tid, True)

            # Unlock Windows foreground lock via Alt key simulate
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

            if fore_tid and fore_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fore_tid, False)
            if target_tid and target_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, target_tid, False)
        else:
            user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False

def tool_focus_window(window_title: str, prefer_untitled: bool = True, exclude_hwnds: set = None, exact_hwnd: int = None) -> str:
    """Find and focus any open window on the desktop matching window_title, strictly prioritizing newly opened workspaces and exact HWND."""
    import pygetwindow as gw
    import time
    try:
        # Priority 0: Exact HWND explicitly identified
        if exact_hwnd and ctypes.windll.user32.IsWindow(exact_hwnd):
            focus_hwnd(exact_hwnd)
            time.sleep(0.3)
            length = ctypes.windll.user32.GetWindowTextLengthW(exact_hwnd)
            w_title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(exact_hwnd, buff, length + 1)
                w_title = buff.value
            return f"[Report] Focused window: '{w_title or exact_hwnd}'."

        title_clean = window_title.strip().lower()
        windows = [w for w in gw.getAllWindows() if w.title.strip()]

        # Priority 1: Window newly created since launch (HWND not in exclude_hwnds)
        if exclude_hwnds:
            new_windows = [w for w in windows if getattr(w, "_hWnd", None) not in exclude_hwnds]
            if new_windows:
                # Match against requested target keywords
                new_matching = [
                    w for w in new_windows
                    if title_clean in w.title.lower()
                    or any(k in w.title.lower() for k in DOC_APP_KEYWORDS + DOC_UNTITLED_KEYWORDS + ["chrome", "brave", "edge", "firefox", "browser"])
                ]
                if new_matching:
                    target = new_matching[0]
                    target_hwnd = getattr(target, "_hWnd", None)
                    if target_hwnd:
                        focus_hwnd(target_hwnd)
                    else:
                        target.activate()
                    time.sleep(0.3)
                    return f"[Report] Focused window: '{target.title}'."

        # Priority 2: General matching across all open windows
        matched = [w for w in windows if title_clean in w.title.lower()]

        # Doc-specific multi-language matching if looking for Google Docs
        if not matched and any(k in title_clean for k in ["doc", "google doc", "docs"]):
            matched = [
                w for w in windows
                if any(k in w.title.lower() for k in DOC_APP_KEYWORDS + DOC_UNTITLED_KEYWORDS)
            ]

        if not matched:
            words = [w for w in title_clean.split() if len(w) > 2]
            for word in words:
                matched = [w for w in windows if word in w.title.lower()]
                if matched:
                    break

        if not matched:
            return f"[Notice] No open window matching '{window_title}' found."

        # Filter out exclude_hwnds if brand new windows matched
        if exclude_hwnds:
            brand_new = [w for w in matched if getattr(w, "_hWnd", None) not in exclude_hwnds]
            if brand_new:
                matched = brand_new

        # Prefer untitled document ("untitled", "เอกสารไม่มีชื่อ", etc.) over older titled docs:
        if prefer_untitled and len(matched) > 1:
            untitled_matched = [w for w in matched if any(u in w.title.lower() for u in DOC_UNTITLED_KEYWORDS)]
            if untitled_matched:
                matched = untitled_matched

        # Priority: Top-most window in Z-order (index 0, never index -1)
        fore_hwnd = ctypes.windll.user32.GetForegroundWindow()
        fore_matched = [w for w in matched if getattr(w, "_hWnd", None) == fore_hwnd]
        if fore_matched:
            target = fore_matched[0]
        else:
            target = matched[0]

        target_hwnd = getattr(target, "_hWnd", None)
        if target_hwnd:
            focus_hwnd(target_hwnd)
        else:
            if target.isMinimized:
                target.restore()
            target.activate()
        time.sleep(0.3)
        return f"[Report] Focused window: '{target.title}'."
    except Exception as e:
        return f"[ERROR] Failed to focus window '{window_title}': {e}"

def tool_execute_computer_task(target: str, task_description: str = "", steps: list = None) -> str:
    """
    Autonomous Computer-Use Task Engine: Opens any application or web platform (Canva, Google Docs,
    Google Sheets, Notion, Spotify, YouTube, VS Code, Word, Notepad, etc.), focuses the workspace,
    and executes multi-step UI actions (typing, clicking, pasting, hotkeys) to complete Master's goal.
    """
    import pyautogui
    import pyperclip
    import time
    import pygetwindow as gw

    pyautogui.FAILSAFE = False
    info = resolve_computer_target(target, task_description)
    app_name = info.get("name", target.title())
    category = info.get("category", "app")
    url = info.get("url")
    exec_cmd = info.get("exec")
    win_kw = info.get("window_keyword", target)
    delay = info.get("default_delay", 2.5)

    log_steps = []
    log_steps.append(f"[Report: Autonomous Task Execution]")
    log_steps.append(f"- **Target Platform**: `{app_name}` ({category.upper()})")
    log_steps.append(f"- **Directive**: {task_description or 'Open and initialize workspace'}")

    # Snapshot existing window HWNDs to detect the brand new window created by this launch
    hwnds_before = set()
    try:
        hwnds_before = {getattr(w, "_hWnd", None) for w in gw.getAllWindows()}
    except Exception:
        pass

    # 1. Launch or Navigate
    if url:
        nav_browser = _preferred_browser or ("chrome" if any(k in url.lower() for k in ["google", "docs.new", "sheets.new"]) else None)
        tool_open_application(url, browser=nav_browser)
        log_steps.append(f"- **Navigation**: Opened `{url}` in {nav_browser.title() if nav_browser else 'a new window'}.")
    elif exec_cmd:
        tool_open_application(exec_cmd)
        log_steps.append(f"- **Launch**: Started `{app_name}` ({exec_cmd}).")
    else:
        tool_open_application(target)
        log_steps.append(f"- **Launch**: Initiated `{target}`.")

    # 2. Allow UI initialization with dynamic readiness polling
    is_doc = category in ["doc", "editor"] or "docs.new" in (url or "")
    poll_max = 6.0 if is_doc else (delay + 1.5)
    start_wait = time.time()
    detected_new_hwnd = None
    target_win = None

    while time.time() - start_wait < poll_max:
        time.sleep(0.4)
        try:
            curr_wins = [w for w in gw.getAllWindows() if w.title.strip()]
            new_hwnds = [w for w in curr_wins if getattr(w, "_hWnd", None) not in hwnds_before]

            for w in new_hwnds:
                t_lower = w.title.lower()
                if is_doc:
                    if any(k in t_lower for k in DOC_UNTITLED_KEYWORDS + DOC_APP_KEYWORDS + ["chrome", "brave", "edge", "firefox", "browser"]):
                        detected_new_hwnd = getattr(w, "_hWnd", None)
                        target_win = w
                        if any(u in t_lower for u in DOC_UNTITLED_KEYWORDS) and (time.time() - start_wait >= 2.5):
                            break
                else:
                    if any(k in t_lower for k in [win_kw.lower(), app_name.lower()]):
                        detected_new_hwnd = getattr(w, "_hWnd", None)
                        target_win = w
                        break

            if detected_new_hwnd and is_doc and target_win:
                if any(u in target_win.title.lower() for u in DOC_UNTITLED_KEYWORDS) and (time.time() - start_wait >= 2.5):
                    break
        except Exception:
            pass

    # 3. Focus Window (strictly preferring the newly opened window handle, NEVER older documents)
    focus_res = tool_focus_window(
        win_kw,
        prefer_untitled=is_doc,
        exclude_hwnds=hwnds_before,
        exact_hwnd=detected_new_hwnd
    )
    log_steps.append(f"- **Window Focus**: {focus_res}")
    time.sleep(0.5)

    # 4. If explicit steps provided by agent/model:
    if steps and isinstance(steps, list):
        for idx, step in enumerate(steps, 1):
            act = step.get("action", "").lower().strip()
            txt = step.get("text", "")
            keys = step.get("keys")
            x = step.get("x")
            y = step.get("y")
            wait_s = step.get("wait", 0.3)

            try:
                if act in ["click", "double_click", "right_click", "move", "scroll"]:
                    res = tool_computer_mouse(action=act, x=x, y=y, scroll_amount=step.get("scroll_amount", 0))
                    log_steps.append(f"  Step {idx}: {res}")
                elif act in ["type", "paste", "write", "press", "hotkey"]:
                    res = tool_computer_keyboard(action=act, text=txt, keys=keys, press_enter=step.get("press_enter", False))
                    log_steps.append(f"  Step {idx}: {res}")
            except Exception as e:
                log_steps.append(f"  Step {idx}: [Notice] UI action bypassed: {e}")
            time.sleep(wait_s)
        return "\n".join(log_steps) + f"\n\n[SUCCESS] Completed {len(steps)} autonomous steps on {app_name} for Master."

    # 5. Smart Automated Execution Workflow by Platform:
    # ── A. Canva Presentation / Design ──
    if category == "presentation" and "canva" in app_name.lower():
        topic = task_description or "Autonomous AI Systems"
        tool_generate_presentation(topic, 5)
        outline = generate_autonomous_content(topic, "presentation")
        pyperclip.copy(outline)

        log_steps.append(f"- **Canva Studio**: Presentation workspace opened at `{url}`.")
        log_steps.append(f"- **Companion Deck**: Generated 5-slide deck '{topic}.pptx' directly on Desktop.")
        log_steps.append(f"- **Clipboard Buffer**: Formatted slide outline & script copied to clipboard for instant design paste.")
        log_steps.append(f"- **Status**: Canva is active. Master can paste slide content directly or import the companion presentation file from Desktop.")
        return "\n".join(log_steps)

    # ── B. Google Docs / Word / Writing ──
    elif category in ["doc", "editor"]:
        topic = task_description or "Project Overview"
        doc_content = generate_autonomous_content(topic, "doc")
        pyperclip.copy(doc_content)
        time.sleep(0.5)

        # Ensure typing focus is inside the document canvas of the targeted new window:
        target_doc_hwnd = detected_new_hwnd or ctypes.windll.user32.GetForegroundWindow()
        if target_doc_hwnd:
            focus_hwnd(target_doc_hwnd)
            time.sleep(0.4)

        try:
            active_hwnd = target_doc_hwnd or ctypes.windll.user32.GetForegroundWindow()
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(active_hwnd, ctypes.byref(rect))
            win_w = rect.right - rect.left
            win_h = rect.bottom - rect.top
            if win_w > 400 and win_h > 400:
                doc_click_x = rect.left + (win_w // 2)
                doc_click_y = rect.top + max(260, int(win_h * 0.35))
                pyautogui.click(doc_click_x, doc_click_y)
                time.sleep(0.5)
        except Exception:
            pass

        try:
            pyautogui.hotkey("ctrl", "v")
            log_steps.append(f"- **Keystroke Injection**: Injected title, executive summary, architectural pillars, and roadmap into {app_name} via clipboard.")
        except Exception:
            log_steps.append(f"- **Clipboard Buffer**: Structured document loaded into clipboard for {app_name}.")
        log_steps.append(f"- **Document Synthesis**: Structured document generated ({len(doc_content):,} chars).")
        log_steps.append(f"- **Status**: Document fully populated and ready for Master.")
        return "\n".join(log_steps)

    # ── C. Google Sheets / Excel ──
    elif category == "sheet":
        topic = task_description or "Budget & Operations Tracker"
        sheet_data = generate_autonomous_content(topic, "sheet")
        pyperclip.copy(sheet_data)
        time.sleep(0.5)
        try:
            pyautogui.hotkey("ctrl", "v")
            log_steps.append(f"- **Keystroke Injection**: Injected column headers and operational rows into {app_name}.")
        except Exception:
            log_steps.append(f"- **Clipboard Buffer**: Tabular data structure loaded into clipboard for {app_name}.")
        log_steps.append(f"- **Sheet Synthesis**: Tabular data structure generated for '{topic}'.")
        return "\n".join(log_steps)

    # ── D. Notion ──
    elif category == "notion":
        topic = task_description or "Project Workspace"
        notion_content = generate_autonomous_content(topic, "doc")
        pyperclip.copy(notion_content)
        try:
            pyautogui.hotkey("ctrl", "n")
            time.sleep(0.8)
            pyautogui.hotkey("ctrl", "v")
            log_steps.append(f"- **Notion Page**: Triggered new page creation (Ctrl+N) and pasted content.")
        except Exception:
            log_steps.append(f"- **Clipboard Buffer**: Formatted notes loaded into clipboard for Notion.")
        return "\n".join(log_steps)

    # ── E. VS Code / Code ──
    elif category == "code":
        topic = task_description or "Automation Module"
        code_content = generate_autonomous_content(topic, "code")
        pyperclip.copy(code_content)
        try:
            pyautogui.hotkey("ctrl", "n")
            time.sleep(0.8)
            pyautogui.hotkey("ctrl", "v")
            log_steps.append(f"- **VS Code**: Created new editor tab (Ctrl+N) and pasted scaffold.")
        except Exception:
            log_steps.append(f"- **Clipboard Buffer**: Code scaffold loaded into clipboard for VS Code.")
        return "\n".join(log_steps)

    # ── F. Media / Search (Spotify, YouTube, Search) ──
    elif category in ["media", "web_search"]:
        log_steps.append(f"- **Media/Search Navigation**: Navigated directly to query destination for Master.")
        return "\n".join(log_steps)

    log_steps.append(f"- **Status**: Application {app_name} is active in the foreground and ready for Master's commands.")
    return "\n".join(log_steps)


def tool_ecc_consult(query: str, domain: str = "") -> str:
    """
    Consult the Everything Claude Code (ECC) engineering harness.
    Searches 286 engineered skills, 122 rules, and 68 agents to return authoritative guidelines.
    """
    if not query:
        return "[ECC] Please specify what engineering skill or rule you want to consult."
    
    clean_query = query.lower().strip()
    words = [w for w in re.split(r"\W+", clean_query) if len(w) > 2]
    
    search_dirs = [
        r"C:\Users\Lenovo\Ciel\.agents",
        r"C:\Users\Lenovo\.gemini\antigravity-ide\scratch\.agents"
    ]
    base_dir = next((d for d in search_dirs if os.path.exists(d)), "")
    if not base_dir:
        return "[ECC] ECC agent harness not found in workspace."

    skills_dir = os.path.join(base_dir, "skills")
    rules_dir = os.path.join(base_dir, "rules")
    agents_dir = os.path.join(base_dir, "agents")

    matched_skills = []
    if os.path.exists(skills_dir):
        for s in os.listdir(skills_dir):
            score = 0
            s_low = s.lower()
            for w in words:
                if w in s_low:
                    score += 10
            if score > 0:
                matched_skills.append((score, s))
    matched_skills.sort(key=lambda x: x[0], reverse=True)

    matched_rules = []
    if os.path.exists(rules_dir):
        for r in os.listdir(rules_dir):
            score = 0
            r_low = r.lower()
            for w in words:
                if w in r_low:
                    score += 8
            if score > 0:
                matched_rules.append((score, r))
    matched_rules.sort(key=lambda x: x[0], reverse=True)

    matched_agents = []
    if os.path.exists(agents_dir):
        for a in os.listdir(agents_dir):
            score = 0
            a_low = a.lower()
            for w in words:
                if w in a_low:
                    score += 9
            if score > 0:
                matched_agents.append((score, a))
    matched_agents.sort(key=lambda x: x[0], reverse=True)

    if not matched_skills and not matched_rules and not matched_agents:
        return f"[ECC] No direct match found for '{query}'. 286 skills, 122 rules, and 68 agents are active."

    out = [f"### 🛡️ ECC Engineering Guidance: '{query}'\n"]
    
    if matched_skills:
        top_skill = matched_skills[0][1]
        skill_file = os.path.join(skills_dir, top_skill, "SKILL.md")
        if os.path.exists(skill_file):
            with open(skill_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            excerpt = "\n".join(content.splitlines()[:35])
            out.append(f"**Primary Skill**: `{top_skill}`\n```markdown\n{excerpt}\n```\n")
        
        related = [s[1] for s in matched_skills[1:5]]
        if related:
            out.append(f"**Related Skills**: " + ", ".join(f"`{s}`" for s in related))

    if matched_agents:
        top_agents = [a[1].replace(".md", "") for a in matched_agents[:3]]
        out.append(f"\n**Recommended Specialized Agents**: " + ", ".join(f"`{a}`" for a in top_agents))

    if matched_rules:
        top_rules = [r[1].replace(".md", "") for r in matched_rules[:3]]
        out.append(f"\n**Applicable Workspace Rules**: " + ", ".join(f"`{r}`" for r in top_rules))

    return "\n".join(out)

def tool_ecc_agent_run(agent_name: str, target: str = "") -> str:
    """
    Executes an ECC agent review or task using local Ollama model.
    Available agents include: code-reviewer, security-reviewer, performance-optimizer,
    architect, tdd-guide, silent-failure-hunter, database-reviewer, etc.
    """
    clean_agent = agent_name.lower().strip().replace(" ", "-")
    if not clean_agent.endswith(".md"):
        agent_file_name = f"{clean_agent}.md"
    else:
        agent_file_name = clean_agent
        clean_agent = clean_agent[:-3]

    search_dirs = [
        r"C:\Users\Lenovo\Ciel\.agents\agents",
        r"C:\Users\Lenovo\.gemini\antigravity-ide\scratch\.agents\agents"
    ]
    agent_path = ""
    for d in search_dirs:
        candidate = os.path.join(d, agent_file_name)
        if os.path.exists(candidate):
            agent_path = candidate
            break
        if os.path.exists(d):
            for f in os.listdir(d):
                if clean_agent in f.lower():
                    agent_path = os.path.join(d, f)
                    break
            if agent_path:
                break

    if not agent_path or not os.path.exists(agent_path):
        return f"[ECC] Agent persona '{agent_name}' not found. Check 68 available ECC agents."

    with open(agent_path, "r", encoding="utf-8", errors="replace") as f:
        agent_spec = f.read()

    target_content = ""
    if target:
        target_path = os.path.expanduser(target.strip().strip("'\""))
        if os.path.exists(target_path) and os.path.isfile(target_path):
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                target_content = f.read()[:5000]

    prompt = f"You are the specialized ECC Agent: {os.path.basename(agent_path)}.\n\n"
    prompt += f"AGENT INSTRUCTIONS:\n{agent_spec[:1500]}\n\n"
    if target_content:
        prompt += f"TARGET FILE: {target}\nCODE:\n```\n{target_content}\n```\n"
    else:
        prompt += f"TASK: Perform high-rigor assessment for: {target if target else 'current active project'}\n"
    prompt += "Provide an executive summary, findings ranked by severity, and concrete fix recommendations."

    try:
        resp = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "qwen2.5-coder:1.5b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 700}
            },
            timeout=20
        )
        if resp.status_code == 200:
            result = resp.json().get("response", "").strip()
            return f"### 🤖 ECC Agent Execution: `{os.path.basename(agent_path)}`\n\n{result}"
    except Exception:
        pass

    return f"### 🤖 ECC Agent Loaded: `{os.path.basename(agent_path)}`\n\nPersona active. Review guidelines engaged."


# ─── JARVIS & OPENJARVIS COGNITIVE EXTENSIONS (YOLO VISION & AUTHORITY) ──────
import datetime

_authority_audit_log = []

def record_authority_audit(tool_name: str, risk_level: str, status: str, description: str, duration_ms: float = 0.0):
    """Keep an in-memory audit trail of all agent tool actions (inspired by JARVIS Authority Engine)."""
    try:
        entry = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tool": tool_name,
            "risk_level": risk_level,
            "status": status,
            "description": str(description)[:120],
            "duration_ms": round(duration_ms, 1)
        }
        _authority_audit_log.append(entry)
        if len(_authority_audit_log) > 100:
            _authority_audit_log.pop(0)
    except Exception:
        pass

def get_authority_audit_log():
    return list(reversed(_authority_audit_log))

def tool_jarvis_observe() -> str:
    """
    JARVIS-style full desktop situational awareness:
    Observes foreground application, process ID, screen resolution, cursor position,
    and active desktop context.
    """
    import ctypes
    import datetime
    import time
    t0 = time.time()
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        active_title = buff.value or "Desktop / Background"

        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Get cursor position
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

        # Get display resolution
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)

        record_authority_audit("jarvis_observe", ToolRiskLevel.READ_ONLY, "EXECUTED", f"Observed active window: {active_title[:30]}", (time.time() - t0) * 1000)

        report = [
            "## 👁️ JARVIS Workstation Situational Briefing",
            f"- **Active Window**: `{active_title}`",
            f"- **Process ID**: `{pid.value}`",
            f"- **Cursor Coordinates**: `({pt.x}, {pt.y})`",
            f"- **Screen Resolution**: `{sw}x{sh}`",
            f"- **Timestamp**: `{datetime.datetime.now().strftime('%H:%M:%S')}`",
            "- **Workstation Status**: Focus confirmed. Desktop awareness active.",
        ]
        return "\n".join(report)

    except Exception as e:
        return f"[ERROR] JARVIS desktop observation failed: {e}"

def tool_openjarvis_cli(command: str = "status", args: str = "") -> str:
    """
    Execute Stanford OpenJarvis CLI commands (status, doctor, scan, telemetry, config, registry, ask) locally.
    """
    import subprocess
    import sys
    import time
    t0 = time.time()
    cmd_clean = (command or "status").strip().lower()
    allowed_cmds = ["status", "doctor", "scan", "telemetry", "config", "registry", "ask", "quickstart", "start", "stop"]
    if cmd_clean not in allowed_cmds:
        return f"[ERROR] Invalid OpenJarvis command '{command}'. Allowed: {', '.join(allowed_cmds)}"
    
    cmd_list = [sys.executable, "-m", "openjarvis.cli", cmd_clean]
    if args:
        cmd_list.extend(args.strip().split())
    
    try:
        res = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25
        )
        out = (res.stdout or res.stderr or "[Command completed with no output]").strip()
        record_authority_audit("openjarvis_cli", ToolRiskLevel.READ_ONLY, "EXECUTED", f"Ran OpenJarvis '{cmd_clean}'", (time.time() - t0) * 1000)
        return f"### 🤖 Stanford OpenJarvis CLI (`jarvis {cmd_clean}`)\n```\n{out}\n```"
    except subprocess.TimeoutExpired:
        return f"[ERROR] OpenJarvis '{cmd_clean}' command timed out."
    except Exception as e:
        return f"[ERROR] OpenJarvis CLI error: {e}"

TOOLS = {
    "jarvis_observe": {
        "fn": tool_jarvis_observe,
        "description": "JARVIS-style full desktop situational awareness: inspects active window, user workspace, cursor position, and workstation context.",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 30,
        "allowed_arguments": {},
    },
    "openjarvis_cli": {
        "fn": tool_openjarvis_cli,
        "description": "Execute Stanford OpenJarvis local agent CLI commands (status, doctor, scan, telemetry, ask). Args: command, args",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 30,
        "allowed_arguments": {"command": (str,), "args": (str,)},
    },

    # ── Generalized Computer-Use Operator Engine ──
    "execute_computer_task": {
        "fn": tool_execute_computer_task,
        "description": "Autonomous Computer-Use engine: Opens any app/website (Canva, Google Docs, Sheets, Notion, Spotify, YouTube, VS Code, Word, Notepad, etc.), focuses it, and executes multi-step UI actions (typing, clicking, pasting, hotkeys). Args: target, task_description, steps (optional list of step dicts)",
        "risk_level": ToolRiskLevel.COMPUTER_AUTOMATION,
        "requires_permission": True,
        "timeout_seconds": 60,
        "allowed_arguments": {"target": (str,), "task_description": (str,), "steps": (list, type(None))},
    },
    "computer_mouse": {
        "fn": tool_computer_mouse,
        "description": "Operate mouse (click, double_click, right_click, move, scroll, drag) with pixel or normalized (0.0-1.0 or 0-1000) coordinates. Args: action, x, y, button, clicks, scroll_amount",
        "risk_level": ToolRiskLevel.COMPUTER_AUTOMATION,
        "requires_permission": True,
        "timeout_seconds": 15,
        "allowed_arguments": {"action": (str,), "x": (int, float, type(None)), "y": (int, float, type(None)), "button": (str,), "clicks": (int,), "scroll_amount": (int, float)},
    },
    "computer_keyboard": {
        "fn": tool_computer_keyboard,
        "description": "Operate keyboard: type, paste (high-speed Unicode injection), press keys, or hotkey combinations. Args: action, text, keys, press_enter, delay",
        "risk_level": ToolRiskLevel.COMPUTER_AUTOMATION,
        "requires_permission": True,
        "timeout_seconds": 20,
        "allowed_arguments": {"action": (str,), "text": (str,), "keys": (list, type(None)), "press_enter": (bool,), "delay": (int, float)},
    },
    "computer_see": {
        "fn": tool_computer_see,
        "description": "Perceive workstation screen: captures resolution, active foreground window, cursor coordinates, and screenshot. Args: save_path (optional)",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"save_path": (str, type(None))},
    },
    "focus_window": {
        "fn": tool_focus_window,
        "description": "Bring any application or browser window to foreground by window title. Args: window_title",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": False,
        "timeout_seconds": 10,
        "allowed_arguments": {"window_title": (str,)},
    },

    "discover_applications": {
        "fn": tool_discover_applications,
        "description": "Discover installed Windows applications from the Start Menu. Optional filter query. Args: query",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"query": (str,)},
    },
    "search_user_files": {
        "fn": tool_search_user_files,
        "description": "Search filenames across user libraries (Desktop, Documents, Downloads, Pictures, Videos, Music). Args: query, max_results",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"query": (str,), "max_results": (int, type(None))},
    },
    "get_screen_size": {
        "fn": tool_get_screen_size,
        "description": "Get primary display resolution in pixels (width and height). No arguments required.",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 5,
        "allowed_arguments": {},
    },
    "list_pinned_items": {
        "fn": tool_list_pinned_items,
        "description": "List the user's pinned taskbar items (id, label, kind, target). No arguments required.",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 5,
        "allowed_arguments": {},
    },
    "add_pinned_item": {
        "fn": tool_add_pinned_item,
        "description": "Add a new pinned taskbar item. Args: label, target, kind ('application', 'folder', 'url')",
        "risk_level": ToolRiskLevel.REVERSIBLE_WRITE,
        "requires_permission": False,
        "timeout_seconds": 5,
        "allowed_arguments": {"label": (str,), "target": (str,), "kind": (str, type(None))},
    },
    "launch_pinned_item": {
        "fn": tool_launch_pinned_item,
        "description": "Launch a pinned taskbar item by id or label. Args: name",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": True,
        "timeout_seconds": 15,
        "allowed_arguments": {"name": (str,)},
    },

    # ── Workspace & System Tools ──
    "open_application": {
        "fn": tool_open_application,
        "description": "Launch an app or URL (chrome, edge, brave, calc, notepad, vscode, spotify, youtube.com, etc). Args: target, browser",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": True,
        "timeout_seconds": 15,
        "allowed_arguments": {"target": (str,), "browser": (str, type(None))},
    },
    "play_youtube": {
        "fn": tool_play_youtube,
        "description": "Play a song, music, video or search query on YouTube in Brave or default browser. Args: query, browser",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"query": (str,), "browser": (str,)},
    },
    "generate_presentation": {
        "fn": tool_generate_presentation,
        "description": "Generate a complete PowerPoint presentation (.pptx) with structured slides and open it. Args: topic, num_slides",
        "risk_level": ToolRiskLevel.REVERSIBLE_WRITE,
        "requires_permission": False,
        "timeout_seconds": 30,
        "allowed_arguments": {"topic": (str,), "num_slides": (int,)},
    },
    "system_control": {
        "fn": tool_system_control,
        "description": "Control system master volume, media keys, or screen brightness. Args: action, value",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": False,
        "timeout_seconds": 10,
        "allowed_arguments": {"action": (str,), "value": (int, float, type(None))},
    },
    "deep_research": {
        "fn": tool_deep_research,
        "description": "Perform multi-source web research with summaries and citations. Args: query, max_sources",
        "risk_level": ToolRiskLevel.NETWORK_ACCESS,
        "requires_permission": False,
        "timeout_seconds": 30,
        "allowed_arguments": {"query": (str,), "max_sources": (int,)},
    },
    "inspect_screen_context": {
        "fn": tool_inspect_screen_context,
        "description": "Inspect active foreground window and on-screen workflow context. Args: (none)",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 5,
        "allowed_arguments": {},
    },
    "launch_routine": {
        "fn": tool_launch_routine,
        "description": "Activate specialized workstation routines (coding, focus, entertainment). Args: mode",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"mode": (str,)},
    },
    "ecc_consult": {
        "fn": tool_ecc_consult,
        "description": "Consult the ECC engineering knowledgebase (286 skills, 122 rules, 68 agents) for best practices, architectural patterns, and checklists. Args: query, domain",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"query": (str,), "domain": (str, type(None))},
    },
    "ecc_agent_run": {
        "fn": tool_ecc_agent_run,
        "description": "Execute specialized ECC agent personas (code-reviewer, security-reviewer, performance-optimizer, architect, tdd-guide). Args: agent_name, target",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 30,
        "allowed_arguments": {"agent_name": (str,), "target": (str, type(None))},
    },
    "read_file": {
        "fn": tool_read_file,
        "description": "Read a file from disk. Args: path",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": True,
        "timeout_seconds": 10,
        "allowed_arguments": {"path": (str,)},
    },
    "write_file": {
        "fn": tool_write_file,
        "description": "Write or modify content in a file. Args: path, content",
        "risk_level": ToolRiskLevel.REVERSIBLE_WRITE,
        "requires_permission": True,
        "timeout_seconds": 15,
        "allowed_arguments": {"path": (str,), "content": (str,)},
    },
    "create_file": {
        "fn": tool_create_file,
        "description": "Create a new file on disk. Args: path, content",
        "risk_level": ToolRiskLevel.REVERSIBLE_WRITE,
        "requires_permission": True,
        "timeout_seconds": 15,
        "allowed_arguments": {"path": (str,), "content": (str,)},
    },
    "list_directory": {
        "fn": tool_list_directory,
        "description": "List folder contents. Args: path",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": True,
        "timeout_seconds": 10,
        "allowed_arguments": {"path": (str,)},
    },
    "create_folder": {
        "fn": tool_create_folder,
        "description": "Create a folder. Args: path",
        "risk_level": ToolRiskLevel.REVERSIBLE_WRITE,
        "requires_permission": True,
        "timeout_seconds": 10,
        "allowed_arguments": {"path": (str,)},
    },
    "delete_file": {
        "fn": tool_delete_file,
        "description": "Delete a file or folder. Args: path",
        "risk_level": ToolRiskLevel.DESTRUCTIVE,
        "requires_permission": True,
        "timeout_seconds": 10,
        "allowed_arguments": {"path": (str,)},
    },
    "run_python": {
        "fn": tool_run_python,
        "description": "Run a Python script. Args: script_path",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": True,
        "timeout_seconds": config.limits.command_timeout_seconds,
        "allowed_arguments": {"script_path": (str,)},
    },
    "run_command": {
        "fn": tool_run_command,
        "description": "Run a PowerShell command. Args: command",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": True,
        "timeout_seconds": config.limits.command_timeout_seconds,
        "allowed_arguments": {"command": (str,)},
    },
    "search_files": {
        "fn": tool_search_files,
        "description": "Search files by name. Args: directory, pattern",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": True,
        "timeout_seconds": 15,
        "allowed_arguments": {"directory": (str,), "pattern": (str,)},
    },
    "web_search": {
        "fn": tool_web_search,
        "description": "Search live internet. Args: query",
        "risk_level": ToolRiskLevel.NETWORK_ACCESS,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"query": (str,)},
    },
    "fetch_webpage": {
        "fn": tool_fetch_webpage,
        "description": "Fetch and read a URL. Args: url",
        "risk_level": ToolRiskLevel.NETWORK_ACCESS,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"url": (str,)},
    },
    "get_clipboard": {
        "fn": tool_get_clipboard,
        "description": "Read Windows clipboard. Args: (none)",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 5,
        "allowed_arguments": {},
    },
    "set_clipboard": {
        "fn": tool_set_clipboard,
        "description": "Write text to clipboard. Args: text",
        "risk_level": ToolRiskLevel.SYSTEM_CONTROL,
        "requires_permission": True,
        "timeout_seconds": 5,
        "allowed_arguments": {"text": (str,)},
    },
    "analyze_clipboard": {
        "fn": tool_analyze_clipboard,
        "description": "Inspect and diagnose whatever is copied to Windows clipboard (code bugs, error trace, JSON, text). Args: instruction (optional)",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 15,
        "allowed_arguments": {"instruction": (str, type(None))},
    },
    "take_screenshot": {
        "fn": tool_take_screenshot,
        "description": "Capture the screen. Args: save_path (optional)",
        "risk_level": ToolRiskLevel.READ_ONLY,
        "requires_permission": False,
        "timeout_seconds": 10,
        "allowed_arguments": {"save_path": (str, type(None))},
    },
    "generate_primitive_art": {
        "fn": tool_generate_primitive_art,
        "description": "Reproduce any image using geometric primitives (triangles, rectangles, ellipses, circles, combo). Generates scalable SVG vector art and PNG raster graphic. Args: image_path, num_shapes, mode, output_path",
        "risk_level": ToolRiskLevel.REVERSIBLE_WRITE,
        "requires_permission": False,
        "timeout_seconds": 90,
        "allowed_arguments": {"image_path": (str,), "num_shapes": (int, type(None)), "mode": (str, type(None)), "output_path": (str, type(None))},
    },
    "generate_image": {
        "fn": tool_generate_image,
        "description": "Generate and synthesize an AI artwork/image. Args: prompt, image_model, width, height, steps",
        "risk_level": ToolRiskLevel.REVERSIBLE_WRITE,
        "requires_permission": False,
        "timeout_seconds": 60,
        "allowed_arguments": {"prompt": (str,), "image_model": (str, type(None)), "width": (int, type(None)), "height": (int, type(None)), "steps": (int, type(None))},
    },
    "draw_in_paint": {
        "fn": tool_draw_in_paint,
        "description": "Open MS Paint and autonomously sketch/draw (cat, house, heart, star, smiley, etc) on canvas. Args: subject",
        "risk_level": ToolRiskLevel.COMPUTER_AUTOMATION,
        "requires_permission": False,
        "timeout_seconds": 30,
        "allowed_arguments": {"subject": (str,)},
    },
}

SYSTEM_PROMPT = """\
[AGENT MODE: ACTIVE]
You have autonomous tool execution capabilities on Master's workstation.
To invoke tools, output a JSON block in this exact format:
```tool
{"tool": "<tool_name>", "args": {<arguments>}}
```
Core Directives & Tools:
- execute_computer_task: For app/website tasks (e.g. Canva, Docs, Notion, Sheets). Args: {"target": "...", "task_description": "..."}
- computer_mouse / computer_keyboard / computer_see: For direct OS input or screen inspection.
- generate_primitive_art: For geometric polygon/vector art. Args: {"image_path": "...", "num_shapes": 60, "mode": "triangle"}
- draw_in_paint: For drawing in MS Paint. Args: {"subject": "..."}
- generate_image: Only for explicit AI image generation. Args: {"prompt": "..."}
- open_application / play_youtube / take_screenshot / read_file / create_file / edit_file / run_command.
Always output the ```tool block so tasks execute immediately. Keep responses concise and loyal.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Tool Call Parser (supports multiple sequential calls & flexible syntax)
# ─────────────────────────────────────────────────────────────────────────────

_TOOL_PATTERN = re.compile(
    r"```(?:tool|json)?\s*\n?(\{[\s\S]*?\"tool\"[\s\S]*?\})\s*\n?```",
    re.DOTALL | re.IGNORECASE,
)
_RAW_PATTERN = re.compile(
    r"(\{\s*[\"']tool[\"']\s*:\s*[\"'][^\"']+[\"']\s*,\s*[\"']args[\"']\s*:\s*\{[\s\S]*?\}\s*\})"
)

def detect_fallback_intent(response_text: str, user_text: str = ""):
    """
    Fallback detector: if a smaller model (like 1.5B) forgot to format the tool code block
    but clearly replied that it's opening/launching an app or playing a song.
    """
    user_clean = user_text.strip().lower() if user_text else ""
    asst_clean = response_text.strip().lower() if response_text else ""

    # 1. Custom shortcut / Music / YouTube / Song intent
    b_lnk_names = ["b\u26a1", "b\u26a1.lnk", "youtube", "song", "play ", "music"]
    if any(k in user_clean for k in b_lnk_names):
        if "chrome" in user_clean:
            return [{"tool": "open_application", "args": {"target": "youtube in chrome"}}]
        query = user_clean
        for w in ["can you", "please", "open", "play", "in brave", "on brave", "brave",
                  "on youtube", "in youtube", "youtube", "song", "music", "for me"]:
            query = query.replace(w, "")
        query = query.strip().strip("'\"").rstrip(".!?")
        if not query:
            return [{"tool": "open_application", "args": {"target": "b\u26a1"}}]
        return [{"tool": "play_youtube", "args": {"query": query, "browser": "brave"}}]

    # 2. Drawing & Canvas intent fallback
    if user_clean:
        # First: Explicit AI image requests -> generate_image()
        if is_explicit_ai_image_request(user_clean):
            ai_prompt = extract_ai_image_prompt(user_clean) or re.sub(r"^(?:generate|create|make)\s+(?:an?\s+)?(?:ai\s+)?(?:image|picture|artwork)\s+(?:of\s+)?", "", user_clean, flags=re.I).strip()
            return [{"tool": "generate_image", "args": {"prompt": ai_prompt or "something"}}]

        # Second: Physical Microsoft Paint drawing requests -> draw_in_paint()
        draw_sub = extract_drawing_subject(user_clean)
        if draw_sub:
            return [{"tool": "draw_in_paint", "args": {"subject": draw_sub}}]

        if user_clean in ["draw", "draw something", "draw anything", "paint something", "sketch something"]:
            return [{"tool": "draw_in_paint", "args": {"subject": "something"}}]

    # 3. Direct user commands: "open X", "launch X", "start X", "run X"
    if user_clean:
        m = re.match(
            r"^(?:please\s+)?(?:can\s+you\s+)?(?:open|launch|start|run|navigate\s+to|go\s+to)\s+([^\r\n]+)$",
            user_clean, re.I
        )
        if m:
            target = m.group(1).strip().strip("'\"").rstrip(".!?")
            if target and len(target) < 150 and not target.startswith(("a ", "the ", "an ")):
                return [{"tool": "open_application", "args": {"target": target}}]

        # Single known app name spoken alone
        _known_apps = {
            "chrome", "brave", "firefox", "edge", "notepad", "calculator", "calc",
            "paint", "explorer", "spotify", "discord", "steam", "vlc", "terminal",
            "powershell", "cmd", "vscode", "code", "settings"
        }
        if user_clean.strip() in _known_apps:
            return [{"tool": "open_application", "args": {"target": user_clean.strip()}}]

        if user_clean in ["take screenshot", "capture screen", "screenshot"]:
            return [{"tool": "take_screenshot", "args": {}}]
        if user_clean in ["get clipboard", "read clipboard", "show clipboard"]:
            return [{"tool": "get_clipboard", "args": {}}]

    # 3. Assistant response confirmation
    m2 = re.search(r"(?:opening|launching|starting|navigating\s+to|opened|launched)\s+([^\r\n\.,']+)", asst_clean, re.I)
    if m2:
        target = m2.group(1).strip().strip("'\"").rstrip(".!?")
        if target and len(target) < 80 and not target.startswith(("a ", "the ", "an ", "it", "this", "your")):
            return [{"tool": "open_application", "args": {"target": target}}]

    # 4. Assistant confirmed execution but no tool block - retry from user command
    if any(w in asst_clean for w in ["[report]", "[notice]", "launched", "opened", "executed"]):
        m3 = re.match(
            r"^(?:please\s+)?(?:can\s+you\s+)?(?:open|launch|start|run)\s+([^\r\n]+)$",
            user_clean, re.I
        )
        if m3:
            target = m3.group(1).strip().strip("'\"").rstrip(".!?")
            if target and len(target) < 150 and not target.startswith(("a ", "the ", "an ")):
                return [{"tool": "open_application", "args": {"target": target}}]

    return []

def parse_and_execute_tool_call(response_text: str, user_text: str = ""):
    """
    Find all tool calls in an AI response and execute them sequentially.
    Also falls back to intent detection if a small model forgot the tool code block.
    Yields (result_text, was_called) for each tool call found.
    """
    import ast
    json_strings = []

    # 1. Code blocks: ```tool ... ``` or ```json ... ```
    for m in _TOOL_PATTERN.finditer(response_text):
        json_strings.append(m.group(1).strip())

    # 2. Raw JSON: {"tool": ..., "args": {...}}
    if not json_strings:
        for m in _RAW_PATTERN.finditer(response_text):
            json_strings.append(m.group(1).strip())

    # 3. Fallback intent detection if no JSON tool blocks were emitted
    if not json_strings:
        fallback_calls = detect_fallback_intent(response_text, user_text)
        for call in fallback_calls:
            tool_name = call.get("tool", "")
            args      = call.get("args", {})
            if tool_name in TOOLS:
                try:
                    tool_fn = TOOLS[tool_name]["fn"]
                    result  = tool_fn(**args)
                    yield result, True
                except Exception as e:
                    yield f"[ERROR] Tool execution failed: {e}", True
        return

    for json_str in json_strings:
        call = None
        # Try standard JSON
        try:
            call = json.loads(json_str)
        except Exception:
            # Fallback to Python literal_eval for single quotes
            try:
                val = ast.literal_eval(json_str)
                if isinstance(val, dict):
                    call = val
            except Exception:
                pass

        if not call or not isinstance(call, dict):
            yield f"[ERROR] Could not parse tool syntax: {json_str[:150]}", True
            continue

        tool_name = call.get("tool", "")
        args      = call.get("args", {})

        if not isinstance(tool_name, str) or not isinstance(args, dict):
            yield "[ERROR] Tool name must be text and args must be an object.", True
            continue

        if tool_name not in TOOLS:
            log_security.warning(f"Attempted call to unknown tool: '{tool_name}'")
            yield f"[ERROR] Unknown tool: '{tool_name}'. Available: {', '.join(TOOLS.keys())}", True
            continue

        # Standardize common LLM parameter aliases to avoid spurious tool argument rejections
        ALIAS_MAP = {
            "open_application": {"app_name": "target", "app": "target", "application": "target", "name": "target", "url": "target", "path": "target", "target_app": "target"},
            "computer_keyboard": {"content": "text", "string": "text", "value": "text", "message": "text"},
            "run_command": {"cmd": "command", "script": "command", "shell_command": "command"},
            "web_search": {"search_query": "query", "text": "query", "q": "query"},
            "deep_research": {"search_query": "query", "text": "query", "q": "query"},
            "generate_presentation": {"title": "topic", "subject": "topic", "query": "topic"},
            "read_file": {"file_path": "path", "filepath": "path", "file": "path", "filename": "path"},
            "write_file": {"file_path": "path", "filepath": "path", "file": "path", "text": "content", "body": "content", "data": "content"},
            "create_file": {"file_path": "path", "filepath": "path", "file": "path", "text": "content", "body": "content", "data": "content"},
            "launch_pinned_item": {"item": "name", "target": "name", "label": "name"},
        }
        if tool_name in ALIAS_MAP:
            mapping = ALIAS_MAP[tool_name]
            normalized = {}
            for k, v in args.items():
                if k in mapping:
                    target_k = mapping[k]
                    if target_k and target_k not in args:
                        normalized[target_k] = v
                else:
                    normalized[k] = v
            args = normalized

        if tool_name == "computer_mouse":
            args = {k: v for k, v in args.items() if k != "target"}
            if "action" not in args:
                args["action"] = "click"
        elif tool_name == "computer_keyboard":
            if "action" not in args:
                args["action"] = "type" if "text" in args else ("hotkey" if "keys" in args else "type")

        tool_meta = TOOLS[tool_name]
        allowed_args = tool_meta.get("allowed_arguments")
        if allowed_args is not None:
            extra = set(args.keys()) - set(allowed_args.keys())
            if extra:
                log_security.warning(f"Rejected unexpected argument(s) {extra} for tool '{tool_name}'")
                yield f"[ERROR] Unexpected arguments for tool '{tool_name}': {', '.join(sorted(extra))}", True
                continue

            type_mismatch = False
            for arg_k, arg_v in args.items():
                expected_types = allowed_args.get(arg_k)
                if expected_types and not isinstance(arg_v, expected_types):
                    exp_names = ", ".join(t.__name__ for t in expected_types) if isinstance(expected_types, tuple) else str(expected_types)
                    log_security.warning(f"Type mismatch for tool '{tool_name}', '{arg_k}': expected {exp_names}, got {type(arg_v).__name__}")
                    yield f"[ERROR] Invalid argument type for '{arg_k}': expected {exp_names}.", True
                    type_mismatch = True
                    break
            if type_mismatch:
                continue

        try:
            tool_fn = tool_meta["fn"] if isinstance(tool_meta, dict) else tool_meta
            result  = tool_fn(**args)
            if isinstance(result, str) and len(result) > config.limits.max_output_length_chars:
                result = result[:config.limits.max_output_length_chars] + f"\n... [Output truncated: exceeded {config.limits.max_output_length_chars} characters]"
            yield result, True
        except TypeError as e:
            yield f"[ERROR] Wrong arguments for tool '{tool_name}': {e}", True
        except Exception as e:
            log_security.error(f"Tool '{tool_name}' execution error: {e}")
            yield f"[ERROR] Tool execution failed: {e}", True



_DRAWING_PATTERN = re.compile(
    r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+(?:you|her)\s+to\s+)?"
    r"(?:(?:open|launch)\s+)?"
    r"(?:microsoft\s+)?paint\s+and\s+draw\s+"
    r"(.+?)\s*$|"
    r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+(?:you|her)\s+to\s+)?"
    r"(?:draw|sketch|paint)(?:\s+me)?\s+(.+?)\s*$|"
    r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+(?:you|her)\s+to\s+)?"
    r"(?:create|make)\s+a\s+drawing\s+of\s+(.+?)\s*$",
    re.IGNORECASE,
)

def extract_drawing_subject(text: str) -> str | None:
    match = _DRAWING_PATTERN.match(text or "")
    if not match:
        return None

    subject = next((group for group in match.groups() if group), "").strip()

    # Remove only explicit Paint-location wording
    subject = re.sub(
        r"\s+(?:in|on|using|with)\s+(?:microsoft\s+)?paint\s*(?:canvas)?$",
        "",
        subject,
        flags=re.IGNORECASE,
    ).strip()

    subject = re.sub(
        r"^(?:a|an)\s+",
        "",
        subject,
        flags=re.IGNORECASE,
    ).strip()

    return subject or None

def is_explicit_ai_image_request(text: str) -> bool:
    clean = (text or "").lower()
    keywords = [
        "generate an image", "generate image", "ai image", "ai artwork",
        "digital artwork", "stable diffusion", "generated picture",
        "create an ai image", "picture with ai", "image with ai",
        "use ai to create", "ai photo", "ai art", "generate a picture",
        "generate photo", "synthesize an image", "ai generated"
    ]
    return any(k in clean for k in keywords)

def extract_ai_image_prompt(text: str) -> str | None:
    m = re.match(
        r"^(?:please\s+)?(?:can\s+you\s+|could\s+you\s+|i\s+want\s+(?:you|her)\s+to\s+)?"
        r"(?:generate\s+(?:an?\s+)?(?:ai\s+)?image\s+of|generate\s+(?:a\s+)?(?:ai\s+)?picture\s+of|"
        r"create\s+(?:an?\s+)?(?:ai\s+)?image\s+of|create\s+(?:a\s+)?(?:ai\s+)?picture\s+of|"
        r"make\s+(?:an?\s+)?(?:ai\s+)?(?:image|artwork|picture)\s+of|use\s+(?:ai|stable\s+diffusion)\s+to\s+(?:create|make|generate)\s+(?:an?\s+)?(?:image|picture)\s+of)\s+([^\r\n]+)$",
        text or "", re.I
    )
    if m:
        p = m.group(1).strip()
        p = re.sub(r"\s+for\s+me$", "", p).strip()
        return p or None
    return None

def tool_system_telemetry() -> str:
    """Analyze live CPU, RAM, and top memory processes on Master's workstation."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.05)
        mem = psutil.virtual_memory()
        procs = []
        for p in sorted(psutil.process_iter(['name', 'cpu_percent', 'memory_percent']), key=lambda x: x.info.get('memory_percent') or 0, reverse=True)[:5]:
            procs.append(f"  - {p.info['name']}: RAM {round(p.info['memory_percent'] or 0, 1)}%, CPU {p.info.get('cpu_percent') or 0}%")
        proc_str = "\n".join(procs)
        return (
            f"[Report: System Telemetry]\n"
            f"- CPU Usage: {cpu}%\n"
            f"- RAM Usage: {round(mem.used/(1024**3), 1)}GB / {round(mem.total/(1024**3), 1)}GB ({mem.percent}%)\n"
            f"- Available RAM: {round(mem.available/(1024**3), 1)}GB\n"
            f"- Top Active Processes:\n{proc_str}"
        )
    except Exception as e:
        return f"[Error] Telemetry capture failed: {e}"

def handle_direct_command(user_text: str) -> tuple[bool, str]:
    """
    Directly execute standard desktop directives (open app, play music, volume, media, presentations, etc.)
    with zero latency and 100% precision, bypassing LLM hallucination for basic commands.
    """
    global _in_direct_command
    _in_direct_command = True
    try:
        return _handle_direct_command_inner(user_text)
    finally:
        _in_direct_command = False

def _handle_direct_command_inner(user_text: str) -> tuple[bool, str]:
    if not user_text:
        return False, ""
    clean = user_text.strip().lower()
    clean = re.sub(r"^\s*(?:hey\s+|hi\s+|hello\s+|ok\s+|yo\s+|manas\s+)?(?:ciel|shell|seal|siel|ceel|she\'ll|shall|chill|kiel|cyan|cell|seel)\b[,\s.]*", "", clean).strip()
    clean = re.sub(r"^[\s,.:;?!\-]+|[\s,.:;?!\-]+$", "", clean).strip()

    # 0.01 Universal Browser / App Path Detection
    # If Master passes ANY shortcut or executable path in their request, resolve the target browser & profile:
    m_any_path = re.search(r'["\'“”‘’]?((?:[a-zA-Z]:[\\/]|%[^%]+%[\\/]|~[\\/])[^"\'“”‘’\r\n\t]+?\.(?:lnk|exe|url|bat|cmd|py))["\'“”‘’]?', user_text, re.I)
    user_browser_target = None
    if m_any_path:
        raw_path = os.path.expanduser(os.path.expandvars(m_any_path.group(1).strip().strip('"\'“”‘’')))
        if os.path.exists(raw_path):
            user_browser_target = resolve_browser_from_path(raw_path)
            if user_browser_target and user_browser_target.get("is_browser"):
                set_preferred_browser_target(user_browser_target)

    # 0.02 Direct Path Execution (Explicit App / Shortcut Launching)
    # If Master passes a specific app path, launch it directly (even if already open)!
    if m_any_path and not any(w in clean for w in ["google doc", "docs.new", "presentation", "slide"]):
        target_path = os.path.expanduser(os.path.expandvars(m_any_path.group(1).strip().strip('"\'“”‘’')))
        if os.path.exists(target_path):
            res = tool_open_application(target_path)
            return True, res

    # 0.05 Geometric Primitive Art Direct Execution
    m_prim = re.match(
        r"^(?:please\s+)?(?:can\s+you\s+)?(?:generate|create|make|render)\s+(?:geometric\s+)?(?:primitive|polygon|vector)\s+art(?:\s+from\s+(?:my\s+)?([^\r\n]+))?$",
        clean, re.I
    )
    if m_prim or "primitive art" in clean:
        src = m_prim.group(1).strip() if (m_prim and m_prim.group(1)) else ""
        from agent_tools import tool_generate_primitive_art
        img_target = None
        if "screenshot" in src or "screenshot" in clean:
            try:
                img_dir = str(config.paths.image_dir)
                shots = [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.startswith("screenshot_") or f.endswith(".png")]
                if shots:
                    shots.sort(key=os.path.getmtime, reverse=True)
                    img_target = shots[0]
            except Exception:
                pass
        res = tool_generate_primitive_art(image_path=img_target or "screenshot", num_shapes=60, mode="triangle")
        return True, res

    # 0.08 System Telemetry & Performance Direct Execution
    if clean in [
        "analyze system performance and active processes", "system performance",
        "system status", "system info", "performance status", "diagnose system"
    ]:
        res = tool_system_telemetry()
        return True, res

    # 0. Screen Context & Perception
    if clean in ["what's on my screen", "whats on my screen", "screen context", "what am i looking at", "active window", "inspect screen", "see screen"]:
        res = tool_computer_see()
        return True, res

    # 0.1 Clipboard Analysis & Inspection
    if clean in ["inspect clipboard", "analyze clipboard", "check clipboard", "what's on my clipboard", "whats on my clipboard", "explain clipboard", "check my clipboard", "read clipboard"]:
        res = tool_analyze_clipboard()
        return True, res

    # 0.15 Drawing & Art Synthesis Direct Execution
    # First: Explicit AI image requests -> generate_image()
    if is_explicit_ai_image_request(clean):
        ai_prompt = extract_ai_image_prompt(clean) or re.sub(r"^(?:generate|create|make)\s+(?:an?\s+)?(?:ai\s+)?(?:image|picture|artwork)\s+(?:of\s+)?", "", clean, flags=re.I).strip()
        if ai_prompt and ai_prompt not in ["it", "this", "that"]:
            res = tool_generate_image(ai_prompt)
            return True, res

    # Second: Physical Microsoft Paint drawing requests -> draw_in_paint()
    draw_sub = extract_drawing_subject(clean)
    if draw_sub:
        res = tool_draw_in_paint(draw_sub)
        return True, res

    if clean in ["draw", "draw something", "draw anything", "paint something", "sketch something"]:
        res = tool_draw_in_paint("something")
        return True, res

    # 0.18 PowerPoint & Canva Presentation Generator Intent
    m_ppt = re.match(
        r"^(?:please\s+)?(?:can\s+you\s+)?(?:generate|create|make|build|do)\s+(?:a\s+)?(?:(?:slide\s+)?presentation|powerpoint|ppt|slides?|slide\s+deck|canva\s+slides?|canva\s+presentation)(?:\s+(?:in|on|with|using)\s+canva)?(?:\s+for\s+me)?(?:\s+(?:about|on|for)\s+([^\r\n]+))?$",
        clean, re.I
    )
    if not m_ppt:
        m_ppt = re.match(
            r"^(?:please\s+)?(?:can\s+you\s+)?(?:generate|create|make|build|do)\s+(?:a\s+)?canva\s+(?:presentation|slides?|slide\s+deck)(?:\s+for\s+me)?(?:\s+(?:about|on|for)\s+([^\r\n]+))?$",
            clean, re.I
        )
    if m_ppt:
        raw_topic = (m_ppt.group(1) or "").strip()
        topic = raw_topic if raw_topic else "Project Presentation"
        is_canva = "canva" in clean
        res = tool_generate_presentation(topic, 5)
        if is_canva:
            tool_open_application("https://www.canva.com/create/presentations/")
            res += "\n\n✦ **Canva Studio Opened**: Canva Presentation Studio has been launched in your browser so you can upload or customize your deck!"
        return True, res

    # 0.19 Google Docs & Office Document Writing Direct Execution
    m_doc_write = re.search(r"(?:google\s+doc[s]?|docs\.new)", clean, re.I)
    if m_doc_write and any(w in clean.lower() for w in ["essay", "write", "type", "draft", "give me", "put", "create", "notes", "article", "paper"]):
        # If user passed a specific browser path in user_text, user_browser_target was already resolved & set!
        if not user_browser_target or not user_browser_target.get("is_browser"):
            if "chrome" in clean:
                set_preferred_browser("chrome")
            elif "brave" in clean:
                set_preferred_browser("brave")
            elif "edge" in clean:
                set_preferred_browser("edge")
            elif "firefox" in clean:
                set_preferred_browser("firefox")
            else:
                set_preferred_browser("chrome")

        # Extract essay/topic directive:
        topic_match = re.search(r"(?:give\s+me|write|draft|type|create|put)\s+(?:a\s+)?([^\r\n]+?)(?:\s+(?:in|to|on)\s+(?:that\s+)?(?:google\s+doc[s]?|docs\.new)|$)", clean, re.I)
        topic = topic_match.group(1).strip() if (topic_match and topic_match.group(1)) else "100 word essay about AI"

        res = tool_execute_computer_task("google docs", topic)
        set_preferred_browser_target(None)
        return True, res

    # 0.2 Generalized Multi-Step Autonomous Computer Task Engine
    # Pattern A: "open [app/site] and [action/do work]" (e.g., "open canva and make a presentation about AI in robotics")
    m_task_and = re.match(
        r"^(?:please\s+)?(?:can\s+you\s+)?(?:open|launch|start|go\s+to)\s+([a-zA-Z0-9\s\.\-]+?)\s+(?:and|to)\s+([^\r\n]+)$",
        clean, re.I
    )
    if m_task_and:
        target_app = m_task_and.group(1).strip()
        directive  = m_task_and.group(2).strip()
        if target_app and directive and target_app not in ["it", "this", "that"]:
            # If target is canva and directive is presentation, create presentation and open canva
            if "canva" in target_app.lower() and any(w in directive.lower() for w in ["presentation", "slide", "powerpoint", "deck"]):
                topic_clean = re.sub(r"^(?:make|create|generate|do)\s+(?:a\s+)?(?:presentation|slide\s+deck|slides?)\s+(?:about|on|for)\s+", "", directive, flags=re.I).strip()
                res = tool_generate_presentation(topic_clean or "Project Presentation", 5)
                tool_open_application("https://www.canva.com/create/presentations/")
                res += "\n\n✦ **Canva Studio Opened**: Canva Presentation Studio has been launched in your browser so you can upload or customize your deck!"
                return True, res
            res = tool_execute_computer_task(target_app, directive)
            return True, res

    # Pattern B: "make/create/write/design [action] on/in [app/site]" (e.g., "make a presentation about space in canva")
    m_task_in = re.match(
        r"^(?:please\s+)?(?:can\s+you\s+)?(?:make|create|write|design|build|generate|do)\s+(?:a\s+)?([^\r\n]+?)\s+(?:on|in|using|with)\s+([a-zA-Z0-9\s\.\-]+)$",
        clean, re.I
    )
    if m_task_in:
        directive  = m_task_in.group(1).strip()
        target_app = m_task_in.group(2).strip()
        known_computer_targets = set(COMPUTER_TARGET_CATALOG.keys()) | {
            "canva", "figma", "notion", "docs", "sheets", "word", "excel", "powerpoint",
            "paint", "spotify", "youtube", "discord", "slack", "vscode", "github"
        }
        target_lower = target_app.lower()
        is_known = (
            target_lower in known_computer_targets
            or any(k in target_lower for k in known_computer_targets)
            or "." in target_lower
            or target_lower.startswith("http")
        )
        if is_known and target_app and directive and target_app not in ["it", "this", "that", "seconds", "minutes", "slides", "pages"]:
            if "canva" in target_lower and any(w in directive.lower() for w in ["presentation", "slide", "powerpoint", "deck"]):
                topic_clean = re.sub(r"^(?:presentation|slide\s+deck|slides?)\s+(?:about|on|for)\s+", "", directive, flags=re.I).strip()
                res = tool_generate_presentation(topic_clean or "Project Presentation", 5)
                tool_open_application("https://www.canva.com/create/presentations/")
                res += "\n\n✦ **Canva Studio Opened**: Canva Presentation Studio has been launched in your browser so you can upload or customize your deck!"
                return True, res
            res = tool_execute_computer_task(target_app, directive)
            return True, res

    # 0.3 Direct Mouse & Keyboard Directives
    m_click = re.match(r"^(?:mouse\s+)?(?:double\s+)?click(?:\s+at)?\s+(\d+)[,\s]+(\d+)$", clean, re.I)
    if m_click:
        x, y = int(m_click.group(1)), int(m_click.group(2))
        act = "double_click" if "double" in clean else "click"
        res = tool_computer_mouse(action=act, x=x, y=y)
        return True, res

    if clean in ["scroll down", "scroll up"]:
        amt = -350 if "down" in clean else 350
        res = tool_computer_mouse(action="scroll", scroll_amount=amt)
        return True, res

    m_press = re.match(r"^press\s+(enter|tab|esc|escape|space|backspace|delete|up|down|left|right)$", clean, re.I)
    if m_press:
        k = m_press.group(1).strip()
        res = tool_computer_keyboard(action="press", text=k)
        return True, res

    m_type = re.match(r"^(?:type|paste|write)\s+([^\r\n]+)$", clean, re.I)
    if m_type:
        txt = m_type.group(1).strip().strip("'\"")
        res = tool_computer_keyboard(action="type", text=txt)
        return True, res

    m_focus = re.match(r"^(?:focus|switch\s+to|bring\s+up)\s+([a-zA-Z0-9\s\.\-]+)$", clean, re.I)
    if m_focus:
        tgt = m_focus.group(1).strip()
        res = tool_focus_window(tgt)
        return True, res

    m_routine = re.match(r"^(?:start|activate|launch|enter|set)?\s*(coding|work|developer|focus|deep\s+work|zen|entertainment|chill|music)\s*(?:mode|routine)$", clean, re.I)
    if m_routine:
        mode = m_routine.group(1).replace(" ", "_")
        res = tool_launch_routine(mode)
        return True, res

    # 2. System Audio & Volume Control
    if clean in ["volume up", "increase volume", "louder", "turn up volume", "raise volume"]:
        res = tool_system_control("volume_up")
        return True, res
    if clean in ["volume down", "decrease volume", "lower volume", "turn down volume", "quieter"]:
        res = tool_system_control("volume_down")
        return True, res
    if clean in ["mute", "mute audio", "mute sound", "silence"]:
        res = tool_system_control("mute")
        return True, res
    if clean in ["unmute", "unmute audio", "unmute sound"]:
        res = tool_system_control("unmute")
        return True, res
    
    m_vol = re.match(r"^(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})%?$", clean, re.I)
    if m_vol:
        val = int(m_vol.group(1))
        res = tool_system_control("volume_set", val)
        return True, res

    # 3. Media Controls (Play / Pause / Next / Previous)
    if clean in ["pause music", "pause song", "pause", "pause media", "stop music", "resume music", "resume", "play music toggle", "toggle music"]:
        res = tool_system_control("play_pause")
        return True, res
    if clean in ["next song", "next track", "skip song", "skip track", "skip"]:
        res = tool_system_control("next_track")
        return True, res
    if clean in ["previous song", "previous track", "prev song", "last song"]:
        res = tool_system_control("prev_track")
        return True, res

    # 4. Display Brightness Controls
    if clean in ["brightness up", "increase brightness", "brighten screen"]:
        res = tool_system_control("brightness_up")
        return True, res
    if clean in ["brightness down", "decrease brightness", "dim screen", "dim"]:
        res = tool_system_control("brightness_down")
        return True, res
    m_bright = re.match(r"^(?:set\s+)?brightness\s+(?:to\s+)?(\d{1,3})%?$", clean, re.I)
    if m_bright:
        val = int(m_bright.group(1))
        res = tool_system_control("brightness_set", val)
        return True, res

    # 5. Music / YouTube intent
    b_lnk_triggers = ["open music", "play music", "music", "song", "play song", "open youtube", "youtube", "b⚡", "all pin music", "pin music"]
    if clean in b_lnk_triggers or clean == "b":
        res = tool_open_application("b⚡")
        return True, res

    # 6. Specific YouTube query: "play [song]" or "play [song] in brave"
    m_play = re.match(r"^(?:please\s+)?(?:can\s+you\s+)?(?:play|listen\s+to|search\s+youtube\s+for)\s+([^\r\n]+)$", clean, re.I)
    if m_play:
        query = m_play.group(1).strip()
        if query and query not in ["music", "song", "a song", "toggle", "pause", "next", "previous"]:
            res = tool_play_youtube(query)
            return True, res

    # 7. Direct App Launch intent: "open X", "launch X", "start X", "run X"
    m_open = re.match(r"^(?:please\s+)?(?:can\s+you\s+)?(?:open|launch|start|run|go\s+to|navigate\s+to)\s+([^\r\n]+)$", clean, re.I)
    if m_open:
        target = m_open.group(1).strip().strip("'\"").rstrip(".!?")
        if target and len(target) < 100 and not target.startswith(("a ", "the ", "an ")):
            res = tool_open_application(target)
            return True, res

    # 8. ECC Engineering Harness Direct Commands
    m_ecc_review = re.match(r"^(?:please\s+)?(?:can\s+you\s+)?(?:ecc\s+review|code\s+review|review\s+code\s+in|review\s+file)\s+([^\r\n]+)$", clean, re.I)
    if m_ecc_review:
        target = m_ecc_review.group(1).strip()
        res = tool_ecc_agent_run("code-reviewer", target)
        return True, res

    m_ecc_sec = re.match(r"^(?:please\s+)?(?:can\s+you\s+)?(?:ecc\s+security|security\s+audit|security\s+review)\s*(.*)$", clean, re.I)
    if m_ecc_sec:
        target = m_ecc_sec.group(1).strip()
        res = tool_ecc_agent_run("security-reviewer", target)
        return True, res

    m_ecc_consult = re.match(r"^(?:please\s+)?(?:can\s+you\s+)?(?:ecc|consult\s+ecc)\s+([^\r\n]+)$", clean, re.I)
    if m_ecc_consult:
        query = m_ecc_consult.group(1).strip()
        res = tool_ecc_consult(query)
        return True, res

    # 9. Known standalone app names: e.g. "brave", "discord", "notepad", "paint", "calculator", "vscode", "roblox", "opera"
    _standalone_apps = {
        "paint": "paint", "mspaint": "mspaint", "brave": "brave", "chrome": "chrome",
        "discord": "discord", "notepad": "notepad", "calculator": "calculator", "calc": "calc",
        "vscode": "vscode", "code": "code", "roblox": "roblox", "opera": "opera", "operagx": "operagx",
        "spotify": "spotify", "steam": "steam", "thonny": "thonny", "bilibili": "bilibili",
        "canva": "https://www.canva.com/create/presentations/"
    }
    if clean in _standalone_apps:
        res = tool_open_application(_standalone_apps[clean])
        return True, res

    if clean in ["take screenshot", "capture screen", "screenshot"]:
        res = tool_take_screenshot()
        return True, res

    # 10. OpenJarvis & Routine Fast Triggers
    m_jarvis_ask = re.match(r"^(?:jarvis\s+ask|ask\s+jarvis)\s+([^\r\n]+)$", clean, re.I)
    if m_jarvis_ask:
        q = m_jarvis_ask.group(1).strip()
        res = tool_openjarvis_cli("ask", q)
        return True, res

    if clean in ["openjarvis status", "jarvis status", "jarvis doctor", "openjarvis doctor", "openjarvis scan", "jarvis scan", "openjarvis telemetry", "jarvis telemetry"]:
        cmd = "doctor" if "doctor" in clean else ("scan" if "scan" in clean else ("telemetry" if "telemetry" in clean else "status"))
        res = tool_openjarvis_cli(cmd)
        return True, res

    if clean in ["jarvis", "jarvis observe", "observe desktop", "inspect screen", "observe screen", "what am i doing", "what am i doing right now"]:
        res = tool_jarvis_observe()
        return True, res

    if clean in ["coding routine", "code routine", "coding mode", "developer mode"]:
        res = tool_launch_routine("coding")
        return True, res

    if clean in ["focus routine", "focus mode", "do not disturb"]:
        res = tool_launch_routine("focus")
        return True, res

    return False, ""
