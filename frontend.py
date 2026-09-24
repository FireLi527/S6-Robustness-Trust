"""Unified local entry point; reuse existing S6 services and own only new children."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import URLError
import argparse
import json
import subprocess
import sys
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8764
SERVICES = {
    "image": (8766, "data_poisoning", "S6PoisoningLocal/"),
    "prompt": (8765, "prompt_injection", "S6Local/"),
}

def probe(port, expected):
    try:
        with urlopen(f"http://{HOST}:{port}/", timeout=1) as response:
            return "ready" if expected in response.headers.get("Server", "") else "conflict"
    except (OSError, URLError):
        return "offline"

class Handler(BaseHTTPRequestHandler):
    server_version = "S6Portal/1.0"

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        elif path == "/api/status":
            body = json.dumps({key: {"status": probe(port, expected), "url": f"http://{HOST}:{port}/"}
                for key, (port, _, expected) in SERVICES.items()}).encode()
            content_type = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    url = f"http://{HOST}:{PORT}/"
    existing = probe(PORT, "S6Portal/")
    if existing == "ready":
        print("Unified frontend already running: " + url)
        if not args.no_browser:
            webbrowser.open(url)
        return
    if existing == "conflict":
        raise RuntimeError(f"Port {PORT} belongs to another service")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    children, logs = [], []
    try:
        log_dir = ROOT / "results/local_frontend"
        log_dir.mkdir(parents=True, exist_ok=True)
        for key, (port, module, expected) in SERVICES.items():
            status = probe(port, expected)
            if status == "ready":
                print(f"Reusing {module}: {port}")
                continue
            if status == "conflict":
                print(f"Cannot start {module}: port {port} belongs to another service")
                continue
            log = (log_dir / f"{key}.log").open("a", encoding="utf-8")
            logs.append(log)
            child = subprocess.Popen([sys.executable, "-u", str(ROOT / "s6" / module / "app.py"), "--no-browser"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            children.append(child)
        print("Unified frontend: " + url, flush=True)
        print("Close with Ctrl+C. Existing services will be preserved.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for log in logs:
            log.close()

if __name__ == "__main__":
    main()
