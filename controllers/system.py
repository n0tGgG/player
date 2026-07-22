import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class AudioBackend(Enum):
    """Supported audio backends"""
    PULSEAUDIO = "pulseaudio"
    PIPEWIRE = "pipewire"
    NONE = "none"


@dataclass
class VolumeInfo:
    """Volume information"""
    level: int
    muted: bool
    backend: AudioBackend


class SystemControl:
    """Production-ready system control module for Linux"""

    def __init__(self) -> None:
        self._backend: Optional[AudioBackend] = None
        self._backend_detected: bool = False

    def _detect_audio_backend(self) -> AudioBackend:
        """
        Detect available audio backend (PipeWire or PulseAudio).
        Result is cached to avoid repeated detection.
        """
        if self._backend_detected:
            return self._backend

        if self._try_pipewire():
            self._backend = AudioBackend.PIPEWIRE
            logger.info("Detected PipeWire audio backend")
            self._backend_detected = True
            return self._backend

        if self._try_pulseaudio():
            self._backend = AudioBackend.PULSEAUDIO
            logger.info("Detected PulseAudio backend")
            self._backend_detected = True
            return self._backend

        self._backend = AudioBackend.NONE
        logger.warning(
            "No audio backend detected (PulseAudio/PipeWire not available)"
        )
        self._backend_detected = True
        return self._backend

    @staticmethod
    def _try_pipewire() -> bool:
        """Check if PipeWire is available and functional"""
        try:
            result = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                timeout=2,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _try_pulseaudio() -> bool:
        """Check if PulseAudio is available and functional"""
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True,
                timeout=2,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def get_volume(self) -> Optional[VolumeInfo]:
        """Get current volume level and mute state"""
        backend = self._detect_audio_backend()

        if backend == AudioBackend.PIPEWIRE:
            return await self._get_volume_pipewire()
        elif backend == AudioBackend.PULSEAUDIO:
            return await self._get_volume_pulseaudio()

        logger.warning("Cannot get volume: no audio backend available")
        return None

    async def _get_volume_pipewire(self) -> Optional[VolumeInfo]:
        """Get volume from PipeWire using wpctl"""
        try:
            process = await asyncio.create_subprocess_exec(
                "wpctl",
                "get-volume",
                "@DEFAULT_AUDIO_SINK@",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=5
            )

            if process.returncode != 0:
                logger.error(f"wpctl error: {stderr.decode()}")
                return None

            output = stdout.decode().strip()
            parts = output.split()
            if len(parts) >= 2:
                level = int(float(parts[1]) * 100)
                level = min(100, max(0, level))
                muted = "[MUTED]" in output
                return VolumeInfo(
                    level=level, muted=muted, backend=AudioBackend.PIPEWIRE
                )
        except asyncio.TimeoutError:
            logger.error("wpctl get-volume timeout")
        except Exception as e:
            logger.error(f"Error getting PipeWire volume: {e}")

        return None

    async def _get_volume_pulseaudio(self) -> Optional[VolumeInfo]:
        """Get volume from PulseAudio using pactl"""
        try:
            process = await asyncio.create_subprocess_exec(
                "pactl",
                "get-sink-volume",
                "@DEFAULT_SINK@",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=5
            )

            if process.returncode != 0:
                logger.error(f"pactl error: {stderr.decode()}")
                return None

            output = stdout.decode().strip()
            match = re.search(r"(\d+)%", output)
            if match:
                level = int(match.group(1))
                level = min(100, max(0, level))
                muted = "yes" in output.lower()
                return VolumeInfo(
                    level=level, muted=muted, backend=AudioBackend.PULSEAUDIO
                )
        except asyncio.TimeoutError:
            logger.error("pactl get-sink-volume timeout")
        except Exception as e:
            logger.error(f"Error getting PulseAudio volume: {e}")

        return None

    async def set_volume(self, level: int) -> bool:
        """
        Set volume level (0-100%).
        Returns True on success, False on failure.
        """
        if not 0 <= level <= 100:
            logger.error(f"Invalid volume level: {level}")
            return False

        backend = self._detect_audio_backend()

        if backend == AudioBackend.PIPEWIRE:
            return await self._set_volume_pipewire(level)
        elif backend == AudioBackend.PULSEAUDIO:
            return await self._set_volume_pulseaudio(level)

        logger.warning("Cannot set volume: no audio backend available")
        return False

    async def _set_volume_pipewire(self, level: int) -> bool:
        """Set volume using PipeWire"""
        try:
            volume_fraction = level / 100.0
            process = await asyncio.create_subprocess_exec(
                "wpctl",
                "set-volume",
                "@DEFAULT_AUDIO_SINK@",
                str(volume_fraction),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=5
            )

            if process.returncode != 0:
                logger.error(f"wpctl set-volume failed: {stderr.decode()}")
                return False

            logger.info(f"Volume set to {level}% via PipeWire")
            return True
        except asyncio.TimeoutError:
            logger.error("wpctl set-volume timeout")
        except Exception as e:
            logger.error(f"Error setting PipeWire volume: {e}")

        return False

    async def _set_volume_pulseaudio(self, level: int) -> bool:
        """Set volume using PulseAudio"""
        try:
            process = await asyncio.create_subprocess_exec(
                "pactl",
                "set-sink-volume",
                "@DEFAULT_SINK@",
                f"{level}%",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=5
            )

            if process.returncode != 0:
                logger.error(
                    f"pactl set-sink-volume failed: {stderr.decode()}"
                )
                return False

            logger.info(f"Volume set to {level}% via PulseAudio")
            return True
        except asyncio.TimeoutError:
            logger.error("pactl set-sink-volume timeout")
        except Exception as e:
            logger.error(f"Error setting PulseAudio volume: {e}")

        return False

    async def set_mute(self, muted: bool) -> bool:
        """
        Mute or unmute audio.
        Returns True on success, False on failure.
        """
        backend = self._detect_audio_backend()

        if backend == AudioBackend.PIPEWIRE:
            return await self._set_mute_pipewire(muted)
        elif backend == AudioBackend.PULSEAUDIO:
            return await self._set_mute_pulseaudio(muted)

        logger.warning("Cannot set mute: no audio backend available")
        return False

    async def _set_mute_pipewire(self, muted: bool) -> bool:
        """Set mute state using PipeWire"""
        try:
            state = "1" if muted else "0"
            process = await asyncio.create_subprocess_exec(
                "wpctl",
                "set-mute",
                "@DEFAULT_AUDIO_SINK@",
                state,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=5
            )

            if process.returncode != 0:
                logger.error(f"wpctl set-mute failed: {stderr.decode()}")
                return False

            action = "muted" if muted else "unmuted"
            logger.info(f"Audio {action} via PipeWire")
            return True
        except asyncio.TimeoutError:
            logger.error("wpctl set-mute timeout")
        except Exception as e:
            logger.error(f"Error setting PipeWire mute: {e}")

        return False

    async def _set_mute_pulseaudio(self, muted: bool) -> bool:
        """Set mute state using PulseAudio"""
        try:
            state = "1" if muted else "0"
            process = await asyncio.create_subprocess_exec(
                "pactl",
                "set-sink-mute",
                "@DEFAULT_SINK@",
                state,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=5
            )

            if process.returncode != 0:
                logger.error(f"pactl set-sink-mute failed: {stderr.decode()}")
                return False

            action = "muted" if muted else "unmuted"
            logger.info(f"Audio {action} via PulseAudio")
            return True
        except asyncio.TimeoutError:
            logger.error("pactl set-sink-mute timeout")
        except Exception as e:
            logger.error(f"Error setting PulseAudio mute: {e}")

        return False

    async def toggle_mute(self) -> bool:
        """Toggle mute state"""
        volume_info = await self.get_volume()
        if volume_info is None:
            logger.warning("Cannot toggle mute: unable to get volume info")
            return False

        return await self.set_mute(not volume_info.muted)

    async def shutdown(self) -> bool:
        """
        Initiate system shutdown with sudo.
        Requires user to have sudoers permissions for poweroff.
        Returns True on success, False on failure.
        """
        try:
            logger.info("Initiating system shutdown...")
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "poweroff",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=10
            )

            if process.returncode != 0:
                error_msg = stderr.decode().lower()
                if "permission denied" in error_msg or "not in sudoers" in error_msg:
                    logger.error(
                        "Shutdown denied: insufficient permissions. "
                        "Add user to sudoers or configure passwordless sudo."
                    )
                else:
                    logger.error(f"Shutdown failed: {stderr.decode()}")
                return False

            logger.info("Shutdown command executed successfully")
            return True
        except asyncio.TimeoutError:
            logger.error("Shutdown command timeout (10s)")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        return False

    async def increase_volume(self, step: int = 5) -> bool:
        """Increase volume by step percentage"""
        volume_info = await self.get_volume()
        if volume_info is None:
            return False

        new_level = min(100, volume_info.level + step)
        return await self.set_volume(new_level)

    async def decrease_volume(self, step: int = 5) -> bool:
        """Decrease volume by step percentage"""
        volume_info = await self.get_volume()
        if volume_info is None:
            return False

        new_level = max(0, volume_info.level - step)
        return await self.set_volume(new_level)

    def get_backend_info(self) -> str:
        """Get current audio backend info"""
        backend = self._detect_audio_backend()
        return f"Audio Backend: {backend.value}"

    def is_audio_available(self) -> bool:
        """Check if any audio backend is available"""
        return self._detect_audio_backend() != AudioBackend.NONE
