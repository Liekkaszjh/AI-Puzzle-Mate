"""启动：python run.py；不需要安装第三方依赖。"""

import argparse
import os
import sys
from pathlib import Path

# 保持项目根目录严格只有四个模块文件夹，不生成额外缓存目录。
sys.dont_write_bytecode = True

from llm import ModelClient, ModelError, load_env
from module4_frontend import create_server


def main():
    load_env(Path(__file__).with_name(".env"))
    parser = argparse.ArgumentParser(description="海龟汤 · 与 AI 队友一起还原真相")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=os.getenv("PORT", "8000"))
    parser.add_argument("--demo", action="store_true", help="使用内置演示题，不调用远程模型")
    parser.add_argument("--check-api", action="store_true", help="检查 DeepSeek 网络与密钥，不产生文本生成费用")
    args = parser.parse_args()
    if args.demo:
        os.environ["DEMO_MODE"] = "true"
    try:
        client = ModelClient()
        if args.check_api:
            available = client.check_connection()
            print("DeepSeek 网络与密钥检查通过；deepseek-flash " + ("可用。" if available else "未出现在模型列表中，请检查账户状态。"))
            return
        server = create_server(client, args.host, args.port)
    except (ModelError, ValueError, OSError) as exc:
        parser.exit(1, "启动失败：%s\n" % exc)
    print("\n海龟汤游戏已启动：http://%s:%d" % (args.host, server.server_port))
    print("运行模式：" + ("演示模式（内置题库 + 简单规则判题）" if client.demo else "大模型模式（" + client.model + "）"))
    print("在浏览器打开上述地址，按 Ctrl+C 停止。\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n游戏已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
