import sys
import os
import signal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import threading
import time
import webbrowser
import uvicorn
import webview
import logging

import config
from setup_logging import setup_logging, get_logger

# Setup logging
setup_logging(config.LOG_LEVEL)
logger = get_logger(__name__)


def run_server():
    """Run FastAPI server in background thread."""
    from server import app
    logger.info(f"Starting FastAPI server on {config.WEB_HOST}:{config.WEB_PORT}")
    uvicorn.run(
        app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="warning"
    )


def main():
    """Main entry point for the application."""
    logger.info("=" * 60)
    logger.info("⚡ กดจนหลอนTone - GUITAR RIG & AMP WORKSTATION")
    logger.info("=" * 60)
    logger.info("Starting Audio Engine & Backend Server...")
    
    # Validate configuration
    if not config.validate_config():
        logger.error("Configuration validation failed. Please check config.py")
        sys.exit(1)
    
    # Print configuration
    config.print_config()

    # Start FastAPI server in background
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(1.2)  # Wait for server to bind

    url = f"http://{config.WEB_HOST}:{config.WEB_PORT}"
    logger.info(f"Backend listening at {url}")

    # Launch desktop window with browser fallback
    start_time = time.time()
    opened_in_browser = False
    try:
        logger.info("Opening กดจนหลอนTone Desktop Window...")
        window = webview.create_window(
            title=config.WINDOW_TITLE,
            url=url,
            width=config.WINDOW_WIDTH,
            height=config.WINDOW_HEIGHT,
            min_size=(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT),
            background_color=config.WINDOW_BG_COLOR
        )
        webview.start()
        elapsed = time.time() - start_time
        if elapsed < 2.0:
            logger.warning(f"Native desktop window closed immediately ({elapsed:.2f}s). Falling back to system browser...")
            opened_in_browser = True
    except Exception as e:
        logger.error(f"Native webview window error: {e}")
        opened_in_browser = True

    if opened_in_browser:
        logger.info("Opening workstation in system browser instead...")
        webbrowser.open(url)
        logger.info("=" * 60)
        logger.info(f"⚡ Workstation running at: {url}")
        logger.info("Press Ctrl+C to terminate.")
        logger.info("=" * 60)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")

    logger.info("Stopping Audio Engine and exiting...")
    try:
        from server import engine
        engine.stop()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
