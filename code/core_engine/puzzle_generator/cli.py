"""真实API测试入口，显式执行才会调用模型并保存结果。"""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from .config import ModelSettings, load_env_file
from .contracts import PuzzleError
from .model_client import ChatModelClient
from .service import PuzzleService


def save_report(result: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4()}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return path.resolve()


def print_progress(event: dict) -> None:
    attempt = f"第{event['attempt']}/{event['max_attempts']}轮"
    if event["stage"] == "generating":
        print(f"{attempt}：正在生成题目……", flush=True)
    elif event["stage"] == "checking":
        print(f"{attempt}：正在检查题目……", flush=True)
    elif event["stage"] == "rejected":
        print(f"{attempt}：未通过检查。", flush=True)
        for issue in event["issues"]:
            print(f"- {issue}", flush=True)
        if event["will_retry"]:
            print("将携带问题原因重新生成。", flush=True)
    elif event["stage"] == "accepted":
        print(f"{attempt}：检查通过。", flush=True)


def main(
    argv: list[str] | None = None, *, default_env_file: Path | None = None,
    default_output_dir: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="生成并审核一份真实海龟汤题目")
    parser.add_argument("theme", nargs="?", default="校园")
    parser.add_argument("difficulty", nargs="?", choices=("简单", "普通", "困难"), default="普通")
    parser.add_argument("--env-file", type=Path, help="配置文件，现有环境变量优先")
    parser.add_argument("--max-retries", type=int, choices=range(4), default=3, help="重新生成次数，默认3（最多生成4题）")
    parser.add_argument("--output-dir", type=Path, default=default_output_dir or Path("tests/integration/output"))
    args = parser.parse_args(argv)
    try:
        env_file = args.env_file or default_env_file or Path(".env")
        if args.env_file is not None or env_file.exists():
            load_env_file(env_file)
        settings = ModelSettings.from_env()
        model = ChatModelClient(
            endpoint=settings.endpoint, model=settings.model, api_key=settings.api_key,
            timeout_seconds=settings.timeout_seconds,
        )
    except PuzzleError as error:
        print(f"配置失败：{error.code}，{error}")
        return 1
    except ValueError:
        print("配置失败：请检查模型地址、名称和超时时间。")
        return 1

    print("开始真实 API 测试：生成完整题目，并执行独立审核。", flush=True)
    print(f"自动重新生成上限：{args.max_retries}次；最多生成{args.max_retries + 1}题。", flush=True)
    result = PuzzleService(model, max_retries=args.max_retries).generate(
        {"theme": args.theme, "difficulty": args.difficulty}, on_progress=print_progress,
    )
    timing = result["timings"]
    print(f"耗时：{timing['total_ms'] / 1000:.1f} 秒；生成次数：{result['attempts']}")
    print(f"生成耗时：{timing['generation_ms'] / 1000:.1f} 秒；检查耗时：{timing['review_ms'] / 1000:.1f} 秒")
    try:
        path = save_report(result, args.output_dir)
    except OSError:
        print("结果保存失败，请检查输出目录的写入权限。")
        return 1
    print(f"完整结果已保存：{path}")
    if not result["success"]:
        error = result["error"]
        print(f"测试失败：{error['code']}，{error['message']}")
        for issue in error.get("issues", []):
            print(f"- {issue}")
        return 1
    print("测试成功：题目通过结构检查及全部语义审核。")
    print(json.dumps(result["puzzle"], ensure_ascii=False, indent=2))
    print("审核结果：", json.dumps(result["review"]["checks"], ensure_ascii=False))
    print("审核依据：", json.dumps(result["review"]["reasons"], ensure_ascii=False, indent=2))
    return 0
