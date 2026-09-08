"""Read-only loopback transport for bundled UI files. No business HTTP routes."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import threading
from urllib.parse import unquote, urlsplit


class AssetServer:
    instances = []

    @classmethod
    def start_server(cls, urls, http_port=None, **_):
        # pywebview computes the URL relative to the exact path it was given.
        # A macOS bundle links Frameworks/desktop-ui to Resources/desktop-ui.
        common = Path(urls[0]).absolute().parent
        root = common.resolve()
        server = cls()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("Host") != f"127.0.0.1:{server.port}":
                    self.send_error(403)
                    return
                relative = unquote(urlsplit(self.path).path).lstrip("/") or "index.html"
                target = (root / relative).resolve()
                if (
                    not target.is_relative_to(root)
                    or not target.is_file()
                    or target.suffix
                    not in (".html", ".js", ".css", ".svg", ".png", ".woff2")
                ):
                    self.send_error(404)
                    return
                data = target.read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    mimetypes.guess_type(target)[0] or "application/octet-stream",
                )
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        server.http = ThreadingHTTPServer(("127.0.0.1", http_port or 0), Handler)
        server.port = server.http.server_port
        server.address = f"http://127.0.0.1:{server.port}/"
        server.root_path = str(root)
        server.common_path = cls.common_path = str(common)
        server.js_api_endpoint = None
        server.running = True
        server.thread = threading.Thread(target=server.http.serve_forever, daemon=True)
        server.thread.start()
        cls.instances.append(server)
        return server.address, str(common), server

    @property
    def is_running(self):
        return self.running

    def close(self):
        if self.running:
            self.http.shutdown()
            self.http.server_close()
            self.thread.join()
            self.running = False
