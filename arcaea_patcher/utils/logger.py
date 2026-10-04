import os
import sys
from typing import Dict


def _enable_windows_ansi() -> bool:
    """Enables ANSI escape sequence processing on Windows consoles."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if h_out == -1 or h_out == 0:
            return False
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(kernel32.SetConsoleMode(h_out, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False


class Logger:
    """Terminal logger with ANSI color formatting."""

    _COLORS: Dict[str, str] = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "cyan": "\033[36m",
        "magenta": "\033[35m",
    }

    def __init__(self, enabled: bool = True):
        self._enabled = enabled and self._supports_color()

    def _supports_color(self) -> bool:
        if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
            return False
        if sys.platform == "win32":
            return _enable_windows_ansi() or "WT_SESSION" in os.environ
        return True

    def _colorize(self, color_name: str, text: str) -> str:
        if self._enabled and color_name in self._COLORS:
            return f"{self._COLORS[color_name]}{text}{self._COLORS['reset']}"
        return text

    def info(self, msg: str) -> None:
        print(f"  {self._colorize('cyan', '[INFO]')} {msg}")

    def success(self, msg: str) -> None:
        print(f"  {self._colorize('green', '[OK]  ')} {msg}")

    def warn(self, msg: str) -> None:
        print(f"  {self._colorize('yellow', '[WARN]')} {msg}")

    def error(self, msg: str) -> None:
        print(f"  {self._colorize('red', '[FAIL]')} {msg}")

    def detail(self, msg: str) -> None:
        print(f"  {self._colorize('dim', '  .. ')} {msg}")

    def header(self, title: str) -> None:
        print(f"\n{self._colorize('bold', self._colorize('magenta', title))}")


logger = Logger()