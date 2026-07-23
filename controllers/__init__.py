"""
CinemaController: Production-ready orchestrator for CinemaTUI.

Provides unified interface aggregating:
- FileScanner (async video discovery with caching)
- MpvController (async playback via IPC socket)
- WebKiosk/KioskManager (Chromium in kiosk mode)
- SystemControl (audio backend detection and control)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple
from pathlib import Path

from controllers.kiosk import (
    ChromiumNotFoundError,
    InvalidURLError,
    KioskManager,
    KioskProcessError,
    WebKiosk,
    WebKioskException,
)
from controllers.player import MpvController, PlaybackState as MpvPlaybackState
from controllers.scanner import FileScanner, VideoFile
from controllers.system import SystemControl, VolumeInfo, AudioBackend

logger = logging.getLogger(__name__)


class PlaybackState(Enum):
    """High-level playback state enumeration."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"


class KioskState(Enum):
    """Kiosk (streaming service) state enumeration."""
    CLOSED = "closed"
    LOADING = "loading"
    ACTIVE = "active"


@dataclass
class MediaItem:
    """Represents a discovered media file."""
    filename: str
    path: str
    size: int
    duration: Optional[str] = None

    @classmethod
    def from_video_file(cls, video: VideoFile) -> "MediaItem":
        """Create from FileScanner VideoFile."""
        return cls(
            filename=video.filename,
            path=video.path,
            size=video.size,
            duration=video.duration
        )


@dataclass
class ControllerState:
    """Tracks controller state for TUI status display."""
    playback_state: PlaybackState = PlaybackState.STOPPED
    current_file: Optional[str] = None
    current_volume: int = 70
    kiosk_state: KioskState = KioskState.CLOSED
    current_service: Optional[str] = None
    scan_in_progress: bool = False
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None


