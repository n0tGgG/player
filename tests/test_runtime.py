import asyncio
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from controllers import CinemaController, KioskManager
from controllers.player import MpvController
from controllers.scanner import FileScanner


class TestRuntimeRegression(unittest.TestCase):
    def test_scanner_reports_real_file_size(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        media_path = repo_root / "_scanner_test_sample.mp4"

        try:
            media_path.write_bytes(b"cinema")

            scanner = FileScanner()
            results = asyncio.run(
                scanner.scan(paths=[str(repo_root)], use_cache=False)
            )

            self.assertTrue(any(item["path"] == str(media_path) for item in results))
            scanned_item = next(item for item in results if item["path"] == str(media_path))
            self.assertEqual(scanned_item["size"], media_path.stat().st_size)
        finally:
            if media_path.exists():
                media_path.unlink()

    def test_play_file_rejects_missing_local_file(self) -> None:
        controller = CinemaController()
        missing_path = Path(tempfile.gettempdir()) / "definitely-missing-cinema-file.mp4"

        if missing_path.exists():
            missing_path.unlink()

        success, message = asyncio.run(controller.play_file(str(missing_path)))

        self.assertFalse(success)
        self.assertIn("File not found", message)

    def test_mpv_controller_requires_mpv_on_linux(self) -> None:
        with patch.object(MpvController, "_resolve_mpv_binary", return_value=None), patch.object(
            MpvController, "_is_windows_platform", return_value=False
        ):
            with self.assertRaises(RuntimeError) as error:
                MpvController()

        self.assertIn("sudo apt install mpv", str(error.exception))

    def test_mpv_controller_builds_linux_kiosk_command(self) -> None:
        with patch.object(MpvController, "_resolve_mpv_binary", return_value="/usr/bin/mpv"), patch.object(
            MpvController, "_is_windows_platform", return_value=False
        ), patch.dict(os.environ, {"MPV_AUDIO_DEVICE": "alsa/hdmi:CARD=HDMI,DEV=0"}, clear=False):
            controller = MpvController()
            command = controller._build_mpv_command("/media/movie.mp4")

        self.assertEqual(command[0], "/usr/bin/mpv")
        self.assertIn("--fullscreen", command)
        self.assertIn("--hwdec=auto", command)
        self.assertIn("--vo=gpu", command)
        self.assertIn("--no-terminal", command)
        self.assertIn("--audio-device=alsa/hdmi:CARD=HDMI,DEV=0", command)

    def test_kiosk_launch_waits_for_close(self) -> None:
        manager = KioskManager()

        async def fake_launch(url: str) -> None:
            async def close_later() -> None:
                await asyncio.sleep(0.05)
                await manager._on_kiosk_closed()

            asyncio.create_task(close_later())

        manager.kiosk.launch = fake_launch  # type: ignore[assignment]

        started = time.monotonic()
        asyncio.run(manager.launch("https://example.com"))
        elapsed = time.monotonic() - started

        self.assertGreaterEqual(elapsed, 0.05)


if __name__ == "__main__":
    unittest.main()
