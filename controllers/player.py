"""
Production-ready MPV player controller with async IPC socket communication.

This module provides a robust interface to control mpv playback via its IPC socket,
supporting local files, HTTP URLs, and YouTube links. It manages async subprocess
operations without blocking the Textual event loop.
"""

import asyncio
import json
import logging
import os
import socket
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class PlaybackState(Enum):
    """Enumeration of mpv playback states."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


class MpvController:
    """
    Production-ready MPV player controller with async IPC socket communication.

    Manages mpv process lifecycle, sends JSON commands via IPC socket, and provides
    callbacks for playback completion events.
    """

    DEFAULT_SOCKET = "/tmp/mpvsocket"
    MPV_TIMEOUT = 5.0
    MONITOR_INTERVAL = 0.5
    POSITION_CHECK_THRESHOLD = 1.0

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET,
        on_finish: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize MpvController.

        Args:
            socket_path: Path to mpv IPC socket. Defaults to /tmp/mpvsocket for Linux.
            on_finish: Optional callback invoked when video finishes playing.

        Falls back to the OS default media player (e.g. VLC, Windows Media Player)
        if mpv is not installed.
        """
        self.socket_path = socket_path
        self.on_finish = on_finish
        self.process: Optional[subprocess.Popen] = None
        self.state = PlaybackState.STOPPED
        self.current_file: Optional[str] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._request_counter = 0
        self._use_system_player: bool = False  # fallback when mpv not available

        if not self._check_mpv_installed():
            logger.warning(
                "mpv not found — falling back to OS default media player (os.startfile)."
            )
            self._use_system_player = True
        else:
            logger.info("MpvController initialized successfully with mpv")

    @staticmethod
    def _check_mpv_installed() -> bool:
        """Check if mpv executable is available in system PATH."""
        return shutil.which("mpv") is not None

    async def play(self, file_path: str) -> bool:
        """
        Play a file or URL.

        Uses mpv if available; falls back to the OS default app (os.startfile) on
        systems where mpv is not installed (e.g. Windows).

        Args:
            file_path: Local file path, HTTP URL, or YouTube URL.

        Returns:
            True if play command succeeded, False otherwise.
        """
        try:
            if self._use_system_player:
                # Fallback: open with the OS default application
                import os as _os
                import platform
                logger.info(f"Opening with system player: {file_path}")
                if platform.system() == "Windows":
                    _os.startfile(file_path)
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", file_path])
                else:
                    subprocess.Popen(["xdg-open", file_path])
                self.current_file = file_path
                self.state = PlaybackState.PLAYING
                # Fire finish callback after a short delay since we can't monitor the external process
                if self.on_finish:
                    asyncio.create_task(self._delayed_finish())
                return True

            if self.process is not None:
                await self.stop()

            self.current_file = file_path
            self.state = PlaybackState.PLAYING

            cmd = self._build_mpv_command(file_path)
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )

            logger.info(f"Started mpv with: {file_path}")

            # Start background playback monitor
            self._monitor_task = asyncio.create_task(self._monitor_playback())

            return True

        except Exception as e:
            logger.error(f"Error playing file {file_path}: {e}")
            self.state = PlaybackState.STOPPED
            self.process = None
            return False

    async def _delayed_finish(self, delay: float = 3.0) -> None:
        """Simulate finish event for system player fallback after a short delay."""
        await asyncio.sleep(delay)
        self.state = PlaybackState.STOPPED
        if self.on_finish:
            self.on_finish()

    async def pause(self) -> bool:
        """
        Pause playback.

        Returns:
            True if pause command succeeded, False otherwise.
        """
        if self.state != PlaybackState.PLAYING:
            logger.warning("Cannot pause: not currently playing")
            return False

        success = await self._send_command(["set_property", "pause", True])
        if success:
            self.state = PlaybackState.PAUSED
            logger.debug("Playback paused")
        return success

    async def resume(self) -> bool:
        """
        Resume playback from pause.

        Returns:
            True if resume command succeeded, False otherwise.
        """
        if self.state != PlaybackState.PAUSED:
            logger.warning("Cannot resume: not currently paused")
            return False

        success = await self._send_command(["set_property", "pause", False])
        if success:
            self.state = PlaybackState.PLAYING
            logger.debug("Playback resumed")
        return success

    async def stop(self) -> bool:
        """
        Stop playback and terminate mpv process.

        Returns:
            True if stop succeeded, False otherwise.
        """
        if self.process is None:
            return False

        try:
            # Attempt graceful quit via IPC
            await self._send_command(["quit"])
        except Exception:
            pass

        # Force terminate if still running
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        self.process = None
        self.state = PlaybackState.STOPPED
        self.current_file = None

        # Cancel monitoring task
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None

        # Clean up socket file if it exists
        self._cleanup_socket()

        logger.info("Stopped mpv process and cleaned up resources")
        return True

    async def volume_up(self, step: float = 5.0) -> bool:
        """
        Increase volume by step.

        Args:
            step: Volume increment in percentage points (default 5.0).

        Returns:
            True if command succeeded, False otherwise.
        """
        success = await self._send_command(["add", "volume", step])
        if success:
            logger.debug(f"Volume increased by {step}")
        return success

    async def volume_down(self, step: float = 5.0) -> bool:
        """
        Decrease volume by step.

        Args:
            step: Volume decrement in percentage points (default 5.0).

        Returns:
            True if command succeeded, False otherwise.
        """
        success = await self._send_command(["add", "volume", -step])
        if success:
            logger.debug(f"Volume decreased by {step}")
        return success

    async def seek(self, seconds: float) -> bool:
        """
        Seek to absolute playback position.

        Args:
            seconds: Target position in seconds.

        Returns:
            True if seek command succeeded, False otherwise.
        """
        success = await self._send_command(["seek", seconds, "absolute"])
        if success:
            logger.debug(f"Seeked to {seconds}s")
        return success

    async def get_volume(self) -> Optional[float]:
        """
        Query current volume level.

        Returns:
            Volume level (0-100) or None if query fails.
        """
        try:
            result = await self._send_command(
                ["get_property", "volume"], expect_response=True
            )
            if result and isinstance(result, dict):
                volume = result.get("data")
                if isinstance(volume, (int, float)):
                    return float(volume)
        except Exception as e:
            logger.debug(f"Error querying volume: {e}")
        return None

    async def get_duration(self) -> Optional[float]:
        """
        Query video duration.

        Returns:
            Duration in seconds or None if query fails.
        """
        try:
            result = await self._send_command(
                ["get_property", "duration"], expect_response=True
            )
            if result and isinstance(result, dict):
                duration = result.get("data")
                if isinstance(duration, (int, float)):
                    return float(duration)
        except Exception as e:
            logger.debug(f"Error querying duration: {e}")
        return None

    async def get_position(self) -> Optional[float]:
        """
        Query current playback position.

        Returns:
            Current position in seconds or None if query fails.
        """
        try:
            result = await self._send_command(
                ["get_property", "time-pos"], expect_response=True
            )
            if result and isinstance(result, dict):
                position = result.get("data")
                if isinstance(position, (int, float)):
                    return float(position)
        except Exception as e:
            logger.debug(f"Error querying position: {e}")
        return None

    def _build_mpv_command(self, file_path: str) -> List[str]:
        """
        Build mpv command with appropriate options for file type.

        Detects YouTube/HTTP URLs and applies yt-dlp format selection.

        Args:
            file_path: File path or URL to play.

        Returns:
            Command list suitable for subprocess.Popen.
        """
        cmd = [
            "mpv",
            "--fullscreen",
            f"--input-ipc-server={self.socket_path}",
            "--no-video-window-title",
            "--keep-open=yes",
            "--script-opts=input.conf",
        ]

        # Enable YouTube format selection for YouTube URLs
        if self._is_youtube_url(file_path):
            cmd.append("--ytdl-format=best[height<=720]")

        cmd.append(file_path)
        return cmd

    @staticmethod
    def _is_youtube_url(url: str) -> bool:
        """Check if URL is a YouTube link."""
        return any(
            domain in url.lower()
            for domain in ["youtube.com", "youtu.be", "yt.be"]
        )

    async def _send_command(
        self,
        command: List[Any],
        expect_response: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Send JSON command to mpv via IPC socket with non-blocking I/O.

        Uses asyncio executor to prevent blocking the event loop. Handles socket
        connection failures gracefully with timeout.

        Args:
            command: mpv command as a list (e.g., ["set_property", "pause", True]).
            expect_response: Whether to wait for and parse mpv response.

        Returns:
            Response dict if expect_response=True and response received, else None.
        """
        if self.process is None or self.process.poll() is not None:
            logger.debug("mpv process is not running, cannot send command")
            return None

        # Check if socket exists and is accessible
        if not os.path.exists(self.socket_path):
            logger.debug(f"Socket {self.socket_path} does not exist yet")
            return None

        try:
            payload = {"command": command}
            message = json.dumps(payload) + "\n"

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.MPV_TIMEOUT)

            try:
                # Connect and send in executor to avoid blocking
                await asyncio.get_event_loop().run_in_executor(
                    None, sock.connect, self.socket_path
                )

                await asyncio.get_event_loop().run_in_executor(
                    None, sock.sendall, message.encode()
                )

                # Receive response if expected
                if expect_response:
                    response_bytes = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, sock.recv, 4096
                        ),
                        timeout=self.MPV_TIMEOUT,
                    )
                    response_text = response_bytes.decode().strip()
                    if response_text:
                        return json.loads(response_text)

                return {"status": "ok"} if expect_response else None

            finally:
                sock.close()

        except socket.timeout:
            logger.debug("Socket communication timeout")
            return None
        except (socket.error, OSError) as e:
            logger.debug(f"Socket error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"JSON decode error in response: {e}")
            return None
        except asyncio.TimeoutError:
            logger.debug("Async operation timeout")
            return None
        except Exception as e:
            logger.debug(f"Unexpected error in IPC communication: {e}")
            return None

    async def _monitor_playback(self) -> None:
        """
        Monitor playback and detect when video finishes.

        Runs in background, periodically checking if playback has reached the end.
        Invokes on_finish callback when video completes.
        """
        try:
            while self.process and self.process.poll() is None:
                await asyncio.sleep(self.MONITOR_INTERVAL)

                if self.state == PlaybackState.PLAYING:
                    try:
                        pos = await self.get_position()
                        duration = await self.get_duration()

                        # Check if near end of video
                        if (
                            pos is not None
                            and duration is not None
                            and pos >= duration - self.POSITION_CHECK_THRESHOLD
                        ):
                            logger.debug("Video playback completed")
                            if self.on_finish:
                                self.on_finish()
                            self.state = PlaybackState.STOPPED
                            break

                    except Exception as e:
                        logger.debug(f"Error checking playback position: {e}")

            # Process exited naturally
            if self.on_finish and self.state == PlaybackState.PLAYING:
                logger.debug("mpv process terminated, invoking finish callback")
                self.on_finish()
                self.state = PlaybackState.STOPPED

        except asyncio.CancelledError:
            logger.debug("Playback monitor task cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in playback monitor: {e}")

    def _cleanup_socket(self) -> None:
        """Remove socket file if it exists."""
        try:
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
                logger.debug(f"Cleaned up socket at {self.socket_path}")
        except OSError as e:
            logger.debug(f"Could not clean up socket: {e}")

    async def cleanup(self) -> None:
        """
        Clean up all resources: stop playback and remove socket file.

        Safe to call multiple times.
        """
        await self.stop()
        self._cleanup_socket()
        logger.info("MpvController cleanup completed")
