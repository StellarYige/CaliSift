"""Development/verification static server (no business endpoints)."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit
import argparse

ROOT = Path(__file__).resolve().parents[1]


class Static(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = unquote(urlsplit(path).path)
        if path.startswith("/CaliSift/"):
            path = path[len("/CaliSift") :]
        if path.startswith("/__fixtures/"):
            target = (ROOT / path[len("/__fixtures/") :]).resolve()
            allowed = (ROOT / "tests/fixtures", ROOT / "samples")
            if not any(target.is_relative_to(x) for x in allowed):
                return str(ROOT / "web/dist/__not_found__")
            return str(target)
        target = (ROOT / "web/dist" / path.lstrip("/")).resolve()
        return (
            str(target)
            if target.is_relative_to(ROOT / "web/dist")
            else str(ROOT / "web/dist/__not_found__")
        )

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8766)
    a = p.parse_args()
    print(f"Static server http://127.0.0.1:{a.port}/CaliSift/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Static).serve_forever()
