"""四个模块共用的 DeepSeek 单次调用，仅依赖 Python 标准库。"""

import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class ModelError(Exception):
    """可安全展示给用户的模型错误。"""


JSON_PROTOCOL = """输出协议优先：只输出任务要求的单个标准 JSON 对象，不得输出推理、解释、Markdown 或 XML。
使用双引号并转义字符串中的双引号和换行；不使用注释、尾逗号、NaN、Infinity。输出前在内部检查括号闭合与必填字段。"""


def parse_json_object(content):
    def reject_constant(value):
        raise ValueError("不允许非JSON常量")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("不允许重复字段")
            result[key] = value
        return result

    if not isinstance(content, str) or not content.strip():
        raise ModelError("DeepSeek 未返回 JSON 正文，可能只生成了思考内容；请重试当前操作。")
    content = content.strip()
    # 兼容完整代码围栏，不从混杂文字中猜取JSON或修补残缺答案。
    if content.startswith("```"):
        lines = content.splitlines()
        if len(lines) >= 3 and lines[0].strip() in ("```", "```json", "```JSON") and lines[-1].strip() == "```":
            content = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(content, parse_constant=reject_constant, object_pairs_hook=unique_keys)
        if not isinstance(value, dict):
            raise ValueError("需要对象")
        return value
    except (ValueError, TypeError) as exc:
        raise ModelError("DeepSeek 正文不是合法 JSON 对象，本次结果未写入游戏；请重试当前操作。") from exc


def connection_error(exc, timeout):
    """仅输出错误分类，不回显可能含凭据的底层异常文本。"""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return ModelError("DeepSeek 请求超过 %s 秒未完成。可稍后重试，或在 .env 中增大 DEEPSEEK_TIMEOUT（最多180秒）并重启服务。" % timeout)
    if isinstance(reason, (ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError)):
        return ModelError("连接 DeepSeek 被拒绝或中断。请检查 HTTP_PROXY / HTTPS_PROXY 是否指向失效代理，并在正常网络终端重新启动 python run.py。")
    if isinstance(reason, socket.gaierror):
        return ModelError("无法解析 api.deepseek.com，请检查 DNS、网络连接及代理配置。")
    if isinstance(reason, ssl.SSLError):
        return ModelError("DeepSeek HTTPS 证书或 TLS 连接失败，请检查系统时间、证书和代理配置。")
    return ModelError("DeepSeek 网络连接失败。请运行 python run.py --check-api 检查连接与密钥，并确认代理配置有效。")


def load_env(path):
    """读取简单 KEY=VALUE 配置；进程环境变量优先。"""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


class ModelClient:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.demo = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes") or not self.api_key
        self.base_url = "https://api.deepseek.com/v1"
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip()
        try:
            self.timeout = float(os.getenv("DEEPSEEK_TIMEOUT", "60"))
        except ValueError as exc:
            raise ValueError("DEEPSEEK_TIMEOUT 必须是秒数") from exc
        if not 1 <= self.timeout <= 180:
            raise ValueError("DEEPSEEK_TIMEOUT 必须在 1 到 180 秒之间")
        if not self.demo:
            url = urllib.parse.urlsplit(self.base_url)
            if url.scheme not in ("http", "https") or not url.netloc or url.query or url.fragment or url.username:
                raise ValueError("DeepSeek API 地址无效")
            if not self.model:
                raise ValueError("DeepSeek 模型未配置")

    def check_connection(self):
        """仅请求模型列表，验证网络与鉴权，不执行收费文本生成。"""
        if not self.api_key:
            raise ModelError("请先在 .env 中填写 DEEPSEEK_API_KEY")
        request = urllib.request.Request(self.base_url + "/models", headers={"Authorization": "Bearer " + self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout, 20)) as response:
                result = json.loads(response.read(100000))
            if not isinstance(result, dict) or not isinstance(result.get("data"), list):
                raise ModelError("DeepSeek 模型列表响应无效")
            return any(isinstance(item, dict) and item.get("id") == self.model for item in result["data"])
        except urllib.error.HTTPError as exc:
            labels = {401: "API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY", 403: "接口拒绝访问", 429: "请求过于频繁，请稍后再试"}
            raise ModelError("DeepSeek 连接检查失败：" + labels.get(exc.code, "HTTP " + str(exc.code))) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise connection_error(exc, min(self.timeout, 20)) from exc
        except (ValueError, TypeError) as exc:
            raise ModelError("DeepSeek 模型列表响应无法解析") from exc

    def complete_json(self, system, payload, max_tokens=1200):
        """只请求一次，不附加重试、工具调用或隐藏的第二轮调用。"""
        if self.demo:
            raise ModelError("演示模式不能调用远程模型")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\n\n" + JSON_PROTOCOL},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "max_tokens": max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ModelError("模型返回内容过大，请换一个模型后重试")
            result = json.loads(raw)
            choice = result["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ModelError("DeepSeek 输出达到长度上限被截断，未采纳残缺答案；请重试当前操作。")
            if choice.get("finish_reason") == "content_filter":
                raise ModelError("DeepSeek 未生成当前内容，请更换故事主题或问题。")
            return parse_json_object(choice["message"].get("content"))
        except urllib.error.HTTPError as exc:
            labels = {400: "当前 DeepSeek 模型不接受请求参数，请检查模型对 JSON 输出和 thinking 参数的支持", 401: "API Key 无效", 402: "DeepSeek 账户余额不足，请在开放平台充值后重试", 403: "接口拒绝访问", 404: "接口地址或模型名称有误", 429: "请求过于频繁或额度不足", 503: "DeepSeek 服务繁忙，请稍后重试"}
            raise ModelError("模型调用失败：" + labels.get(exc.code, "服务商 HTTP " + str(exc.code))) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise connection_error(exc, self.timeout) from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelError("DeepSeek 响应缺少 choices/message 等协议字段，或响应体不是有效 JSON；本次结果未写入游戏。") from exc


def require_text(data, key, max_length):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
        raise ModelError("模型返回的 %s 为空或长度不符合约定" % key)
    return value.strip()
