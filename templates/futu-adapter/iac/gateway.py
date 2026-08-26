"""
FUTU 网关代理 — 零依赖纯标准库 HTTP 反向代理。

设计约束：
- partner SG 出站仅放行 FUTU ECN CIDR:port，TCP 443 被阻断，无法 pip install
- 因此只能用 Python 标准库（http.server / http.client / threading）
- 多 upstream 支持：UPSTREAM_URL 逗号分隔，随机 shuffle 后逐个尝试，连接级故障自动 fallback
- HTTP 应用层错误（4xx/5xx）不 fallback（不重试业务错误）
- /healthz 直接返回 200，供 ECS 或运维探测用
"""

import http.client
import http.server
import logging
import os
import random
import threading
import urllib.parse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

LISTEN_ADDR = os.environ.get("LISTEN_ADDR", "0.0.0.0:8443")
UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))


def parse_upstreams(raw: str) -> list[tuple[str, int, str]]:
    """解析逗号分隔的 upstream URL 列表，返回 (host, port, scheme) 元组列表。"""
    result = []
    for url in raw.split(","):
        url = url.strip()
        if not url:
            continue
        parsed = urllib.parse.urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        result.append((parsed.hostname, port, parsed.scheme))
    return result


UPSTREAMS = parse_upstreams(UPSTREAM_URL)


class GatewayHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)

    def do_healthz(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok\n")

    def _forward(self, method: str):
        if self.path == "/healthz":
            self.do_healthz()
            return

        body_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(body_len) if body_len else b""

        candidates = UPSTREAMS[:]
        random.shuffle(candidates)

        for host, port, scheme in candidates:
            try:
                conn = (
                    http.client.HTTPSConnection(host, port, timeout=REQUEST_TIMEOUT)
                    if scheme == "https"
                    else http.client.HTTPConnection(host, port, timeout=REQUEST_TIMEOUT)
                )
                headers = {k: v for k, v in self.headers.items()}
                headers["Host"] = f"{host}:{port}"
                conn.request(method, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                resp_body = resp.read()

                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp_body)
                return
            except OSError as e:
                # 连接级错误：fallback 到下一个 upstream
                log.warning("upstream %s:%d failed: %s — trying next", host, port, e)
                continue

        self.send_error(502, "All upstreams unreachable")

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")

    def do_PUT(self):
        self._forward("PUT")

    def do_DELETE(self):
        self._forward("DELETE")

    def do_PATCH(self):
        self._forward("PATCH")

    def do_HEAD(self):
        self._forward("HEAD")


def main():
    if not UPSTREAMS:
        raise RuntimeError("UPSTREAM_URL is empty or invalid")

    host, port_str = LISTEN_ADDR.rsplit(":", 1)
    port = int(port_str)
    server = http.server.ThreadingHTTPServer((host, port), GatewayHandler)
    log.info("gateway listening on %s, upstreams: %s", LISTEN_ADDR, UPSTREAM_URL)
    server.serve_forever()


if __name__ == "__main__":
    main()
