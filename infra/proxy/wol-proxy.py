"""
WOL-aware HTTP reverse proxy — listen on localhost, forward to synbox.
On connection failure: triggers WOL via pc_utils, waits for PC, retries.

Stdlib only. One instance per backend.
Env vars: PROXY_LISTEN, PROXY_BACKEND, PC_IP, WOL_MAC
"""
import http.server
import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.request

LISTEN = os.environ["PROXY_LISTEN"]           # e.g. 127.0.0.1:11435
BACKEND = os.environ["PROXY_BACKEND"]          # e.g. http://10.10.10.5:11434
PC_IP = os.environ["PC_IP"]                    # e.g. 10.10.10.5
WOL_MAC = os.environ["WOL_MAC"]               # e.g. XX:XX:XX:XX:XX:XX
MAX_BODY = int(os.environ.get("PROXY_MAX_BODY", 10_485_760))  # 10 MB
CONNECT_RETRIES = int(os.environ.get("PROXY_CONNECT_RETRIES", 3))
RETRY_GRACE = int(os.environ.get("PROXY_RETRY_GRACE", 5))
PC_BOOT_TIMEOUT = int(os.environ.get("PC_BOOT_TIMEOUT", 120))

listen_host, listen_port = LISTEN.rsplit(":", 1)
listen_port = int(listen_port)

log = logging.getLogger("wol-proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [wol-proxy] %(message)s",
                    datefmt="%H:%M:%S")

# ── WOL helper (inlined from pc_utils to avoid extra deploy) ──────────

def _trigger_wol(mac: str) -> None:
    """Write MAC to trigger file watched by wol-server.py."""
    try:
        with open("/tmp/wol_trigger", "w") as f:
            f.write(mac + "\n")
        log.info("WOL trigger written: %s", mac)
    except Exception as exc:
        log.warning("Failed to write WOL trigger: %s", exc)


def _pc_is_up(host: str, port: int, timeout: int = 3) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


def wake_and_wait(timeout: int = PC_BOOT_TIMEOUT) -> bool:
    """Trigger WOL, then block until PC is reachable or timeout expires."""
    log.info("Triggering WOL for %s (mac=%s)...", PC_IP, WOL_MAC)
    _trigger_wol(WOL_MAC)

    deadline = time.time() + timeout
    # PC might already be on — check immediately
    while time.time() < deadline:
        if _pc_is_up(PC_IP, 11434, timeout=2) or _pc_is_up(PC_IP, 8000, timeout=2):
            elapsed = timeout - (deadline - time.time())
            log.info("PC %s is now reachable (waited %.0fs)", PC_IP, elapsed)
            return True
        time.sleep(1)

    log.warning("PC %s did not come online within %ds", PC_IP, timeout)
    return False


# ── Request forwarding ────────────────────────────────────────────────

def _copy_headers(src, skip_keys=("host", "content-length", "transfer-encoding")):
    """Extract headers to forward, skipping hop-by-hop headers."""
    result = {}
    for k, v in src.items():
        if k.lower() not in skip_keys:
            result[k] = v
    return result


def forward(method: str, path: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    """Forward a request to BACKEND. Returns (status, headers, body)."""
    url = f"{BACKEND.rstrip('/')}/{path.lstrip('/')}"
    req_headers = _copy_headers(headers)

    # Avoid chunked transfer — read body fully
    if body is None:
        body = b""

    data = body
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp_headers = _copy_headers(dict(resp.headers),
                                         skip_keys=("content-encoding", "transfer-encoding"))
            resp_body = resp.read()
            return resp.status, resp_headers, resp_body
    except urllib.error.HTTPError as e:
        # HTTP errors (4xx/5xx) — pass through, don't trigger WOL
        resp_headers = _copy_headers(dict(e.headers),
                                     skip_keys=("content-encoding", "transfer-encoding"))
        return e.code, resp_headers, e.read()
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError,
            socket.timeout, OSError) as e:
        raise ConnectionError(f"Backend unreachable: {e}") from e


def do_request(method: str, path: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    """Forward with WOL retry on connection failure."""
    last_err = None
    for attempt in range(1 + CONNECT_RETRIES):
        try:
            return forward(method, path, headers, body)
        except ConnectionError as e:
            last_err = e
            if attempt == CONNECT_RETRIES:
                break
            log.warning("Attempt %d/%d: %s — waking PC...", attempt + 1, CONNECT_RETRIES + 1, e)
            if not wake_and_wait():
                break
            log.info("PC awake, retrying in %ds...", RETRY_GRACE)
            time.sleep(RETRY_GRACE)

    return 502, {"Content-Type": "text/plain"}, f"Backend unreachable: {last_err}".encode()


# ── HTTP server ───────────────────────────────────────────────────────

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Handle all HTTP methods by forwarding to BACKEND."""

    def _handle(self):
        # Read body
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY:
            self.send_response(413)
            self.end_headers()
            self.wfile.write(b"Request body too large")
            return
        body = self.rfile.read(content_len) if content_len > 0 else None

        status, resp_headers, resp_body = do_request(
            self.command, self.path, dict(self.headers), body
        )

        self.send_response(status)
        for k, v in resp_headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp_body)

    # Dispatch all HTTP methods through the same handler
    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_HEAD = _handle
    do_OPTIONS = _handle

    def log_message(self, fmt, *args):
        log.info("%s %s → %d", self.command, self.path,
                 getattr(self, '_last_status', 0) or 0)


if __name__ == "__main__":
    log.info("WOL proxy starting: %s → %s (PC=%s)", LISTEN, BACKEND, PC_IP)
    srv = http.server.HTTPServer((listen_host, listen_port), ProxyHandler)
    srv.serve_forever()
