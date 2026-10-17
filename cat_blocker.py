"""
🐱 Cat Keyboard Blocker v2.1
Блокирует клавиатуру, когда кошка лежит на ней.

Возможности:
  - Иконки в трее с выбором стиля (Клавиатура, Кошачья лапка, Мордочка кота, Замок, Кружок)
  - Горячая клавиша для вкл/выкл (настраиваемая, по умолчанию Ctrl+Shift+K)
  - Автозапуск с Windows
  - Автоматическая и ручная проверка обновлений с GitHub с предложением обновиться
  - Настройки сохраняются в %APPDATA%\\CatKeyboardBlocker\\config.json

Требуется запуск от имени администратора!
"""

import ctypes
import ctypes.wintypes
import threading
import sys
import os
import json
import winreg
import time
import subprocess
import tempfile
import urllib.request
import urllib.error
import re
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageDraw
import pystray

CURRENT_VERSION = "v2.1"
GITHUB_REPO = "skyi4k/keyboard-blocker"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# ══════════════════════════════════════════════════════════════
#  Windows API
# ══════════════════════════════════════════════════════════════
LRESULT = ctypes.c_ssize_t
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12          # Alt
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LMENU = 0xA4
VK_RMENU = 0xA5

MODIFIER_VKS = {
    VK_CONTROL, VK_SHIFT, VK_MENU,
    VK_LCONTROL, VK_RCONTROL,
    VK_LSHIFT, VK_RSHIFT,
    VK_LMENU, VK_RMENU,
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

HOOKPROC = ctypes.CFUNCTYPE(
    LRESULT, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
)

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, HOOKPROC, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = ctypes.c_void_p

user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p, ctypes.c_int,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
]
user32.CallNextHookEx.restype = LRESULT

user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL

user32.GetMessageW.argtypes = [
    ctypes.POINTER(ctypes.wintypes.MSG),
    ctypes.wintypes.HWND, ctypes.c_uint, ctypes.c_uint,
]
user32.GetMessageW.restype = ctypes.c_int

user32.PostThreadMessageW.argtypes = [
    ctypes.wintypes.DWORD, ctypes.c_uint,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
]
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]

kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD

# ══════════════════════════════════════════════════════════════
#  VK helpers
# ══════════════════════════════════════════════════════════════
VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Escape",
    0x20: "Space", 0x21: "PageUp", 0x22: "PageDown",
    0x23: "End", 0x24: "Home",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2D: "Insert", 0x2E: "Delete",
    0x6A: "Num*", 0x6B: "Num+", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/",
    0x70: "F1",  0x71: "F2",  0x72: "F3",  0x73: "F4",
    0x74: "F5",  0x75: "F6",  0x76: "F7",  0x77: "F8",
    0x78: "F9",  0x79: "F10", 0x7A: "F11", 0x7B: "F12",
    0x90: "NumLock", 0x91: "ScrollLock", 0x14: "CapsLock",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-",
    0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}


def vk_to_name(vk: int) -> str:
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num{vk - 0x60}"
    return VK_NAMES.get(vk, f"0x{vk:02X}")


# ══════════════════════════════════════════════════════════════
#  Config
# ══════════════════════════════════════════════════════════════
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", "."), "CatKeyboardBlocker")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_HOTKEY = {"ctrl": True, "shift": True, "alt": False, "vk": 0x4B, "name": "K"}
DEFAULT_CONFIG = {
    "hotkey": dict(DEFAULT_HOTKEY),
    "autostart": False,
    "icon_style": "keyboard",        # keyboard, paw, cat, lock, circle
    "auto_check_updates": True,
}


def _load_config() -> dict:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def _save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def hotkey_display(hk: dict) -> str:
    parts = []
    if hk.get("ctrl"):
        parts.append("Ctrl")
    if hk.get("shift"):
        parts.append("Shift")
    if hk.get("alt"):
        parts.append("Alt")
    parts.append(hk.get("name", vk_to_name(hk.get("vk", 0))))
    return "+".join(parts)


