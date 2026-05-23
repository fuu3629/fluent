import os
import sys


COLOR_CODES = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "end": "\033[0m",
}

COLOR_LABELS = {
    "black": "INFO",
    "red": "STEP",
    "green": "DONE",
    "yellow": "WARN",
    "blue": "INFO",
}

PLAIN_PREFIXES = {
    "STEP": ">>>",
    "DONE": "<<<",
    "WARN": "!!!",
    "INFO": "---",
}


def _enable_windows_ansi() -> bool:
    if os.name != "nt":
        return True

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False

        enable_virtual_terminal_processing = 0x0004
        return bool(
            kernel32.SetConsoleMode(
                handle,
                mode.value | enable_virtual_terminal_processing,
            )
        )
    except Exception:
        return False


ANSI_COLOR_ENABLED = (
    sys.stdout.isatty()
    and os.environ.get("NO_COLOR") is None
    and _enable_windows_ansi()
)


def print_color(text: str, color: str = "red") -> None:
    if ANSI_COLOR_ENABLED and color in COLOR_CODES:
        print(COLOR_CODES[color] + text + COLOR_CODES["end"])
        return

    label = COLOR_LABELS.get(color, "INFO")
    prefix = PLAIN_PREFIXES[label]
    print(f"{prefix} [{label}] {text}")


def pause_for_gui(message: str) -> None:
    input(f"\n{message}\nGUIでの操作が終わったら、このターミナルでEnterを押してください: ")
