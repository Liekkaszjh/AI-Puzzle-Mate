"""从任意目录启动 FastAPI；前端位于 code/module4_frontend。"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
from llm import ModelClient, ModelError, load_env


def main():
    os.chdir(ROOT)
    load_env(ROOT / ".env")
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
            print("DeepSeek 网络与密钥检查通过；" + client.model + " " + ("可用。" if available else "未出现在模型列表中，请检查账户状态。"))
            return
        import uvicorn
        from module3_host.api.app import create_app
        app = create_app()
    except (ModelError, ValueError, OSError) as exc:
        parser.exit(1, "启动失败：%s\n" % exc)
    print("\n后端 API：http://%s:%d/docs" % (args.host, args.port))
    print("运行模式：" + ("演示模式（内置题库 + 简单规则判题）" if client.demo else "大模型模式（" + client.model + "）"))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
