import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mdpeek import cache as cache_module

FIXTURES = Path(__file__).parent / "fixtures"
SMALL_FIXTURES = sorted((FIXTURES / "small").glob("*.md"))


def read_fixture(path: Path) -> str:
    """Read a fixture exactly, keeping its line endings."""
    return path.read_bytes().decode("utf-8")


@pytest.fixture
def fixture_text():
    def load(name: str) -> str:
        return read_fixture(FIXTURES / "small" / name)

    return load


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path_factory, monkeypatch):
    """Never touch the real cache: a private disk cache dir and a clean memory cache."""
    directory = tmp_path_factory.mktemp("mdpeek-cache")
    monkeypatch.setenv("MDPEEK_CACHE_DIR", str(directory))
    cache_module._PROCESS_CACHE.clear()
    return directory


class _Handler(BaseHTTPRequestHandler):
    server: "LocalServer"

    def do_GET(self) -> None:
        self.server.requests.append({"path": self.path, "headers": dict(self.headers)})
        route = self.server.routes.get(self.path)
        if route is None:
            self.send_error(404, "Not Found")
            return
        body, content_type = route
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # keep test output quiet
        pass


class LocalServer(ThreadingHTTPServer):
    routes: dict[str, tuple[bytes, str]]
    requests: list[dict]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def serve(self, path: str, text: str, content_type: str = "text/markdown; charset=utf-8"):
        charset = content_type.partition("charset=")[2] or "utf-8"
        self.routes[path] = (text.encode(charset), content_type)


@pytest.fixture
def http_server():
    server = LocalServer(("127.0.0.1", 0), _Handler)
    server.routes = {}
    server.requests = []
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
