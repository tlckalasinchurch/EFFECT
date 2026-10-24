import sys
import os
import signal
import subprocess
import secrets
import atexit
import threading
import time
import webbrowser
import logging

# Prevent Edge WebView2 GPU DirectComposition green/yellow scanline corruption on Windows
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu --disable-gpu-compositing")
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import uvicorn
import webview

import config
from setup_logging import setup_logging, get_logger

# Setup logging
setup_logging(config.LOG_LEVEL)
logger = get_logger(__name__)

cpp_proc = None


def cleanup_cpp_process():
    global cpp_proc
    if cpp_proc is not None:
        try:
            logger.info("Stopping Native C++ ASIO Engine Host...")
            cpp_proc.terminate()
            cpp_proc.wait(timeout=2.0)
        except Exception:
            try:
                cpp_proc.kill()
            except Exception:
                pass
        cpp_proc = None


atexit.register(cleanup_cpp_process)


def find_cpp_host_binary():
    """Return the first existing native host binary, or None."""
    from engine.cpp_host import find_cpp_host_binary as _find
    return _find(os.path.dirname(os.path.abspath(__file__)))


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
    global cpp_proc
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

    # Try launching the native C++ engine host. Presence of a process is NOT
    # evidence of ASIO UX1 ownership — we query the host for the real backend.
    session_token = secrets.token_hex(16)
    cpp_port = 8765
    cpp_exe = find_cpp_host_binary()
    use_cpp_host = False

    if cpp_exe:
        try:
            logger.info(f"Spawning Native C++ Engine Host: {cpp_exe}")
            cmd = [
                cpp_exe,
                "--port", str(cpp_port),
                "--token", session_token,
                "--backend", "auto",
                "--sr", "48000",
                "--buffer", "128"
            ]
            cpp_proc = subprocess.Popen(cmd)
            time.sleep(0.5)
            if cpp_proc.poll() is None:
                use_cpp_host = True
                logger.info(f"Native C++ Engine Host running (PID: {cpp_proc.pid})")
                from server import engine
                engine.native_cpp_active = True
                engine.native_cpp_asio = False
                try:
                    from engine.cpp_host import snapshot_host
                    info = snapshot_host(cpp_port, session_token, timeout=2.0)
                    engine.cpp_host_info = info
                    engine.native_cpp_asio = bool(info.get("asio_running"))
                    logger.info(
                        "C++ host backend=%s asio_running=%s driver=%s sr=%s buffer=%s roundtrip_ms=%s",
                        info.get("backend"),
                        info.get("asio_running"),
                        info.get("asio_driver"),
                        info.get("sample_rate"),
                        info.get("buffer_size"),
                        info.get("roundtrip_latency_ms"),
                    )
                    if not info.get("asio_running"):
                        logger.warning(
                            "C++ host did not start an ASIO driver (backend=%s). "
                            "Python PortAudio is suppressed to avoid device collision, "
                            "but live Line 6 UX1 I/O is NOT verified.",
                            info.get("backend"),
                        )
                except Exception as probe_err:
                    logger.warning(f"C++ host is running but WebSocket probe failed: {probe_err}")
                    engine.cpp_host_info = {"backend": "probe_failed", "asio_running": False}
            else:
                logger.warning(f"Native C++ Host exited immediately with code {cpp_proc.returncode}")
                cpp_proc = None
        except Exception as e:
            logger.warning(f"Could not spawn Native C++ Host: {e}")
            cpp_proc = None
    else:
        logger.info("Native C++ host binary not found; Python audio engine remains in control")

    # Start FastAPI server in background
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(1.2)  # Wait for server to bind

    url = f"http://{config.WEB_HOST}:{config.WEB_PORT}/?v={int(time.time())}&cpp_token={session_token}&cpp_port={cpp_port}"
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
    cleanup_cpp_process()
    try:
        from server import engine
        engine.stop()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