# ══════════════════════════════════════════════════════════════
#  Autostart (registry)
# ══════════════════════════════════════════════════════════════
_REG_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "CatKeyboardBlocker"


def _exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def set_autostart(enable: bool):
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_RUN, 0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        )
        if enable:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, f'"{_exe_path()}"')
        else:
            try:
                winreg.DeleteValue(key, _APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Autostart error: {e}")


# ══════════════════════════════════════════════════════════════
#  Keyboard Blocker (low-level hook)
# ══════════════════════════════════════════════════════════════

class KeyboardBlocker:
    def __init__(self, hotkey_cfg: dict):
        self.blocking = False
        self._hook_handle = None
        self._thread_id = None
        self._c_callback = HOOKPROC(self._ll_callback)
        self.on_toggle = None

        self._ctrl = False
        self._shift = False
        self._alt = False

        self._hk_ctrl = hotkey_cfg.get("ctrl", False)
        self._hk_shift = hotkey_cfg.get("shift", False)
        self._hk_alt = hotkey_cfg.get("alt", False)
        self._hk_vk = hotkey_cfg.get("vk", 0)

    def update_hotkey(self, hk: dict):
        self._hk_ctrl = hk.get("ctrl", False)
        self._hk_shift = hk.get("shift", False)
        self._hk_alt = hk.get("alt", False)
        self._hk_vk = hk.get("vk", 0)

    def toggle(self) -> bool:
        self.blocking = not self.blocking
        return self.blocking

    def start(self):
        t = threading.Thread(target=self._pump, daemon=True)
        t.start()
        time.sleep(0.3)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _is_hotkey(self, vk: int) -> bool:
        return (
            vk == self._hk_vk
            and self._ctrl == self._hk_ctrl
            and self._shift == self._hk_shift
            and self._alt == self._hk_alt
        )

    def _ll_callback(self, nCode, wParam, lParam):
        if nCode == HC_ACTION:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = kb.vkCode
            is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)

            if vk in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
                self._ctrl = is_down
            elif vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
                self._shift = is_down
            elif vk in (VK_MENU, VK_LMENU, VK_RMENU):
                self._alt = is_down

            if is_down and self._is_hotkey(vk):
                self.blocking = not self.blocking
                if self.on_toggle:
                    self.on_toggle(self.blocking)
                return LRESULT(1).value

            if self.blocking:
                return LRESULT(1).value

        return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

    def _pump(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._c_callback,
            kernel32.GetModuleHandleW(None), 0,
        )
        if not self._hook_handle:
            print("ERROR: SetWindowsHookExW failed. Run as Administrator!")
            return

        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_handle:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None


# ══════════════════════════════════════════════════════════════
#  Tray Icons (Multi-style)
# ══════════════════════════════════════════════════════════════

def _draw_keyboard_icon(d: ImageDraw.Draw, S: int, blocked: bool):
    body = "#D63031" if blocked else "#00B894"
    keys = "#C0392B" if blocked else "#00A381"
    outline = "#A93226" if blocked else "#019875"

    bx, by, bw, bh = 4, 14, 56, 36
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=5, fill=body, outline=outline, width=2)

    rows = [
        (by + 4, 10, 6),
        (by + 12, 9, 6),
        (by + 20, 7, 6),
    ]
    mx = bx + 4
    total_w = bw - 8

    for ry, nk, kh in rows:
        gap = 1
        kw = (total_w - gap * (nk - 1)) / nk
        for i in range(nk):
            kx = mx + i * (kw + gap)
            d.rounded_rectangle([kx, ry, kx + kw, ry + kh], radius=1, fill=keys)

    sp_y = by + 28
    sp_h = 5
    sp_margin = 14
    d.rounded_rectangle([bx + sp_margin, sp_y, bx + bw - sp_margin, sp_y + sp_h], radius=2, fill=keys)

    cx, cy, cr = S - 10, 8, 5
    ind_color = "#E74C3C" if blocked else "#2ECC71"
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=ind_color, outline="white", width=1)


