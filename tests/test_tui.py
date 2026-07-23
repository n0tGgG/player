import asyncio
import unittest
from unittest.mock import patch

from tui import CinemaTUI
from textual.app import App, ComposeResult
from textual.widgets import DirectoryTree, OptionList

from tui.components import TopBar, Sidebar, MainContent, PlayerBar
from tui.styles import ASCII_ART, APP_CSS


class TestCinemaTUI(unittest.TestCase):
    """Test suite for CinemaTUI module structure and initialization."""

    def test_tui_imports(self):
        """Test that CinemaTUI can be imported from package."""
        self.assertIsNotNone(CinemaTUI)
        self.assertTrue(len(ASCII_ART) > 0)
        self.assertTrue(len(APP_CSS) > 0)

    def test_components_instantiation(self):
        """Test that UI layout components instantiate cleanly."""
        top_bar = TopBar()
        sidebar = Sidebar()
        main_content = MainContent()
        player_bar = PlayerBar()

        self.assertEqual(top_bar.id, "top-bar")
        self.assertEqual(sidebar.id, "sidebar")
        self.assertEqual(main_content.id, "main-content")
        self.assertEqual(player_bar.id, "player-bar")

    def test_sidebar_supports_drive_selection(self):
        """Test that the sidebar exposes one drive selector and one tree."""
        class SidebarHarness(App):
            def __init__(self, sidebar: Sidebar) -> None:
                super().__init__()
                self.sidebar = sidebar

            def compose(self) -> ComposeResult:
                yield self.sidebar

        async def exercise() -> None:
            with patch("tui.components.discover_media_roots", return_value=[
                "/home/gabri",
                "/",
                "/mnt/usb1",
                "/mnt/usb2",
            ]):
                sidebar = Sidebar()
                app = SidebarHarness(sidebar)

                async with app.run_test(size=(80, 24)):
                    drive_selectors = list(sidebar.query(OptionList))
                    trees = list(sidebar.query(DirectoryTree))

                    self.assertEqual(sidebar.drive_roots, [
                        "/home/gabri",
                        "/",
                        "/mnt/usb1",
                        "/mnt/usb2",
                    ])
                    self.assertEqual(len(drive_selectors), 2)
                    self.assertEqual(len(trees), 1)
                    self.assertEqual(sidebar.current_drive, "/home/gabri")
                    self.assertEqual(
                        str(sidebar.source_tree.path).replace("\\", "/"),
                        "/home/gabri",
                    )
                    self.assertEqual(sidebar.drive_selector.highlighted, 0)

                    sidebar.set_drive_root("/mnt/usb2")
                    await asyncio.sleep(0.05)

                    self.assertEqual(
                        str(sidebar.source_tree.path).replace("\\", "/"),
                        "/mnt/usb2",
                    )
                    self.assertIn("usb2", str(sidebar.source_tree.border_title))

        asyncio.run(exercise())

    def test_app_initialization(self):
        """Test that CinemaTUI app initializes without missing callbacks or errors."""
        app = CinemaTUI()
        self.assertIsNotNone(app.controller)
        self.assertTrue(hasattr(app, "_on_kiosk_close"))
        self.assertTrue(hasattr(app, "_on_playback_finish"))
        self.assertTrue(hasattr(app, "_on_error"))
        self.assertTrue(hasattr(app, "_on_volume_change"))

    def test_callbacks_execution(self):
        """Test event callbacks do not crash when invoked."""
        app = CinemaTUI()
        # Test event callback methods
        app._on_playback_finish()
        app._on_error("Test error")
        app._on_volume_change(50)
        app._on_kiosk_close()


if __name__ == "__main__":
    unittest.main()
