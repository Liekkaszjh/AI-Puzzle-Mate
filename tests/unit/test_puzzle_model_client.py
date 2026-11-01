import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import puzzle_fixtures  # 配置源码导入路径
from puzzle_generator import ChatModelClient, PuzzleError
from puzzle_generator.model_client import HttpResponse


class ModelClientTests(unittest.TestCase):
    def client(self, transport, **kwargs):
        return ChatModelClient(endpoint="https://model.example/v1/chat/completions", model="test-model",
                               api_key="test-key", transport=transport, **kwargs)

    def test_request_and_response(self):
        messages = [{"role": "user", "content": "测试"}]

        def transport(endpoint, headers, body, timeout):
            self.assertEqual(endpoint, "https://model.example/v1/chat/completions")
            self.assertEqual(headers["Authorization"], "Bearer test-key")
            self.assertEqual(timeout, 30)
            self.assertEqual(json.loads(body), {"model": "test-model", "messages": messages, "stream": False})
            return HttpResponse(200, b'{"choices":[{"message":{"content":"{}"}}]}')

        self.assertEqual(self.client(transport).complete(messages), "{}")

    def test_http_status_diagnostics(self):
        for status, hint in ((401, "API Key"), (402, "余额"), (404, "地址"), (429, "限流"), (503, "异常")):
            with self.subTest(status=status):
                model = self.client(lambda *args: HttpResponse(status, b'secret upstream response'))
                with self.assertRaises(PuzzleError) as caught:
                    model.complete([])
                self.assertEqual(caught.exception.code, "MODEL_UNAVAILABLE")
                self.assertIn(f"HTTP {status}", str(caught.exception))
                self.assertIn(hint, str(caught.exception))
                self.assertNotIn("secret", str(caught.exception))

    def test_network_error_and_timeout_are_sanitized(self):
        for error, code in ((OSError("secret"), "MODEL_UNAVAILABLE"), (TimeoutError("secret"), "MODEL_TIMEOUT")):
            def transport(*args):
                raise error
            with self.assertRaises(PuzzleError) as caught:
                self.client(transport).complete([])
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("secret", str(caught.exception))

    def test_malformed_or_empty_response(self):
        bodies = [b'not JSON', b'[]', b'{}', b'{"choices":[]}',
                  b'{"choices":[{"message":{"content":" "}}]}', b'\xff']
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaises(PuzzleError) as caught:
                    self.client(lambda *args: HttpResponse(200, body)).complete([])
                self.assertEqual(caught.exception.code, "MODEL_OUTPUT_INVALID")

    def test_invalid_client_configuration(self):
        for endpoint in (None, "", "ftp://model.example", "https://user:pass@model.example", "https://host:bad", "https://host/#token"):
            with self.assertRaises(ValueError):
                ChatModelClient(endpoint=endpoint, model="test")
        for timeout in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                self.client(lambda *args: None, timeout_seconds=timeout)


class LocalTransportTests(unittest.TestCase):
    """仅连接回环地址，实际验证HTTP传输和停滞响应，无外部API费用。"""

    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    if self.path == "/redirect":
                        self.send_response(302)
                        self.send_header("Location", "/ok")
                        self.end_headers()
                        return
                    if self.path == "/headers":
                        time.sleep(0.5)
                    body = b'{"choices":[{"message":{"content":"{}"}}]}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if self.path == "/body":
                        time.sleep(0.5)
                    if self.path == "/trickle":
                        for byte in body:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.02)
                    else:
                        self.wfile.write(body)
                except (OSError, ConnectionError):
                    pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def client(self, path, timeout=1):
        return ChatModelClient(endpoint=f"http://127.0.0.1:{self.server.server_port}{path}",
                               model="test", timeout_seconds=timeout)

    def test_real_transport_returns_content(self):
        self.assertEqual(self.client("/ok").complete([]), "{}")

    def test_redirect_is_not_followed(self):
        with self.assertRaises(PuzzleError) as caught:
            self.client("/redirect").complete([])
        self.assertIn("302", str(caught.exception))

    def test_header_body_and_slow_trickle_timeout(self):
        for path in ("/headers", "/body", "/trickle"):
            with self.subTest(path=path):
                started = time.monotonic()
                with self.assertRaises(PuzzleError) as caught:
                    self.client(path, timeout=0.1).complete([])
                self.assertEqual(caught.exception.code, "MODEL_TIMEOUT")
                self.assertLess(time.monotonic() - started, 0.45)


if __name__ == "__main__":
    unittest.main()
