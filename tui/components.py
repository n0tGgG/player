"""UI Components for CinemaTUI."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, OptionList, Static, RichLog

from .styles import ASCII_ART


class TopBar(Horizontal):
    """Top navigation bar containing search and action buttons."""

    DEFAULT_CSS = """
    TopBar {
        column-span: 4;
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


class Sidebar(Vertical):
    """Sidebar containing sources and categories lists."""

    DEFAULT_CSS = """
    Sidebar {
        column-span: 1;
        row-span: 7;
        layout: vertical;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="sidebar")

    def compose(self) -> ComposeResult:
        import os
        from textual.widgets import DirectoryTree
        
        path = os.path.expanduser("~")
        library = DirectoryTree(path, id="sources-list")
        library.border_title = "Sources"
        library.add_class("list-box")
        yield library

        playlists = OptionList("Netflix", "Prime Video", "RaiPlay")
        playlists.border_title = "Streaming"
        playlists.id = "categories-list"
        playlists.add_class("list-box")
        yield playlists


class MainContent(VerticalScroll):
    """Main viewport displaying banner, search results, and status details."""

    DEFAULT_CSS = """
    MainContent {
        column-span: 3;
        row-span: 7;
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
        column-span: 4;
        row-span: 2;
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
