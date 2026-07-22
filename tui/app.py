"""Main CinemaTUI Application class."""

import asyncio
import logging
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Button, DirectoryTree, Input, OptionList, Static

from controllers import CinemaController, PlaybackState
from .components import MainContent, PlayerBar, Sidebar, TopBar
from .styles import APP_CSS
from textual.widgets import RichLog

logger = logging.getLogger(__name__)


class TextualLoggerHandler(logging.Handler):
    """Custom logging handler to route log records to Textual RichLog widget."""
    def __init__(self, app: App, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = app

    def emit(self, record):
        try:
            msg = self.format(record)
            self.app.call_from_thread(self.write_log, msg)
        except Exception:
            self.handleError(record)

    def write_log(self, msg):
        try:
            if getattr(self.app, "is_mounted", False):
                terminal = self.app.query_one("#terminal-output", RichLog)
                terminal.write(msg)
        except Exception:
            pass


class CinemaTUI(App):
    """Media Center TUI Application styled like Spotify/Spotatui."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "play_pause", "Play/Pause"),
        Binding("s", "stop", "Stop"),
        Binding("n", "next_vol", "Vol+"),
        Binding("m", "prev_vol", "Vol-"),
    ]

    CSS = APP_CSS

    def __init__(self) -> None:
        super().__init__()
        self.controller = CinemaController()
        self.current_files: List = []
        self.current_service: Optional[str] = None
        self._full_scan_confirm: bool = False
        self._spinner_running: bool = False
        self._spinner_task: Optional[asyncio.Task] = None
        self._selected_file: Optional[str] = None  # File queued for playback

        # Register event callbacks
        self.controller.on("playback_finish", self._on_playback_finish)
        self.controller.on("error", self._on_error)
        self.controller.on("volume_change", self._on_volume_change)
        self.controller.on("kiosk_close", self._on_kiosk_close)

    async def on_mount(self) -> None:
        """Setup initial UI state after application is mounted."""
        logger.info("CinemaTUI mounted")
        status = self.query_one("#player-bar", Vertical)
        status.border_title = "Ready (No media playing)"
        
        # Set up terminal output logger
        handler = TextualLoggerHandler(self)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s", "%H:%M:%S")
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)

    def compose(self) -> ComposeResult:
        """Compose top-level layout components."""
        yield TopBar()
        yield Sidebar()
        yield MainContent()
        yield PlayerBar()

    # -------------------------------------------------------------------------
    # Event Handlers (Buttons, Option Lists, Search Input)
    # -------------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses from controls and navigation header."""
        button_id = event.button.id

        if button_id == "play":
            self.action_play_pause()
        elif button_id == "stop":
            self.action_stop()
        elif button_id == "volup":
            self.action_next_vol()
        elif button_id == "voldown":
            self.action_prev_vol()
        elif button_id == "poweroff":
            self.action_poweroff()
        elif button_id == "scan-fast":
            self.action_scan_fast()
        elif button_id == "scan-full":
            if not getattr(self, "_full_scan_confirm", False):
                self._full_scan_confirm = True
                self._update_status(
                    "Press 'Scan Full' again within 6s to confirm full scan", True
                )

                async def _reset():
                    await asyncio.sleep(6)
                    self._full_scan_confirm = False

                asyncio.create_task(_reset())
            else:
                self._full_scan_confirm = False
                self.action_scan_full()
        elif button_id == "cancel-scan":
            self.action_cancel_scan()
        elif button_id == "web":
            # Web button now opens Google directly
            self.run_worker(self.controller.stream_service("google", "https://www.google.com"))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Queue a video file for playback - press Play to start."""
        import os
        path = str(event.path)
        VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"}
        if os.path.splitext(path)[1].lower() in VIDEO_EXTS:
            self._selected_file = path
            name = os.path.basename(path)
            # Show the selected file in the player bar title
            try:
                player_bar = self.query_one("#player-bar", Vertical)
                player_bar.border_title = f"Ready ▶  {name}  — Press [Play] to start"
            except Exception:
                pass
            self._update_status(f"Selected: {name}  — Press Play to start", True)
        else:
            self._update_status(f"Not a video file: {os.path.basename(path)}", False)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle media source, category, or search result selection."""
        categories_list = self.query_one("#categories-list", OptionList)
        results_list = self.query_one("#results-list", OptionList)

        if event.option_list is categories_list:
            selected_text = str(event.option)
            if selected_text == "Netflix":
                self.action_stream_service("netflix")
            elif selected_text == "Prime Video":
                self.action_stream_service("prime")
            elif selected_text == "RaiPlay":
                self.run_worker(self.controller.stream_service("raiplay", "https://www.raiplay.it"))

        elif event.option_list is results_list:
            try:
                file_path = getattr(event.option, "id", None) or str(event.option)
                if isinstance(file_path, str) and file_path.startswith("web:"):
                    svc = file_path.split(":", 1)[1]
                    if svc == "custom":
                        self._update_status(
                            "Paste custom URL into the Search box and press Enter", True
                        )
                        search = self.query_one("#search-box", Input)
                        search.focus()
                    else:
                        self.run_worker(self._async_stream_service(svc))
                else:
                    self.run_worker(self._async_play_file(file_path))
            except Exception as e:
                logger.error(f"Error handling result selection: {e}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search box input submission."""
        search_text = event.value

        if search_text.startswith("http://") or search_text.startswith("https://"):
            self.action_play_url(search_text)
        elif "youtube" in search_text.lower() or "youtu.be" in search_text.lower():
            self.action_play_url(search_text)
        else:
            self.action_search_files(search_text)

    # -------------------------------------------------------------------------
    # Actions & Async Controller Operations
    # -------------------------------------------------------------------------

    def action_play_pause(self) -> None:
        """Toggle playback play/pause state."""
        self.run_worker(self._async_play_pause())

    async def _async_play_pause(self) -> None:
        import os
        state = self.controller.get_state()
        if state.playback_state == PlaybackState.PLAYING:
            # Pause current playback
            success, msg = await self.controller.player_pause()
            self._update_status(msg, success)
        elif state.playback_state == PlaybackState.PAUSED:
            # Resume paused playback
            success, msg = await self.controller.player_resume()
            self._update_status(msg, success)
        elif self._selected_file:
            # Nothing playing – start the queued file
            name = os.path.basename(self._selected_file)
            self._start_spinner(f"Starting {name}")
            try:
                success, msg = await self.controller.play_file(self._selected_file)
                if success:
                    try:
                        player_bar = self.query_one("#player-bar", Vertical)
                        player_bar.border_title = f"▶ Now playing: {name}"
                    except Exception:
                        pass
                self._update_status(msg, success)
            finally:
                self._stop_spinner()
        else:
            self._update_status("No file selected — pick a video from Sources", False)

    def action_stop(self) -> None:
        """Stop current playback."""
        self.run_worker(self._async_stop())

    async def _async_stop(self) -> None:
        success, msg = await self.controller.player_stop()
        self._update_status(msg, success)

    def action_next_vol(self) -> None:
        """Increase system volume."""
        self.run_worker(self._async_volume_up())

    async def _async_volume_up(self) -> None:
        success, msg = await self.controller.volume_up(5)
        self._update_status(msg, success)

    def action_prev_vol(self) -> None:
        """Decrease system volume."""
        self.run_worker(self._async_volume_down())

    async def _async_volume_down(self) -> None:
        success, msg = await self.controller.volume_down(5)
        self._update_status(msg, success)

    def action_poweroff(self) -> None:
        """Initiate system shutdown."""
        self.run_worker(self._async_poweroff())

    async def _async_poweroff(self) -> None:
        success, msg = await self.controller.system_poweroff()
        if success:
            self.exit()

    def action_scan_local(self) -> None:
        """Scan default local media files."""
        self.run_worker(self._async_scan_local())

    async def _async_scan_local(self) -> None:
        success, items, error = await self.controller.scan_files()
        if success:
            self.current_files = items
            self._update_status(f"Found {len(items)} files", True)
        else:
            self._update_status(error or "Scan failed", False)

    def action_scan_fast(self) -> None:
        """Trigger a fast scan of standard media directories."""
        self.run_worker(self._async_scan_fast())

    async def _async_scan_fast(self) -> None:
        self._start_spinner("Scanning (fast)")
        try:
            success, items, error = await self.controller.scan_fast()
            if success:
                self.current_files = items
                results_list = self.query_one("#results-list", OptionList)
                try:
                    results_list.clear()
                except Exception:
                    pass
                for item in items:
                    try:
                        results_list.add_option(item.filename, item.path)
                    except Exception:
                        results_list.add_option(item.filename)
                self._update_status(f"Found {len(items)} files", True)
            else:
                self._update_status(error or "Scan failed", False)
        finally:
            self._stop_spinner()

    def action_scan_full(self) -> None:
        """Trigger a deep scan across available paths."""
        self._update_status("Starting full scan (may take long)...", True)
        self.run_worker(self._async_scan_full())

    async def _async_scan_full(self) -> None:
        self._start_spinner("Scanning (full)")
        try:
            success, items, error = await self.controller.scan_full()
            if success:
                self.current_files = items
                results_list = self.query_one("#results-list", OptionList)
                try:
                    results_list.clear()
                except Exception:
                    pass
                for item in items:
                    try:
                        results_list.add_option(item.filename, item.path)
                    except Exception:
                        results_list.add_option(item.filename)
                self._update_status(f"Full scan found {len(items)} files", True)
            else:
                self._update_status(error or "Full scan failed", False)
        finally:
            self._stop_spinner()

    def action_cancel_scan(self) -> None:
        """Cancel ongoing file scanning."""
        self.run_worker(self._async_cancel_scan())

    async def _async_cancel_scan(self) -> None:
        cancelled = self.controller.cancel_scan()
        if cancelled:
            self._stop_spinner()
            self._update_status("Scan cancelled", True)
        else:
            self._update_status("No scan to cancel", False)

    def action_search_files(self, pattern: str) -> None:
        """Search local files matching pattern."""
        self.run_worker(self._async_search_files(pattern))

    async def _async_search_files(self, pattern: str) -> None:
        success, items, error = await self.controller.scan_files(pattern=pattern)
        if success:
            self.current_files = items
            self._update_status(f"Found {len(items)} matches", True)
        else:
            self._update_status(f"No matches for '{pattern}'", False)

    def action_play_url(self, url: str) -> None:
        """Play media from a direct URL or YouTube link."""
        self.run_worker(self._async_play_url(url))

    async def _async_play_url(self, url: str) -> None:
        success, msg = await self.controller.play_youtube(url)
        self._update_status(msg, success)

    def action_stream_service(self, service: str) -> None:
        """Launch web kiosk streaming service."""
        self.run_worker(self._async_stream_service(service))

    async def _async_stream_service(self, service: str) -> None:
        success, msg = await self.controller.stream_service(service)
        self._update_status(msg, success)

    async def _async_play_file(self, path: str) -> None:
        """Play local media file."""
        if not path:
            self._update_status("No file selected", False)
            return
        self._start_spinner("Starting playback")
        try:
            success, msg = await self.controller.play_file(path)
            self._update_status(msg, success)
        finally:
            self._stop_spinner()

    async def action_quit(self) -> None:
        """Cleanup controller resources and quit application."""
        logger.info("Quitting CinemaTUI")
        await self.controller.cleanup()
        self.exit()

    # -------------------------------------------------------------------------
    # UI Helpers (Status, Spinner, Web Options)
    # -------------------------------------------------------------------------

    def _update_status(self, message: str, success: bool = True) -> None:
        """Update status display message."""
        try:
            status_info = self.query_one("#status-info", Static)
            color = "#98c379" if success else "#e06c75"
            status_info.update(f"[{color}]{message}[/]")
        except Exception as e:
            logger.debug(f"Could not update status display: {e}")

    def _start_spinner(self, label: str = "Working") -> None:
        """Start a spinner animation in player bar."""
        if getattr(self, "_spinner_task", None):
            return
        self._spinner_running = True
        spinner_widget = self.query_one("#spinner", Static)

        async def _spin():
            chars = "|/-\\"
            i = 0
            while self._spinner_running:
                try:
                    spinner_widget.update(f"{label} {chars[i % len(chars)]}")
                except Exception:
                    pass
                i += 1
                await asyncio.sleep(0.12)
            try:
                spinner_widget.update("")
            except Exception:
                pass

        self._spinner_task = asyncio.create_task(_spin())

    def _stop_spinner(self) -> None:
        """Stop spinner animation task."""
        self._spinner_running = False
        task = getattr(self, "_spinner_task", None)
        if task and not task.done():
            task.cancel()
        self._spinner_task = None

    def _show_web_options(self) -> None:
        """Populate results list with web streaming choices."""
        results_list = self.query_one("#results-list", OptionList)
        try:
            results_list.clear()
        except Exception:
            pass
        try:
            results_list.add_option("Netflix", "web:netflix")
            results_list.add_option("Prime Video", "web:prime")
            results_list.add_option("YouTube", "web:youtube")
            results_list.add_option("Custom URL...", "web:custom")
        except Exception:
            results_list.add_option("Netflix")
            results_list.add_option("Prime Video")
            results_list.add_option("YouTube")
            results_list.add_option("Custom URL...")

    # -------------------------------------------------------------------------
    # Controller Event Callbacks
    # -------------------------------------------------------------------------

    def _on_playback_finish(self) -> None:
        """Callback triggered when media playback completes."""
        self._update_status("Playback finished", True)

    def _on_error(self, error_msg: str) -> None:
        """Callback triggered when an error occurs in controller."""
        self._update_status(f"Error: {error_msg}", False)

    def _on_volume_change(self, volume: int) -> None:
        """Callback triggered when system/player volume changes."""
        self._update_status(f"Volume: {volume}%", True)

    def _on_kiosk_close(self) -> None:
        """Callback triggered when web kiosk browser closes."""
        self._update_status("Web kiosk closed", True)
