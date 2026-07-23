"""UI Components for CinemaTUI."""

from pathlib import Path
import os

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DirectoryTree, Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from .styles import ASCII_ART


def discover_media_roots() -> list[str]:
    """Return mounted drives first, then home/root fallbacks."""
    if os.name == "nt":
        return _discover_windows_roots()
    return _discover_unix_roots()


def _discover_windows_roots() -> list[str]:
    import string

    roots: list[str] = []
    for letter in string.ascii_uppercase:
        path = f"{letter}:\\"
        if os.path.isdir(path):
            roots.append(path)
    return roots


def _discover_unix_roots() -> list[str]:
    roots = _discover_unix_mount_roots()
    roots.extend([str(Path.home()), "/"])
    return _dedupe_roots(roots)


def _discover_unix_mount_roots() -> list[str]:
    mount_bases = (Path("/mnt"), Path("/media"), Path("/run/media"))
    discovered: list[str] = []

    for base in mount_bases:
        if not base.exists():
            continue

        try:
            for candidate in base.rglob("*"):
                if candidate.is_dir() and candidate.is_mount():
                    discovered.append(str(candidate))
        except OSError:
            continue

    return sorted(discovered)


def _dedupe_roots(roots: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()

    for root in roots:
        normalized = os.path.normcase(os.path.normpath(root))
        if normalized not in seen:
            seen.add(normalized)
            unique.append(root)

    return unique


def _format_root_label(root: str) -> str:
    home_root = os.path.normcase(os.path.normpath(str(Path.home())))
    candidate = os.path.normcase(os.path.normpath(root))

    if candidate == home_root:
        return "Home"

    if root in {"/", "\\"}:
        return "Root /"

    if os.name == "nt" and len(root) == 3 and root[1:] == ":\\":
        return root[:2]

    label = Path(root).name
    return label or root.rstrip("\\/")


class TopBar(Horizontal):
    """Top navigation bar containing search and action buttons."""

    DEFAULT_CSS = """
    TopBar {
        column-span: 5;
        row-span: 1;
        layout: horizontal;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="top-bar")

    def compose(self) -> ComposeResult:
        search = Input(placeholder="Cerca film o URL...", id="search-box")
        search.border_title = "Search"
        yield search

        # Scan controls
        yield Button("Scan Fast", id="scan-fast", classes="small-panel")
        yield Button("Scan Full", id="scan-full", classes="small-panel")
        yield Button("Cancel Scan", id="cancel-scan", classes="small-panel")

        # Web services
        yield Button("Web", id="web", classes="small-panel")


class Sidebar(VerticalScroll):
    """Sidebar containing sources and categories lists."""

    DEFAULT_CSS = """
    Sidebar {
        column-span: 2;
        row-span: 8;
        layout: vertical;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="sidebar")
        self.drive_roots = discover_media_roots() or [str(Path.home())]
        self.current_drive = self.drive_roots[0]
        self.drive_selector = None
        self.source_tree = None
        self.categories_list = None

    def _build_drive_selector(self) -> OptionList:
        drive_options = [
            Option(_format_root_label(root), id=root)
            for root in self.drive_roots
        ]

        drive_selector = OptionList(*drive_options, id="drive-selector")
        drive_selector.border_title = "Drives"
        drive_selector.add_class("list-box")

        for index, option in enumerate(drive_selector.options):
            if str(getattr(option, "id", "")) == self.current_drive:
                drive_selector.highlighted = index
                break

        return drive_selector

    def _build_source_tree(self) -> DirectoryTree:
        source_tree = DirectoryTree(self.current_drive, id="sources-list")
        source_tree.border_title = f"Files — {_format_root_label(self.current_drive)}"
        source_tree.add_class("list-box")
        return source_tree

    def _build_categories_list(self) -> OptionList:
        categories_list = OptionList(
            Option("Netflix", id="netflix"),
            Option("Prime Video", id="prime"),
            Option("RaiPlay", id="raiplay"),
            id="categories-list",
        )
        categories_list.border_title = "Streaming"
        categories_list.add_class("list-box")
        return categories_list

    def compose(self) -> ComposeResult:
        if self.drive_selector is None:
            self.drive_selector = self._build_drive_selector()
        if self.source_tree is None:
            self.source_tree = self._build_source_tree()
        if self.categories_list is None:
            self.categories_list = self._build_categories_list()

        yield self.drive_selector
        yield self.source_tree
        yield self.categories_list

    def set_drive_root(self, root: str) -> None:
        normalized_root = str(root)
        self.current_drive = normalized_root
        source_tree = getattr(self, "source_tree", None)
        if source_tree is not None:
            source_tree.border_title = f"Files — {_format_root_label(normalized_root)}"
            if str(source_tree.path) != normalized_root:
                source_tree.path = normalized_root

        drive_selector = getattr(self, "drive_selector", None)
        if drive_selector is not None:
            for index, option in enumerate(drive_selector.options):
                if str(getattr(option, "id", "")) == normalized_root:
                    drive_selector.highlighted = index
                    break


class MainContent(VerticalScroll):
    """Main viewport displaying banner, search results, and status details."""

    DEFAULT_CSS = """
    MainContent {
        column-span: 3;
        row-span: 8;
        border: round #61afef;
        padding: 1 2;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="main-content")
        self.border_title = "Welcome!"

    def compose(self) -> ComposeResult:
        yield Static(ASCII_ART, classes="ascii-art")

        results = OptionList(id="results-list")
        results.border_title = "Results"
        results.add_class("list-box")
        yield results

        terminal_log = RichLog(id="terminal-output", highlight=True, markup=True)
        terminal_log.border_title = "Terminal Output"
        # Optional: Add border styles to terminal_log here or in CSS
        yield terminal_log

        yield Static(
            "Sistema pronto.\nMotore di riproduzione mpv caricato con successo.\n\nLog located in /tmp/cinema.log\n",
            classes="info-text",
        )
        yield Static(
            "Backend:\n- FileScanner: Scanning asincrono\n- MpvController: Playback IPC\n- WebKiosk: Kiosk mode\n- SystemControl: Audio control",
            classes="info-text",
            id="status-info",
        )


class PlayerBar(Vertical):
    """Bottom bar for player controls and status indicator."""

    DEFAULT_CSS = """
    PlayerBar {
        column-span: 5;
        row-span: 1;
        border: round #56b6c2;
        layout: vertical;
        content-align: center middle;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="player-bar")
        self.border_title = "Ready ( MP4 Locale | Nessun media in riproduzione )"

    def compose(self) -> ComposeResult:
        with Horizontal(id="controls"):
            yield Button("[Prev]", id="prev")
            yield Button("[Play/Pause]", id="play")
            yield Button("[Next]", id="next")
            yield Button("[Stop]", id="stop")
            yield Button("[Vol-]", id="voldown")
            yield Button("[Vol+]", id="volup")
            yield Button("[Poweroff]", id="poweroff")
            # Spinner area for loading animations
            yield Static("", id="spinner")


