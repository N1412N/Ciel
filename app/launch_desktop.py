"""
launch_desktop.py — Launch Ciel AI as an always-active native Windows desktop assistant.
Supports system tray persistence, global summon hotkeys, and hands-free voice engine.
"""

import threading
import time
import webview
import requests as req
import subprocess
import os
import sys
import ctypes
import ctypes.wintypes

# ── Force Windows to treat this as an independent app (NOT Python) ──
try:
    myappid = 'tensura.manas.ciel.studio.v1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception as e:
    pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CIEL_ROOT = os.path.dirname(APP_DIR)
os.environ["OLLAMA_MODELS"] = os.path.join(CIEL_ROOT, "models", "ollama")
os.environ["HF_HOME"] = os.path.join(CIEL_ROOT, "models", "huggingface")

FLASK_PORT = 5000
FLASK_URL = f"http://127.0.0.1:{FLASK_PORT}"
ICON_PATH = os.path.join(APP_DIR, "ciel.ico")

def start_flask():
    """Start the Flask server in a background thread."""
    from app import app
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)

def wait_for_flask(timeout=30):
    """Wait until Flask is ready to serve requests."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            req.get(FLASK_URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False

def start_ollama():
    """Ensure Ollama is running in the background."""
    ollama_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "Ollama", "ollama.exe"
    )
    if os.path.exists(ollama_path):
        try:
            req.get("http://127.0.0.1:11434", timeout=1)
        except Exception:
            subprocess.Popen(
                [ollama_path, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            time.sleep(2)

# ── 64-bit Safe Win32 ctypes signatures ──
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

user32.LoadImageW.restype = ctypes.wintypes.HANDLE
user32.LoadImageW.argtypes = [
    ctypes.wintypes.HINSTANCE,
    ctypes.c_wchar_p,
    ctypes.wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.wintypes.UINT
]

user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM
]

user32.GetAncestor.restype = ctypes.wintypes.HWND
user32.GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]

def attach_window_icon():
    """Find the Ciel window and apply the custom icon to titlebar & taskbar."""
    if not os.path.exists(ICON_PATH):
        return

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1
    GA_ROOT = 2

    try:
        hicon_big = user32.LoadImageW(0, ICON_PATH, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        hicon_small = user32.LoadImageW(0, ICON_PATH, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)

        def enum_windows_callback(hwnd, lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                if "Ciel" in buff.value:
                    root_hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
                    if hicon_small:
                        user32.SendMessageW(root_hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                    if hicon_big:
                        user32.SendMessageW(root_hwnd, WM_SETICON, ICON_BIG, hicon_big)
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
            return True

        cb = WNDENUMPROC(enum_windows_callback)

        for _ in range(30):
            time.sleep(0.3)
            user32.EnumWindows(cb, 0)
    except Exception as e:
        pass

# ── Global Application Handles ──
window = None
tray_icon = None
force_exit = False
SW_HIDE = 0
SW_NORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOW = 5
SW_RESTORE = 9

user32.IsIconic.restype = ctypes.wintypes.BOOL
user32.IsIconic.argtypes = [ctypes.wintypes.HWND]

user32.IsZoomed.restype = ctypes.wintypes.BOOL
user32.IsZoomed.argtypes = [ctypes.wintypes.HWND]
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def is_startup_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "Ciel")
            return bool(val)
    except Exception:
        return False

def set_startup_enabled(enable: bool):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
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
        return True
    except Exception as e:
        print("[Startup] Error setting registry:", e)
        return False

def get_ciel_hwnd():
    ciel_hwnd = [None]
    def enum_cb(hwnd, _):
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            text = buff.value.strip()
            if text == "Ciel" or text.startswith("Ciel ·") or "Ciel" in text:
                root = ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd
                ciel_hwnd[0] = root
                return False
        return True
    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)
    return ciel_hwnd[0]

def is_window_visible(hwnd=None):
    if hwnd is None:
        hwnd = get_ciel_hwnd()
    if not hwnd:
        return False
    return bool(ctypes.windll.user32.IsWindowVisible(hwnd))

def show_ciel_window():
    global window
    if window:
        try:
            window.show()
        except Exception:
            pass
    hwnd = get_ciel_hwnd()
    if hwnd:
        try:
            is_minimized = bool(user32.IsIconic(hwnd))
            is_maximized = bool(user32.IsZoomed(hwnd))
            if is_minimized:
                # Restore minimized window preserving maximized state
                if is_maximized:
                    user32.ShowWindow(hwnd, SW_MAXIMIZE)
                else:
                    user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                # Window already open (maximized or normal) — keep exact dimensions!
                user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
    attach_window_icon()

def hide_ciel_window():
    global window
    hwnd = get_ciel_hwnd()
    if hwnd:
        user32.ShowWindow(hwnd, SW_HIDE)
    elif window:
        try:
            window.hide()
        except Exception:
            pass

def toggle_ciel_window():
    hwnd = get_ciel_hwnd()
    if hwnd and is_window_visible(hwnd) and not user32.IsIconic(hwnd):
        hide_ciel_window()
    else:
        show_ciel_window()

def on_window_closing():
    global force_exit
    if force_exit:
        return True
    # Always Active: hide window to system tray instead of destroying
    hide_ciel_window()
    return False

def launch_companion():
    try:
        req.post(f"{FLASK_URL}/api/system/launch_companion", timeout=2)
    except Exception:
        pass

def is_wake_active():
    try:
        r = req.get(f"{FLASK_URL}/api/voice/wake_status", timeout=3)
        return bool(r.json().get("wake_active", False))
    except Exception:
        return False

def toggle_wake(icon=None, item=None):
    try:
        curr = is_wake_active()
        req.post(f"{FLASK_URL}/api/voice/wake_toggle", json={"enable": not curr}, timeout=3)
    except Exception:
        pass

def toggle_startup(icon=None, item=None):
    curr = is_startup_enabled()
    set_startup_enabled(not curr)

def create_tray_icon():
    global tray_icon
    if not os.path.exists(ICON_PATH):
        return
    try:
        from PIL import Image
        import pystray
        from pystray import MenuItem as item

        img = Image.open(ICON_PATH)
        tray_menu = pystray.Menu(
            item("Show Ciel Studio", lambda icon, item: show_ciel_window(), default=True),
            item("Hide to Tray", lambda icon, item: hide_ciel_window()),
            item("Floating Companion HUD", lambda icon, item: launch_companion()),
            pystray.Menu.SEPARATOR,
            item("Wake Word (\"Hey Ciel\")", toggle_wake, checked=lambda item: is_wake_active()),
            item("Start with Windows", toggle_startup, checked=lambda item: is_startup_enabled()),
            pystray.Menu.SEPARATOR,
            item("Exit Ciel", lambda icon, item: full_clean_shutdown())
        )
        tray_icon = pystray.Icon("ciel_tray", img, "Ciel AI (Always Active)", tray_menu)
        tray_icon.run()
    except Exception as e:
        print("[Tray] Error starting tray icon:", e)

def setup_global_hotkeys():
    """Register Ctrl+Shift+Space and Ctrl+Alt+Space to toggle Ciel from anywhere."""
    try:
        import keyboard
        keyboard.add_hotkey("ctrl+shift+space", toggle_ciel_window)
        keyboard.add_hotkey("ctrl+alt+space", toggle_ciel_window)
    except Exception as e:
        print("[Hotkeys] Error registering global hotkeys:", e)

def full_clean_shutdown(icon=None, item=None):
    """Purge AI models from VRAM/RAM, stop all background threads, and exit."""
    global force_exit, tray_icon
    force_exit = True
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass

    try:
        # 1. Unload all models from Ollama to free VRAM/RAM
        r = req.get("http://127.0.0.1:11434/api/ps", timeout=2)
        if r.status_code == 200:
            for m in r.json().get("models", []):
                name = m.get("name")
                if name:
                    req.post("http://127.0.0.1:11434/api/generate", json={"model": name, "keep_alive": 0}, timeout=2)
    except Exception:
        pass

    # 2. Stop wake word audio listener
    try:
        req.post(f"{FLASK_URL}/api/voice/wake_toggle", json={"enable": False}, timeout=1)
    except Exception:
        pass

    if window:
        try:
            window.destroy()
        except Exception:
            pass

    # 3. Clean exit
    time.sleep(0.3)
    os._exit(0)


if __name__ == "__main__":
    is_companion = "--companion" in sys.argv or "--overlay" in sys.argv or "--hud" in sys.argv
    start_hidden = "--tray" in sys.argv or "--minimized" in sys.argv

    # Single-instance guard: if Ciel is already running, summon it and exit immediately
    if not is_companion:
        try:
            r = req.get(f"{FLASK_URL}/api/sysinfo", timeout=0.8)
            if r.status_code == 200:
                try:
                    req.post(f"{FLASK_URL}/api/system/summon", timeout=1)
                except Exception:
                    pass
                os._exit(0)
        except Exception:
            pass

    # Start Ollama backend
    start_ollama()

    # Start Flask in a daemon thread
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    if not wait_for_flask():
        sys.exit(1)

    # Register summon callback with Flask
    try:
        from app import register_summon_callback
        register_summon_callback(show_ciel_window)
    except Exception:
        pass

    # Start background icon attacher thread
    icon_thread = threading.Thread(target=attach_window_icon, daemon=True)
    icon_thread.start()

    # Start global summon hotkey listener (Ctrl+Shift+Space & Ctrl+Alt+Space)
    hotkey_thread = threading.Thread(target=setup_global_hotkeys, daemon=True)
    hotkey_thread.start()

    # Start system tray icon thread (Always Active)
    if not is_companion:
        tray_thread = threading.Thread(target=create_tray_icon, daemon=True)
        tray_thread.start()

    if is_companion:
        # Determine screen metrics for bottom-right taskbar companion placement
        comp_w = 440
        comp_h = 740
        try:
            user32 = ctypes.windll.user32
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
            pos_x = max(20, sw - comp_w - 24)
            pos_y = max(20, sh - comp_h - 64)
        except Exception:
            pos_x, pos_y = 800, 100

        window = webview.create_window(
            title="Ciel · Companion HUD",
            url=f"{FLASK_URL}?v={int(time.time())}&mode=companion",
            width=comp_w,
            height=comp_h,
            x=pos_x,
            y=pos_y,
            min_size=(380, 500),
            resizable=True,
            on_top=True,
        )
        window.events.closing += full_clean_shutdown
    else:
        # Open the desktop window (hidden if launched on Windows startup with --tray)
        window = webview.create_window(
            title="Ciel",
            url=f"{FLASK_URL}?v={int(time.time())}",
            maximized=not start_hidden,
            width=1280,
            height=800,
            min_size=(800, 600),
            resizable=True,
            hidden=start_hidden,
        )
        # Close-to-tray: keeps Ciel always active!
        window.events.closing += on_window_closing

    # Start the desktop GUI (blocks until window is explicitly exited)
    webview.start(debug=False)

    # Ensure clean exit after loop finishes
    full_clean_shutdown()
