"""CZ as a native macOS app: runs the CZ server and shows CZ Studio in its own window.

Started by ~/Applications/CZ.app (see install_cz_app.sh). Closing the window
stops the server.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_DIR)
os.chdir(REPO_DIR)

HOST = "127.0.0.1"


def free_port(start: int = 8080, end: int = 8180) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("Kein freier Port zwischen 8080 und 8179 gefunden.")


def wait_until_ready(url: str, timeout: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def start_server(port: int):
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config("app.asgi:app", host=HOST, port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, name="cz-server", daemon=True)
    thread.start()
    return server, thread


def name_the_app() -> None:
    """Show "CZ" instead of "Python" in the macOS menu bar."""
    try:
        from Foundation import NSBundle

        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = "CZ"
    except Exception:
        pass


def write_url_file(url: str) -> str:
    path = os.path.join(REPO_DIR, "storage", "cz-url")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(url)
    return path


def main() -> int:
    port = free_port()
    base = f"http://{HOST}:{port}"
    url = f"{base}/cz/"
    server, thread = start_server(port)
    print(f"CZ Studio: {url}", flush=True)
    if not wait_until_ready(f"{base}/api/v1/cz/status"):
        print("CZ-Server ist nicht gestartet. Details siehe Log oben.", flush=True)
        server.should_exit = True
        return 1
    url_file = write_url_file(url)

    if os.environ.get("CZ_HEADLESS") == "1":
        # Used by automated checks: keep the server up without a window.
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    else:
        import webview

        name_the_app()
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window(
            "CZ Studio",
            url,
            width=1440,
            height=920,
            min_size=(900, 640),
            background_color="#05070d",
        )
        webview.start()

    server.should_exit = True
    thread.join(timeout=10)
    try:
        os.remove(url_file)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
