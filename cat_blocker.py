"""
🐱 Cat Keyboard Blocker v2.0
Блокирует клавиатуру, когда кошка лежит на ней.

Возможности:
  - Иконка-клавиатура в трее (зелёная / красная)
  - Горячая клавиша для вкл/выкл (настраиваемая, по умолчанию Ctrl+Shift+K)
  - Автозапуск с Windows
  - Настройки сохраняются в %APPDATA%\CatKeyboardBlocker\config.json

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
import tkinter as tk

from PIL import Image, ImageDraw
import pystray

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
DEFAULT_CONFIG = {"hotkey": dict(DEFAULT_HOTKEY), "autostart": False}


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
        self.on_toggle = None                       # external callback

        self._ctrl = False
        self._shift = False
        self._alt = False

        self._hk_ctrl = hotkey_cfg.get("ctrl", False)
        self._hk_shift = hotkey_cfg.get("shift", False)
        self._hk_alt = hotkey_cfg.get("alt", False)
        self._hk_vk = hotkey_cfg.get("vk", 0)

    # ── public ───────────────────────────────────────────────
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

    # ── internals ────────────────────────────────────────────
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

            # Track modifiers (always, even when blocking)
            if vk in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
                self._ctrl = is_down
            elif vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
                self._shift = is_down
            elif vk in (VK_MENU, VK_LMENU, VK_RMENU):
                self._alt = is_down

            # Hotkey detected → toggle
            if is_down and self._is_hotkey(vk):
                self.blocking = not self.blocking
                if self.on_toggle:
                    self.on_toggle(self.blocking)
                return LRESULT(1).value

            # Block everything while active
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
#  Tray icon — keyboard shape
# ══════════════════════════════════════════════════════════════

def _make_icon(blocked: bool) -> Image.Image:
    """64×64 keyboard icon: red when blocked, green when free."""
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if blocked:
        body = "#D63031"
        keys = "#C0392B"
        outline = "#A93226"
    else:
        body = "#00B894"
        keys = "#00A381"
        outline = "#019875"

    # Keyboard body
    bx, by, bw, bh = 4, 14, 56, 36
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=5,
                        fill=body, outline=outline, width=2)

    # Key rows:  row_y, num_keys, key_h
    rows = [
        (by + 4,  10, 6),    # top row
        (by + 12, 9,  6),    # middle row
        (by + 20, 7,  6),    # bottom row
    ]
    mx = bx + 4                       # left margin inside body
    total_w = bw - 8                   # usable width

    for ry, nk, kh in rows:
        gap = 1
        kw = (total_w - gap * (nk - 1)) / nk
        for i in range(nk):
            kx = mx + i * (kw + gap)
            d.rounded_rectangle([kx, ry, kx + kw, ry + kh],
                                radius=1, fill=keys)

    # Space bar
    sp_y = by + 28
    sp_h = 5
    sp_margin = 14
    d.rounded_rectangle([bx + sp_margin, sp_y,
                         bx + bw - sp_margin, sp_y + sp_h],
                        radius=2, fill=keys)

    # Status indicator — small circle top-right
    cx, cy, cr = S - 10, 8, 5
    ind_color = "#E74C3C" if blocked else "#2ECC71"
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr],
              fill=ind_color, outline="white", width=1)

    return img


# ══════════════════════════════════════════════════════════════
#  Hotkey settings dialog  (tkinter)
# ══════════════════════════════════════════════════════════════

def _show_hotkey_dialog(current_hk: dict, on_save):
    """Open a small window; user presses desired combo, clicks Save."""
    root = tk.Tk()
    root.title("Горячая клавиша — Cat Keyboard Blocker")
    root.geometry("380x200")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg="#2C3E50")

    # Centre on screen
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
        # Modifier state from tkinter event
        ctrl  = bool(event.state & 0x4)
        shift = bool(event.state & 0x1)
        alt   = bool(event.state & 0x20000) or bool(event.state & 0x8)

        vk = event.keycode
        # Ignore bare modifier press
        if vk in (16, 17, 18, 160, 161, 162, 163, 164, 165):
            parts = []
            if ctrl:  parts.append("Ctrl")
            if shift: parts.append("Shift")
            if alt:   parts.append("Alt")
            parts.append("...")
            display_var.set("+".join(parts))
            return "break"

        name = event.keysym
        if len(name) == 1:
            name = name.upper()

        captured["ctrl"]  = ctrl
        captured["shift"] = shift
        captured["alt"]   = alt
        captured["vk"]    = vk
        captured["name"]  = name

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

    def _update_tray(is_blocked):
        icon = icon_ref[0]
        if icon is None:
            return
        icon.icon = _make_icon(is_blocked)
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

    def cb_autostart(icon, _item):
        config["autostart"] = not config.get("autostart", False)
        _save_config(config)
        set_autostart(config["autostart"])

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

    # ── menu ─────────────────────────────────────────────────
    menu = pystray.Menu(
        pystray.MenuItem(txt_toggle, cb_toggle, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(txt_hotkey, cb_hotkey),
        pystray.MenuItem("🚀  Автозапуск с Windows", cb_autostart,
                         checked=chk_autostart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌  Выход", cb_exit),
    )

    # sync autostart on launch
    if config.get("autostart"):
        set_autostart(True)

    icon = pystray.Icon(
        name="cat_keyboard_blocker",
        icon=_make_icon(False),
        title="⌨️ Клавиатура свободна",
        menu=menu,
    )
    icon_ref[0] = icon
    icon.run()


if __name__ == "__main__":
    main()
