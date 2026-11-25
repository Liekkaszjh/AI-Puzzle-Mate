"""Explicit, idempotent import of the legacy JSON library into SQLite."""
import argparse
import json
import os
from pathlib import Path

from llm import load_env
from module3_host.storage import Repository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="code/module1_puzzles/generated_puzzles.json")
    args = parser.parse_args()
    load_env(Path.cwd() / ".env")
    puzzles = json.loads(Path(args.path).read_text(encoding="utf-8"))
    if not isinstance(puzzles, list):
        parser.error("题库必须为数组")
    for puzzle in puzzles:
        if not isinstance(puzzle, dict) or not all(isinstance(puzzle.get(k), str) and puzzle[k].strip() for k in ("id", "title", "surface", "bottom")):
            parser.error("题库含无效题目，未执行导入")
        points = puzzle.get("key_points")
        if not isinstance(points, list) or not 2 <= len(points) <= 6 or not all(isinstance(p, str) and p.strip() for p in points):
            parser.error("关键事实无效，未执行导入")
    repo = Repository(os.getenv("DATABASE_PATH", "data/puzzle-mate.sqlite3"))
    with repo.connect() as db:
        before = db.total_changes
        db.executemany("INSERT OR IGNORE INTO puzzles VALUES(?,?,0)", [(p["id"], json.dumps(p, ensure_ascii=False)) for p in puzzles])
        print(f"导入 {db.total_changes-before} 道题；重复 ID 已跳过。演示模式仅使用内置题。")


if __name__ == "__main__":
    main()
