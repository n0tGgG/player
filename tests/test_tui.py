import unittest
from tui import CinemaTUI
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