def _draw_paw_icon(d: ImageDraw.Draw, S: int, blocked: bool):
    color = "#E74C3C" if blocked else "#2ECC71"
    outline = "#C0392B" if blocked else "#27AE60"

    # Main pad (center bottom)
    d.ellipse([16, 26, 48, 54], fill=color, outline=outline, width=2)

    # 4 toes
    toes = [
        (12, 16, 12, 16),
        (22, 8, 11, 15),
        (32, 8, 11, 15),
        (41, 16, 12, 16),
    ]
    for x, y, w, h in toes:
        d.ellipse([x, y, x + w, y + h], fill=color, outline=outline, width=2)

    # Status badge top right
    cx, cy, cr = S - 8, 8, 5
    ind_color = "#E74C3C" if blocked else "#2ECC71"
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=ind_color, outline="white", width=1)


def _draw_cat_icon(d: ImageDraw.Draw, S: int, blocked: bool):
    color = "#E74C3C" if blocked else "#2ECC71"
    outline = "#C0392B" if blocked else "#27AE60"
    eye_color = "white"

    # Ears
    d.polygon([(10, 26), (15, 6), (28, 22)], fill=color, outline=outline)
    d.polygon([(54, 26), (49, 6), (36, 22)], fill=color, outline=outline)

    # Head
    d.ellipse([10, 16, 54, 56], fill=color, outline=outline, width=2)

    # Eyes
    d.ellipse([20, 28, 28, 38], fill=eye_color)
    d.ellipse([36, 28, 44, 38], fill=eye_color)
    d.ellipse([23, 31, 26, 36], fill="#2C3E50")
    d.ellipse([39, 31, 42, 36], fill="#2C3E50")

    # Nose
    d.polygon([(30, 42), (34, 42), (32, 45)], fill="white")

    # Whiskers
    d.line([14, 42, 4, 40], fill="white", width=2)
    d.line([14, 46, 4, 48], fill="white", width=2)
    d.line([50, 42, 60, 40], fill="white", width=2)
    d.line([50, 46, 60, 48], fill="white", width=2)


def _draw_lock_icon(d: ImageDraw.Draw, S: int, blocked: bool):
    color = "#E74C3C" if blocked else "#2ECC71"
    outline = "#C0392B" if blocked else "#27AE60"

    # Shackle
    if blocked:
        # Closed lock
        d.arc([20, 10, 44, 36], start=180, end=0, fill=outline, width=5)
        d.line([20, 23, 20, 32], fill=outline, width=5)
        d.line([44, 23, 44, 32], fill=outline, width=5)
    else:
        # Open lock
        d.arc([20, 8, 44, 34], start=180, end=0, fill=outline, width=5)
        d.line([20, 21, 20, 32], fill=outline, width=5)
        d.line([44, 14, 44, 22], fill=outline, width=5)

    # Body
    d.rounded_rectangle([14, 28, 50, 56], radius=4, fill=color, outline=outline, width=2)

    # Keyhole
    d.ellipse([29, 36, 35, 42], fill="white")
    d.polygon([(30, 40), (34, 40), (33, 48), (31, 48)], fill="white")


