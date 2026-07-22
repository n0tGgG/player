
import asyncio
import logging
from tui import CinemaTUI
from controllers import CinemaController


import os
import tempfile

def setup_logging() -> None:
    """Configure application-wide logging."""
    log_file = os.path.join(tempfile.gettempdir(), "cinema.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            # StreamHandler is removed to prevent it from corrupting the TUI.
            # Logs will be intercepted by the TUI and displayed in the RichLog.
        ]
    )


if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting CinemaTUI application")
    
    try:
        app = CinemaTUI()
        app.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        logger.info("CinemaTUI application closed")