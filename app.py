import os
import sys
import time
import threading
import webbrowser
from pathlib import Path

# Add directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.index import app

if __name__ == "__main__":
    import uvicorn

    port = 8000
    host = "127.0.0.1"
    url = f"http://{host}:{port}"
    print(f"==================================================")
    print(f"  YOUTUBE ULTIMATE DOWNLOADER - FULL RESOLUTION")
    print(f"  Mở trình duyệt tại: {url}")
    print(f"==================================================")

    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host=host, port=port, reload=False)