def _draw_circle_icon(d: ImageDraw.Draw, S: int, blocked: bool):
    if blocked:
        d.ellipse([3, 3, S - 3, S - 3], fill="#E74C3C", outline="#C0392B", width=3)
        d.line([18, 18, S - 18, S - 18], fill="white", width=6)
        d.line([18, S - 18, S - 18, 18], fill="white", width=6)
    else:
        d.ellipse([3, 3, S - 3, S - 3], fill="#2ECC71", outline="#27AE60", width=3)
        d.line([16, S // 2, S // 2 - 2, S - 18], fill="white", width=6)
        d.line([S // 2 - 2, S - 18, S - 14, 18], fill="white", width=6)


def _make_icon(blocked: bool, style: str = "keyboard") -> Image.Image:
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if style == "paw":
        _draw_paw_icon(d, S, blocked)
    elif style == "cat":
        _draw_cat_icon(d, S, blocked)
    elif style == "lock":
        _draw_lock_icon(d, S, blocked)
    elif style == "circle":
        _draw_circle_icon(d, S, blocked)
    else:
        _draw_keyboard_icon(d, S, blocked)

    return img


# ══════════════════════════════════════════════════════════════
#  Updater System
# ══════════════════════════════════════════════════════════════

def _parse_version(v_str: str):
    nums = re.findall(r"\d+", v_str)
    return tuple(map(int, nums)) if nums else (0,)


def check_github_update():
    """Returns (has_update: bool, latest_version: str, download_url: str, body: str)"""
    try:
        req = urllib.request.Request(
            GITHUB_API_LATEST,
            headers={"User-Agent": f"CatKeyboardBlocker-{CURRENT_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                tag = data.get("tag_name", "")
                body = data.get("body", "")

                download_url = None
                for asset in data.get("assets", []):
                    name = asset.get("name", "")
                    if name.lower().endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                        break

                latest_tuple = _parse_version(tag)
                current_tuple = _parse_version(CURRENT_VERSION)

                has_update = latest_tuple > current_tuple and download_url is not None
                return has_update, tag, download_url, body
    except Exception as e:
        print(f"Update check error: {e}")
    return False, "", "", ""


def _apply_update(download_url: str, target_exe: str):
    """Downloads new exe and runs a self-replacing updater script."""
    temp_dir = tempfile.gettempdir()
    new_exe = os.path.join(temp_dir, f"update_{int(time.time())}.exe")

    # Download
    req = urllib.request.Request(download_url, headers={"User-Agent": "CatKeyboardBlocker"})
    with urllib.request.urlopen(req) as response, open(new_exe, "wb") as out_file:
        out_file.write(response.read())

    # Create batch script to replace and restart
    updater_bat = os.path.join(temp_dir, f"updater_{int(time.time())}.bat")
    bat_content = f"""@echo off
timeout /t 1 /nobreak >nul
:retry
move /y "{new_exe}" "{target_exe}" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto retry
)
start "" "{target_exe}"
del "%~f0"
"""
    with open(updater_bat, "w", encoding="cp866") as f:
        f.write(bat_content)

    # Launch updater and exit
    subprocess.Popen(["cmd.exe", "/c", updater_bat], creationflags=0x08000000)
    os._exit(0)


def show_update_dialog(tag: str, body: str, download_url: str):
    """Custom popup window asking user if they want to update."""
    root = tk.Tk()
    root.title("Доступно обновление — Cat Keyboard Blocker")
    root.geometry("450x280")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg="#2C3E50")

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 450) // 2
    y = (root.winfo_screenheight() - 280) // 2
    root.geometry(f"+{x}+{y}")

    tk.Label(
        root, text=f"🎉 Найдена новая версия: {tag}!",
        font=("Segoe UI", 13, "bold"), fg="#2ECC71", bg="#2C3E50",
    ).pack(pady=(16, 4))

    tk.Label(
        root, text=f"Текущая установленная версия: {CURRENT_VERSION}",
        font=("Segoe UI", 9), fg="#BDC3C7", bg="#2C3E50",
    ).pack()

    desc_frame = tk.Frame(root, bg="#34495E")
    desc_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    clean_body = body.strip() if body else "Улучшения стабильности и новые функции."
    text_box = tk.Text(
        desc_frame, bg="#34495E", fg="white", font=("Segoe UI", 9),
        wrap=tk.WORD, relief="flat", padx=8, pady=8, height=5,
    )
    text_box.insert("1.0", clean_body)
    text_box.configure(state="disabled")
    text_box.pack(fill=tk.BOTH, expand=True)

    status_lbl = tk.Label(root, text="", font=("Segoe UI", 9), fg="#F1C40F", bg="#2C3E50")
    status_lbl.pack()

    btn_frame = tk.Frame(root, bg="#2C3E50")
    btn_frame.pack(pady=(4, 14))

    def on_update():
        status_lbl.config(text="⏳ Загрузка обновления и перезапуск...")
        root.update()
        current_exe = _exe_path()
        if not getattr(sys, "frozen", False):
            # Not frozen exe -> open release page in browser
            import webbrowser
            webbrowser.open(download_url)
            root.destroy()
            return
        threading.Thread(target=_apply_update, args=(download_url, current_exe), daemon=True).start()

    tk.Button(
        btn_frame, text="⬇️ Обновить сейчас", command=on_update,
        width=18, font=("Segoe UI", 10, "bold"),
        bg="#27AE60", fg="white", relief="flat", cursor="hand2",
    ).pack(side=tk.LEFT, padx=8)

    tk.Button(
        btn_frame, text="Напомнить позже", command=root.destroy,
        width=16, font=("Segoe UI", 10),
        bg="#7F8C8D", fg="white", relief="flat", cursor="hand2",
    ).pack(side=tk.LEFT, padx=8)

    root.mainloop()


def perform_update_check(manual: bool = False):
    def _worker():
        has_update, tag, url, body = check_github_update()
        if has_update:
            show_update_dialog(tag, body, url)
        elif manual:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showinfo(
                "Обновления",
                f"У вас установлена самая актуальная версия ({CURRENT_VERSION})! 🎉",
            )
            root.destroy()

    threading.Thread(target=_worker, daemon=True).start()


# ══════════════════════════════════════════════════════════════
#  Hotkey settings dialog (tkinter)
# ══════════════════════════════════════════════════════════════

def _show_hotkey_dialog(current_hk: dict, on_save):
    root = tk.Tk()
    root.title("Горячая клавиша — Cat Keyboard Blocker")
    root.geometry("380x200")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg="#2C3E50")

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 380) // 2
    y = (root.winfo_screenheight() - 200) // 2
    root.geometry(f"+{x}+{y}")

    captured = dict(current_hk)
    display_var = tk.StringVar(value=hotkey_display(current_hk))

    tk.Label(root, text="Нажмите новую комбинацию:",
             font=("Segoe UI", 11), fg="white", bg="#2C3E50").pack(pady=(18, 4))

    lbl = tk.Label(root, textvariable=display_var,
                   font=("Segoe UI", 18, "bold"), fg="#F1C40F", bg="#2C3E50")
    lbl.pack(pady=6)

    tk.Label(root, text="(Ctrl / Shift / Alt  +  клавиша)",
             font=("Segoe UI", 9), fg="#95A5A6", bg="#2C3E50").pack()

    def on_key(event):
        ctrl = bool(event.state & 0x4)
        shift = bool(event.state & 0x1)
        alt = bool(event.state & 0x20000) or bool(event.state & 0x8)

        vk = event.keycode
        if vk in (16, 17, 18, 160, 161, 162, 163, 164, 165):
            parts = []
            if ctrl: parts.append("Ctrl")
            if shift: parts.append("Shift")
            if alt: parts.append("Alt")
            parts.append("...")
            display_var.set("+".join(parts))
            return "break"

        name = event.keysym
        if len(name) == 1:
            name = name.upper()

        captured["ctrl"] = ctrl
        captured["shift"] = shift
        captured["alt"] = alt
        captured["vk"] = vk
        captured["name"] = name

        display_var.set(hotkey_display(captured))
        return "break"

    root.bind("<KeyPress>", on_key)

    btn_frame = tk.Frame(root, bg="#2C3E50")
    btn_frame.pack(pady=14)

    def save():
        on_save(dict(captured))
        root.destroy()

    tk.Button(btn_frame, text="💾 Сохранить", command=save,
              width=14, font=("Segoe UI", 10),
              bg="#27AE60", fg="white", relief="flat").pack(side=tk.LEFT, padx=6)
    tk.Button(btn_frame, text="Отмена", command=root.destroy,
              width=14, font=("Segoe UI", 10),
              bg="#7F8C8D", fg="white", relief="flat").pack(side=tk.LEFT, padx=6)

    root.mainloop()


# ══════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════

def main():
    config = _load_config()
    blocker = KeyboardBlocker(config["hotkey"])

    icon_ref = [None]

    def _get_current_icon():
        return _make_icon(blocker.blocking, config.get("icon_style", "keyboard"))

    def _update_tray(is_blocked=None):
        icon = icon_ref[0]
        if icon is None:
            return
        if is_blocked is None:
            is_blocked = blocker.blocking
        icon.icon = _get_current_icon()
        icon.title = (
            "🐱 Клавиатура ЗАБЛОКИРОВАНА"
            if is_blocked
            else "⌨️ Клавиатура свободна"
        )

    blocker.on_toggle = _update_tray
    blocker.start()

    # ── tray callbacks ───────────────────────────────────────
    def cb_toggle(icon, _item=None):
        _update_tray(blocker.toggle())

    def cb_hotkey(icon, _item):
        def save_hk(hk):
            config["hotkey"] = hk
            _save_config(config)
            blocker.update_hotkey(hk)
        threading.Thread(
            target=_show_hotkey_dialog,
            args=(config["hotkey"], save_hk),
            daemon=True,
        ).start()

    def cb_set_style(style_key):
        def _handler(icon, _item):
            config["icon_style"] = style_key
            _save_config(config)
            _update_tray()
        return _handler

    def cb_autostart(icon, _item):
        config["autostart"] = not config.get("autostart", False)
        _save_config(config)
        set_autostart(config["autostart"])

    def cb_toggle_auto_update(icon, _item):
        config["auto_check_updates"] = not config.get("auto_check_updates", True)
        _save_config(config)

    def cb_manual_update(icon, _item):
        perform_update_check(manual=True)

    def cb_exit(icon, _item):
        blocker.stop()
        icon.stop()
        os._exit(0)

    # ── dynamic labels / checks ──────────────────────────────
    def txt_toggle(_):
        return "⛔  Разблокировать" if blocker.blocking else "🔒  Заблокировать"

    def txt_hotkey(_):
        return f"⌨️  Горячая клавиша: {hotkey_display(config['hotkey'])}"

    def chk_autostart(_):
        return config.get("autostart", False)

    def chk_auto_update(_):
        return config.get("auto_check_updates", True)

    def is_style_selected(style_key):
        return lambda _: config.get("icon_style", "keyboard") == style_key

    # ── submenus ─────────────────────────────────────────────
    style_menu = pystray.Menu(
        pystray.MenuItem("⌨️  Клавиатура", cb_set_style("keyboard"), checked=is_style_selected("keyboard")),
        pystray.MenuItem("🐾  Кошачья лапка", cb_set_style("paw"), checked=is_style_selected("paw")),
        pystray.MenuItem("🐱  Мордочка котика", cb_set_style("cat"), checked=is_style_selected("cat")),
        pystray.MenuItem("🔒  Замок", cb_set_style("lock"), checked=is_style_selected("lock")),
        pystray.MenuItem("⚪  Минималистичный кружок", cb_set_style("circle"), checked=is_style_selected("circle")),
    )

    update_menu = pystray.Menu(
        pystray.MenuItem("🔍  Проверить обновления сейчас", cb_manual_update),
        pystray.MenuItem("🔄  Проверять автоматически при запуске", cb_toggle_auto_update, checked=chk_auto_update),
    )

    menu = pystray.Menu(
        pystray.MenuItem(txt_toggle, cb_toggle, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(txt_hotkey, cb_hotkey),
        pystray.MenuItem("🎨  Стиль иконки", style_menu),
        pystray.MenuItem("🚀  Автозапуск с Windows", cb_autostart, checked=chk_autostart),
        pystray.MenuItem(f"ℹ️  Обновления ({CURRENT_VERSION})", update_menu),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌  Выход", cb_exit),
    )

    if config.get("autostart"):
        set_autostart(True)

    icon = pystray.Icon(
        name="cat_keyboard_blocker",
        icon=_get_current_icon(),
        title="⌨️ Клавиатура свободна",
        menu=menu,
    )
    icon_ref[0] = icon

    # Check for updates automatically in background if enabled
    if config.get("auto_check_updates", True):
        threading.Timer(2.0, perform_update_check, args=(False,)).start()

    icon.run()


if __name__ == "__main__":
    main()
