import asyncio
from controllers import CinemaController


def test_controller_initialization():
    """Sanity test: CinemaController imports and initializes without raising.

    This test avoids running heavyweight operations like full scans or launching mpv.
    It ensures the public API is present and get_state() returns an object with expected attributes.
    """
    ctrl = CinemaController()
    state = ctrl.get_state()

    assert hasattr(ctrl, "scan_fast")
    assert hasattr(ctrl, "scan_full")
    assert hasattr(ctrl, "play_file")
    assert hasattr(ctrl, "stream_service")

    # Basic state checks
    assert state.playback_state is not None
    assert hasattr(state, "current_volume")


async def _async_smoke():
    ctrl = CinemaController()
    # ensure async methods are awaitable but do not execute heavy tasks
    # call play_file with a non-existing path and expect a failure tuple
    success, msg = await ctrl.play_file("/nonexistent/file.mp4")
    assert success is False


def test_async_playfile_smoke():
    asyncio.run(_async_smoke())
