COLOR_CODES = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "end": "\033[0m",
}


def print_color(text: str, color: str = "red") -> None:
    print(COLOR_CODES[color] + text + COLOR_CODES["end"])


def pause_for_gui(message: str) -> None:
    input(f"\n{message}\nGUIでの操作が終わったら、このターミナルでEnterを押してください: ")