class CinemaController:
    """
    Production-ready orchestrator for CinemaTUI backend agents.
    
    Orchestrates:
    - FileScanner: Async video file discovery with 5-minute caching
    - MpvController: Media playback via async IPC socket communication
    - KioskManager: Chromium browser in kiosk mode for streaming services
    - SystemControl: Audio backend detection and volume control
    
    Features:
    - Unified error handling with user-friendly messages
    - Event callback system for playback and kiosk events
    - Async/await throughout for non-blocking operations
    - Comprehensive logging and state tracking
    """

    def __init__(self) -> None:
        """Initialize CinemaController with all backend agents."""
        self._setup_logging()

        # Backend agents
        self.scanner = FileScanner()
        self.system = SystemControl()

        # Player and kiosk initialized with callbacks
        self.player: Optional[MpvController] = None
        self.kiosk_manager = KioskManager()

        # State management
        self.state = ControllerState()
        self._callbacks: Dict[str, List[Callable]] = {
            "playback_finish": [],
            "kiosk_close": [],
            "error": [],
            "volume_change": []
        }

        self._player_initialized = False
        self.logger = logging.getLogger(__name__)
        self.logger.info("CinemaController initialized")

    def _setup_logging(self) -> None:
        """Configure logging for the controller."""
        if not logging.getLogger(__name__).handlers:
            # We add a NullHandler so it doesn't complain if no root logger is configured,
            # but we do NOT add a StreamHandler to avoid corrupting the TUI.
            logging.getLogger(__name__).addHandler(logging.NullHandler())
            logging.getLogger(__name__).setLevel(logging.INFO)

    def _ensure_player_initialized(self) -> bool:
        """
        Initialize MpvController if not already done.
        
        Returns:
            True if player is ready, False if initialization failed.
        """
        if self._player_initialized:
            return self.player is not None

        try:
            self.player = MpvController(on_finish=self._on_playback_finish)
            self._player_initialized = True
            self.logger.info("MpvController initialized successfully")
            return True
        except RuntimeError as e:
            error_msg = str(e)
            self._set_error(error_msg)
            self.logger.error(f"Failed to initialize MpvController: {error_msg}")
            return False

    def _on_playback_finish(self) -> None:
        """Callback invoked when playback finishes."""
        self.state.playback_state = PlaybackState.STOPPED
        self.logger.info("Playback finished")
        self._emit("playback_finish")

    def on(self, event: str, callback: Callable) -> None:
        """
        Register event callback.
        
        Args:
            event: Event name ("playback_finish", "kiosk_close", "error", "volume_change")
            callback: Callable to execute
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
            self.logger.debug(f"Registered callback for {event}")

    def off(self, event: str, callback: Callable) -> None:
        """
        Unregister event callback.
        
        Args:
            event: Event name
            callback: Callback to remove
        """
        if event in self._callbacks and callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)
            self.logger.debug(f"Unregistered callback for {event}")

    def _emit(self, event: str, *args, **kwargs) -> None:
        """Emit event to all registered callbacks (non-blocking)."""
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(*args, **kwargs))
                    else:
                        callback(*args, **kwargs)
                except Exception as e:
                    self.logger.error(f"Callback error in {event}: {e}", exc_info=True)

    def _set_error(self, message: str) -> None:
        """Set error state and emit error callback."""
        self.state.last_error = message
        self.state.last_error_time = datetime.now()
        self.logger.error(f"Error state set: {message}")
        self._emit("error", message)

    async def scan_files(
        self,
        paths: Optional[List[str]] = None,
        pattern: Optional[str] = None,
        use_cache: bool = True
    ) -> Tuple[bool, List[MediaItem], Optional[str]]:
        """
        Scan directory for media files asynchronously with caching.
        
        Args:
            paths: List of directory paths to scan. Defaults to ~/Videos, ~/Downloads.
            pattern: Optional regex pattern to filter filenames (case-insensitive).
            use_cache: Whether to use cached results if available (default: True).
        
        Returns:
            (success, media_items, error_message)
            
        Example:
            success, items, err = await controller.scan_files(['/mnt/videos'], pattern='avengers')
            if success:
                print(f"Found {len(items)} files")
            else:
                print(f"Scan failed: {err}")
        """
        try:
            self.state.scan_in_progress = True
            results = await self.scanner.scan(paths=paths, pattern=pattern, use_cache=use_cache)
            self.state.scan_in_progress = False

            if not results:
                error_msg = "No files found or scan failed"
                self._set_error(error_msg)
                return False, [], error_msg

            items = [
                MediaItem(
                    filename=r.get("filename", ""),
                    path=r.get("path", ""),
                    size=r.get("size", 0),
                    duration=r.get("duration")
                )
                for r in results
            ]

            self.logger.info(f"Scanned {len(items)} files")
            return True, items, None

        except Exception as e:
            error_msg = f"Scan error: {str(e)}"
            self._set_error(error_msg)
            self.logger.error(error_msg, exc_info=True)
            self.state.scan_in_progress = False
            return False, [], error_msg

    async def play_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Start playback of a local file.
        
        Args:
            file_path: Path to media file
        
        Returns:
            (success, message)
        """
        try:
            if not file_path:
                return False, "File path is required"

            media_path = Path(file_path).expanduser()
            if not media_path.is_file():
                error_msg = f"File not found: {file_path}"
                self._set_error(error_msg)
                return False, error_msg

            if not self._ensure_player_initialized():
                return False, "Media player not available"

            success = await self.player.play(str(media_path))
            if success:
                self.state.playback_state = PlaybackState.PLAYING
                self.state.current_file = str(media_path)
                self.logger.info(f"Started playback: {file_path}")
                return True, "Playback started"
            else:
                error_msg = f"Failed to start playback: {file_path}"
                self._set_error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Play error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def play_youtube(self, url: str) -> Tuple[bool, str]:
        """
        Play YouTube video via mpv.
        
        Args:
            url: YouTube URL
        
        Returns:
            (success, message)
        """
        try:
            if not self._ensure_player_initialized():
                return False, "Media player not available"

            if not any(domain in url.lower() for domain in ["youtube.com", "youtu.be", "yt.be"]):
                return False, "Invalid YouTube URL"

            success = await self.player.play(url)
            if success:
                self.state.playback_state = PlaybackState.PLAYING
                self.state.current_file = url
                self.logger.info(f"Started YouTube playback: {url}")
                return True, "YouTube playback started"
            else:
                error_msg = "Failed to start YouTube playback"
                self._set_error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"YouTube error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def stream_service(
        self,
        service: str,
        custom_url: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Launch streaming service in Chromium kiosk mode.
        
        Args:
            service: Service name ("netflix", "prime", or custom)
            custom_url: Optional custom URL instead of predefined
        
        Returns:
            (success, message)
        """
        try:
            service_lower = service.lower()
            service_urls = {
                "netflix": "https://www.netflix.com",
                "prime": "https://www.primevideo.com",
                "youtube": "https://www.youtube.com"
            }

            url = custom_url or service_urls.get(service_lower)
            if not url:
                return False, f"Unknown service: {service}"

            # Launch kiosk in background - KioskManager.launch blocks until kiosk closes.
            self.state.kiosk_state = KioskState.ACTIVE
            self.state.current_service = service
            self.logger.info(f"Launching {service} in kiosk mode")
            # This call will block until the kiosk/browser exits; after it returns, emit kiosk_close
            await self.kiosk_manager.launch(url)

            # After kiosk returns, update state and emit kiosk_close
            self.state.kiosk_state = KioskState.CLOSED
            self.state.current_service = None
            self.logger.info(f"Kiosk {service} closed")
            self._emit("kiosk_close")
            return True, f"{service} closed"

        except ChromiumNotFoundError:
            error_msg = "Chromium not installed. Install: sudo apt install chromium-browser"
            self._set_error(error_msg)
            return False, error_msg
        except InvalidURLError as e:
            error_msg = f"Invalid URL: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg
        except KioskProcessError as e:
            error_msg = f"Kiosk error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Stream error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def player_pause(self) -> Tuple[bool, str]:
        """
        Pause playback.
        
        Returns:
            (success, message)
        """
        try:
            if not self.player:
                return False, "No playback to pause"

            success = await self.player.pause()
            if success:
                self.state.playback_state = PlaybackState.PAUSED
                self.logger.info("Playback paused")
                return True, "Paused"
            else:
                return False, "Could not pause"

        except Exception as e:
            error_msg = f"Pause error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def player_resume(self) -> Tuple[bool, str]:
        """
        Resume playback from pause.
        
        Returns:
            (success, message)
        """
        try:
            if not self.player:
                return False, "No playback to resume"

            success = await self.player.resume()
            if success:
                self.state.playback_state = PlaybackState.PLAYING
                self.logger.info("Playback resumed")
                return True, "Resumed"
            else:
                return False, "Could not resume"

        except Exception as e:
            error_msg = f"Resume error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def player_stop(self) -> Tuple[bool, str]:
        """
        Stop playback and terminate player process.
        
        Returns:
            (success, message)
        """
        try:
            if not self.player:
                return False, "No playback to stop"

            success = await self.player.stop()
            if success:
                self.state.playback_state = PlaybackState.STOPPED
                self.state.current_file = None
                self.logger.info("Playback stopped")
                return True, "Stopped"
            else:
                return False, "Could not stop"

        except Exception as e:
            error_msg = f"Stop error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def volume_up(self, step: int = 5) -> Tuple[bool, str]:
        """
        Increase volume.
        
        Args:
            step: Volume increment percentage (default: 5)
        
        Returns:
            (success, message)
        """
        try:
            if self.player and self.player.process is not None:
                success = await self.player.volume_up(float(step))
                if success:
                    self.state.current_volume = min(100, self.state.current_volume + step)
                    self.logger.info(f"Volume increased: {self.state.current_volume}%")
                    self._emit("volume_change", self.state.current_volume)
                    return True, f"Volume: {self.state.current_volume}%"

            success = await self.system.increase_volume(step)
            if success:
                volume, _ = await self.get_volume()
                if volume is not None:
                    self.state.current_volume = volume
                else:
                    self.state.current_volume = min(100, self.state.current_volume + step)
                self.logger.info(f"Volume increased: {self.state.current_volume}%")
                self._emit("volume_change", self.state.current_volume)
                return True, f"Volume: {self.state.current_volume}%"
            return False, "Could not increase volume"

        except Exception as e:
            error_msg = f"Volume up error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def volume_down(self, step: int = 5) -> Tuple[bool, str]:
        """
        Decrease volume.
        
        Args:
            step: Volume decrement percentage (default: 5)
        
        Returns:
            (success, message)
        """
        try:
            if self.player and self.player.process is not None:
                success = await self.player.volume_down(float(step))
                if success:
                    self.state.current_volume = max(0, self.state.current_volume - step)
                    self.logger.info(f"Volume decreased: {self.state.current_volume}%")
                    self._emit("volume_change", self.state.current_volume)
                    return True, f"Volume: {self.state.current_volume}%"

            success = await self.system.decrease_volume(step)
            if success:
                volume, _ = await self.get_volume()
                if volume is not None:
                    self.state.current_volume = volume
                else:
                    self.state.current_volume = max(0, self.state.current_volume - step)
                self.logger.info(f"Volume decreased: {self.state.current_volume}%")
                self._emit("volume_change", self.state.current_volume)
                return True, f"Volume: {self.state.current_volume}%"
            return False, "Could not decrease volume"

        except Exception as e:
            error_msg = f"Volume down error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def get_volume(self) -> Tuple[Optional[int], Optional[str]]:
        """
        Get current volume level from system audio backend.
        
        Returns:
            (volume_level, error_message) where volume_level is 0-100 or None
        """
        try:
            volume_info = await self.system.get_volume()
            if volume_info:
                self.state.current_volume = volume_info.level
                return volume_info.level, None
            else:
                return None, "Could not query volume"

        except Exception as e:
            error_msg = f"Volume query error: {str(e)}"
            self.logger.error(error_msg)
            return None, error_msg

    async def set_volume(self, level: int) -> Tuple[bool, str]:
        """
        Set volume level to specific value (0-100).
        
        Args:
            level: Volume level percentage
        
        Returns:
            (success, message)
        """
        try:
            if not 0 <= level <= 100:
                return False, "Volume must be 0-100"

            success = await self.system.set_volume(level)
            if success:
                self.state.current_volume = level
                self.logger.info(f"Volume set to {level}%")
                self._emit("volume_change", level)
                return True, f"Volume: {level}%"
            else:
                return False, "Could not set volume"

        except Exception as e:
            error_msg = f"Set volume error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def close_kiosk(self) -> Tuple[bool, str]:
        """
        Close active kiosk gracefully.
        
        Returns:
            (success, message)
        """
        try:
            await self.kiosk_manager.shutdown()
            self.state.kiosk_state = KioskState.CLOSED
            self.state.current_service = None
            self.logger.info("Kiosk closed")
            self._emit("kiosk_close")
            return True, "Kiosk closed"

        except Exception as e:
            error_msg = f"Kiosk close error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    async def system_poweroff(self, force: bool = False) -> Tuple[bool, str]:
        """
        Safely shutdown system.
        
        Args:
            force: Force shutdown without confirmation
        
        Returns:
            (success, message)
        """
        try:
            success = await self.system.shutdown()
            if success:
                self.logger.info("System shutdown initiated")
                return True, "Shutdown initiated"
            else:
                error_msg = "Shutdown failed - check permissions"
                self._set_error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Poweroff error: {str(e)}"
            self._set_error(error_msg)
            return False, error_msg

    def get_state(self) -> ControllerState:
        """
        Get current controller state.
        
        Returns:
            ControllerState object with all current states
        """
        return self.state

    async def scan_fast(self, pattern: Optional[str]=None, use_cache: bool=True) -> Tuple[bool, List[MediaItem], Optional[str]]:
        """
        Fast scan: scan default user locations (~/Videos, ~/Downloads, /mnt/*).
        Returns (success, items, error_message).
        """
        try:
            self.state.scan_in_progress = True
            home = Path.home()
            paths = [str(home / "Videos"), str(home / "Downloads"), "/mnt"]
            # schedule scan task so it can be cancelled externally
            self._scan_task = asyncio.create_task(self.scanner.scan(paths=paths, pattern=pattern, use_cache=use_cache))
            try:
                results = await self._scan_task
            except asyncio.CancelledError:
                self._scan_task = None
                self.state.scan_in_progress = False
                return False, [], "Scan cancelled"

            if not results:
                error_msg = "No files found or scan failed"
                self._set_error(error_msg)
                return False, [], error_msg

            items = [MediaItem(filename=r.get("filename", ""), path=r.get("path", ""), size=r.get("size", 0), duration=r.get("duration")) for r in results]
            self.logger.info(f"Scanned {len(items)} files (fast)")
            self._scan_task = None
            return True, items, None
        except Exception as e:
            error_msg = f"Fast scan error: {e}"
            self._set_error(error_msg)
            self._scan_task = None
            return False, [], error_msg
        finally:
            self.state.scan_in_progress = False

    async def scan_full(self, pattern: Optional[str]=None) -> Tuple[bool, List[MediaItem], Optional[str]]:
        """
        Full (deep) scan across mounted drives and home directory. May be slow.
        Returns (success, items, error_message).
        """
        try:
            self.state.scan_in_progress = True
            home = Path.home()
            # broadened paths; scanning entire / is dangerous on some systems, so focus on mounts and home
            paths = [str(home), "/mnt", "/media"]
            temp_scanner = FileScanner(max_results=2000)
            # schedule task so cancellation works
            self._scan_task = asyncio.create_task(temp_scanner.scan(paths=paths, pattern=pattern, use_cache=False))
            try:
                results = await self._scan_task
            except asyncio.CancelledError:
                self._scan_task = None
                self.state.scan_in_progress = False
                return False, [], "Scan cancelled"

            if not results:
                error_msg = "No files found or scan failed"
                self._set_error(error_msg)
                return False, [], error_msg

            items = [
                MediaItem(
                    filename=r.get("filename", ""),
                    path=r.get("path", ""),
                    size=r.get("size", 0),
                    duration=r.get("duration"),
                )
                for r in results
            ]

            self.logger.info(f"Full scan found {len(items)} files")
            self._scan_task = None
            return True, items, None

        except Exception as e:
            error_msg = f"Full scan error: {str(e)}"
            self._set_error(error_msg)
            self.logger.error(error_msg, exc_info=True)
            self._scan_task = None
            return False, [], error_msg

        finally:
            self.state.scan_in_progress = False

    def cancel_scan(self) -> bool:
        """Attempt to cancel an ongoing scan task if present."""
        try:
            if hasattr(self, "_scan_task") and self._scan_task is not None:
                if not self._scan_task.done():
                    self._scan_task.cancel()
                    return True
            return False
        except Exception as e:
            self.logger.debug(f"Cancel scan failed: {e}")
            return False

    async def cleanup(self) -> None:
        """
        Gracefully shutdown controller and all backend agents.
        
        Safe to call multiple times.
        """
        try:
            self.logger.info("Shutting down CinemaController")

            if self.player:
                await self.player.cleanup()

            await self.kiosk_manager.shutdown()

            self.logger.info("CinemaController shutdown complete")

        except Exception as e:
            self.logger.error(f"Cleanup error: {e}", exc_info=True)


# Export public API
__all__ = [
    "CinemaController",
    "PlaybackState",
    "KioskState",
    "MediaItem",
    "ControllerState",
    # Backend exceptions for error handling
    "WebKiosk",
    "KioskManager",
    "WebKioskException",
    "ChromiumNotFoundError",
    "InvalidURLError",
    "KioskProcessError",
]


