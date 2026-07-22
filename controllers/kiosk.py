"""
WebKiosk Controller for CinemaTUI

Manages Chromium browser in kiosk mode for streaming services integration.
Handles process lifecycle, graceful shutdown, and TUI integration.
"""

import asyncio
import logging
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class WebKioskException(Exception):
    """Base exception for kiosk operations."""
    pass


class ChromiumNotFoundError(WebKioskException):
    """Raised when Chromium is not installed."""
    pass


class InvalidURLError(WebKioskException):
    """Raised when URL is invalid."""
    pass


class KioskProcessError(WebKioskException):
    """Raised when kiosk process fails."""
    pass


class WebKiosk:
    """
    Manages Chromium browser in kiosk mode for streaming services.
    
    Features:
        - Launch Chromium with kiosk flags
        - Support Netflix, Prime Video, and generic URLs
        - Async process management with graceful shutdown
        - Detect process termination
        - Callback mechanism for UI integration
    """
    
    CHROMIUM_EXECUTABLES = [
        "chromium-browser",
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "google-chrome-beta",
        "google-chrome-dev",
    ]
    SHUTDOWN_TIMEOUT = 15  # seconds
    PROCESS_CHECK_INTERVAL = 0.5  # seconds
    
    def __init__(
        self,
        on_kiosk_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Initialize WebKiosk controller.
        
        Args:
            on_kiosk_closed: Optional callback when kiosk closes.
        """
        self.process: Optional[subprocess.Popen] = None
        self.current_url: Optional[str] = None
        self.on_kiosk_closed = on_kiosk_closed
        self._monitor_task: Optional[asyncio.Task] = None
        logger.debug("WebKiosk initialized")
    
    @staticmethod
    def find_chromium() -> Optional[str]:
        """
        Find Chromium executable in system PATH.
        
        Returns:
            Path to chromium executable or None if not found.
        """
        for executable in WebKiosk.CHROMIUM_EXECUTABLES:
            path = shutil.which(executable)
            if path:
                logger.debug(f"Found chromium at: {path}")
                return path
        logger.warning("Chromium not found in PATH")
        return None
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format.
        
        Args:
            url: URL to validate.
            
        Returns:
            True if URL is valid, False otherwise.
        """
        try:
            result = urlparse(url)
            is_valid = all([result.scheme, result.netloc])
            if not is_valid:
                logger.warning(f"Invalid URL format: {url}")
            return is_valid
        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalize URL by adding scheme if missing.
        
        Args:
            url: URL to normalize.
            
        Returns:
            Normalized URL.
        """
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url
    
    async def launch(self, url: str, disable_audio: bool = False) -> None:
        """
        Launch Chromium in kiosk mode with the given URL.
        
        Args:
            url: URL to open in kiosk mode.
            disable_audio: If True, disable audio output.
            
        Raises:
            ChromiumNotFoundError: If Chromium is not installed.
            InvalidURLError: If URL is invalid.
            KioskProcessError: If process launch fails.
        """
        if self.process is not None:
            raise KioskProcessError("Kiosk already running")
        
        chromium_path = self.find_chromium()
        if not chromium_path:
            raise ChromiumNotFoundError(
                "Chromium not found. Install with: sudo apt install chromium-browser"
            )
        
        url = self.normalize_url(url)
        if not self.validate_url(url):
            raise InvalidURLError(f"Invalid URL: {url}")
        
        self.current_url = url
        logger.info(f"Launching kiosk with URL: {url}")
        
        try:
            args = [
                chromium_path,
                "--kiosk",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-breakpad",
                "--disable-client-side-phishing-detection",
                "--disable-component-extensions-with-background-pages",
                "--disable-default-apps",
                "--disable-device-discovery-notifications",
                "--disable-extensions",
                "--disable-features=TranslateUI",
                "--disable-hang-monitor",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--disable-sync",
                "--enable-automation",
                "--no-default-browser-check",
                url,
            ]
            
            if disable_audio:
                args.insert(1, "--mute-audio")
            
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            
            logger.info(f"Kiosk process started with PID: {self.process.pid}")
            self._monitor_task = asyncio.create_task(self._monitor_process())
            
        except FileNotFoundError as e:
            self.process = None
            raise KioskProcessError(f"Failed to launch chromium: {e}")
        except Exception as e:
            self.process = None
            raise KioskProcessError(f"Unexpected error during launch: {e}")
    
    async def _monitor_process(self) -> None:
        """
        Monitor process and detect when it terminates.
        
        Runs continuously while process is active, checking periodically
        for unexpected termination.
        """
        while self.process and self.process.poll() is None:
            await asyncio.sleep(self.PROCESS_CHECK_INTERVAL)
        
        logger.info("Kiosk process terminated")
        await self._cleanup()
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown kiosk process.
        
        Attempts SIGTERM first, then SIGKILL after timeout.
        """
        if self.process is None:
            logger.debug("No kiosk process to shutdown")
            return
        
        logger.info(f"Shutting down kiosk process (PID: {self.process.pid})")
        
        try:
            if self.process.poll() is None:
                if hasattr(signal, "SIGTERM"):
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                else:
                    self.process.terminate()
                
                try:
                    await asyncio.wait_for(
                        self._wait_process_exit(),
                        timeout=self.SHUTDOWN_TIMEOUT,
                    )
                    logger.info("Kiosk process terminated gracefully")
                except asyncio.TimeoutError:
                    logger.warning("Kiosk process did not terminate gracefully, forcing kill")
                    if hasattr(signal, "SIGKILL"):
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    else:
                        self.process.kill()
                    await self._wait_process_exit()
        
        except ProcessLookupError:
            logger.debug("Process already terminated")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            await self._cleanup()
    
    async def _wait_process_exit(self) -> None:
        """Wait for process to exit."""
        while self.process and self.process.poll() is None:
            await asyncio.sleep(0.1)
    
    async def _cleanup(self) -> None:
        """Clean up resources after process terminates."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        self.process = None
        self.current_url = None
        
        logger.debug("Cleanup complete")
        
        if self.on_kiosk_closed:
            try:
                if asyncio.iscoroutinefunction(self.on_kiosk_closed):
                    await self.on_kiosk_closed()
                else:
                    self.on_kiosk_closed()
            except Exception as e:
                logger.error(f"Error in on_kiosk_closed callback: {e}")
    
    def is_running(self) -> bool:
        """
        Check if kiosk process is currently running.
        
        Returns:
            True if process is running, False otherwise.
        """
        if self.process is None:
            return False
        return self.process.poll() is None
    
    async def open_netflix(self) -> None:
        """Open Netflix in kiosk mode."""
        await self.launch("https://www.netflix.com")
    
    async def open_prime_video(self) -> None:
        """Open Prime Video in kiosk mode."""
        await self.launch("https://www.primevideo.com")
    
    async def open_url(self, url: str) -> None:
        """
        Open custom URL in kiosk mode.
        
        Args:
            url: URL to open.
        """
        await self.launch(url)


class KioskManager:
    """
    High-level manager for kiosk operations with context management.
    
    Provides async context manager interface for clean resource handling.
    """
    
    def __init__(self) -> None:
        """Initialize kiosk manager."""
        self.kiosk = WebKiosk(on_kiosk_closed=self._on_kiosk_closed)
        self._closed_event: Optional[asyncio.Event] = None
    
    async def _on_kiosk_closed(self) -> None:
        """Handle kiosk close event."""
        if self._closed_event:
            self._closed_event.set()
        logger.info("Kiosk closed, control returned to TUI")
    
    async def __aenter__(self) -> "KioskManager":
        """Enter async context."""
        self._closed_event = asyncio.Event()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context and cleanup."""
        await self.kiosk.shutdown()
    
    async def launch(self, url: str) -> None:
        """
        Launch kiosk and wait for it to close.
        
        Args:
            url: URL to open.
        """
        await self.kiosk.launch(url)
        if self._closed_event:
            await self._closed_event.wait()
    
    async def shutdown(self) -> None:
        """Shutdown kiosk."""
        await self.kiosk.shutdown()
    
    def is_running(self) -> bool:
        """Check if kiosk is running."""
        return self.kiosk.is_running()
