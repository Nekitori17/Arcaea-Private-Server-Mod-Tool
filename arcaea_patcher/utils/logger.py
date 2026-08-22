import sys


class Logger:
    """ANSI color-enabled terminal logger."""

    _COLORS = {
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
        if sys.platform == "win32":
            return False
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

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