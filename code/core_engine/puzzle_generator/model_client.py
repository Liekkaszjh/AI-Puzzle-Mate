"""聊天补全协议适配器：标准库HTTP、超时、状态码及响应解析。"""

import http.client
import json
import math
import socket
import threading
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from .contracts import Message, PuzzleError, parse_model_object


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


Transport = Callable[[str, dict[str, str], bytes, float], HttpResponse]
HTTP_HINTS = {
    400: "请求参数不被支持，请检查模型名称和接口协议。",
    401: "认证失败，请检查 API Key。",
    402: "账户余额不足，请检查服务账户。",
    403: "访问被拒绝，请检查密钥权限。",
    404: "接口地址或模型不存在，请检查完整聊天补全地址及模型名称。",
    422: "参数校验失败，请检查模型名称和请求格式。",
    429: "请求被限流或额度不足，请稍后重试并检查配额。",
}
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def http_transport(endpoint: str, headers: dict[str, str], body: bytes, timeout: float) -> HttpResponse:
    """直连HTTP(S)，不跟随重定向。建立连接后用计时器中断停滞的响应。"""
    url = urlsplit(endpoint)
    connection_type = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(url.hostname, url.port, timeout=timeout)
    expired = threading.Event()
    active_socket = None

    def abort() -> None:
        expired.set()
        sock = active_socket or connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    timer = threading.Timer(timeout, abort)
    timer.daemon = True
    timer.start()
    try:
        connection.connect()
        active_socket = connection.sock
        if expired.is_set():
            raise TimeoutError
        path = url.path or "/"
        if url.query:
            path += "?" + url.query
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            # 不读取或回显错误正文，避免泄露上游敏感信息。
            return HttpResponse(response.status, b"")
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if expired.is_set():
            raise TimeoutError
        if len(data) > MAX_RESPONSE_BYTES:
            raise PuzzleError("MODEL_OUTPUT_INVALID", "模型响应超过允许大小。")
        return HttpResponse(response.status, data)
    except Exception:
        if expired.is_set():
            raise TimeoutError from None
        raise
    finally:
        timer.cancel()
        connection.close()


class ChatModelClient:
    def __init__(
        self, *, endpoint: str, model: str, api_key: str = "",
        timeout_seconds: float = 30, transport: Transport = http_transport,
    ) -> None:
        try:
            url = urlsplit(endpoint)
            valid_url = (isinstance(endpoint, str) and url.scheme in ("http", "https")
                         and bool(url.hostname) and not url.username and not url.password
                         and not url.fragment)
            url.port  # 同时校验端口是否合法。
        except (TypeError, ValueError, AttributeError):
            valid_url = False
        if not valid_url:
            raise ValueError("模型地址须为不含账户密码或片段的完整HTTP(S)地址。")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("请提供模型名称。")
        if (type(timeout_seconds) not in (float, int) or not math.isfinite(timeout_seconds)
                or timeout_seconds <= 0 or not callable(transport)):
            raise ValueError("超时须为正数秒，transport须可调用。")
        if not isinstance(api_key, str):
            raise ValueError("API Key须为字符串。")
        self.endpoint = endpoint
        self.model = model.strip()
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def complete(self, messages: list[Message]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps({"model": self.model, "messages": messages, "stream": False}, ensure_ascii=False).encode("utf-8")
        try:
            response = self.transport(self.endpoint, headers, body, self.timeout_seconds)
            if not 200 <= response.status < 300:
                hint = HTTP_HINTS.get(response.status, "模型服务异常，请稍后重试。")
                raise PuzzleError("MODEL_UNAVAILABLE", f"模型服务返回 HTTP {response.status}：{hint}")
            try:
                payload = parse_model_object(response.body.decode("utf-8"))
                content = payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, UnicodeDecodeError, PuzzleError):
                raise PuzzleError("MODEL_OUTPUT_INVALID", "模型响应格式错误或缺少文本内容。") from None
            if not isinstance(content, str) or not content.strip():
                raise PuzzleError("MODEL_OUTPUT_INVALID", "模型响应缺少文本内容。")
            return content
        except PuzzleError:
            raise
        except TimeoutError:
            raise PuzzleError("MODEL_TIMEOUT", "模型调用超时，请稍后重试。") from None
        except Exception:
            raise PuzzleError("MODEL_UNAVAILABLE", "模型服务调用失败，请检查服务配置。") from None
