"""Create an administrator account without exposing its password in shell history."""
import argparse
import getpass
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from llm import load_env
from module3_host.storage import AuthError, Repository


def main():
    os.chdir(ROOT)
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description="创建问渊管理员账号")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="管理员")
    parser.add_argument("--database", default=os.getenv("DATABASE_PATH", "data/puzzle-mate.sqlite3"))
    args = parser.parse_args()
    email = args.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        parser.error("邮箱格式无效")
    name = args.name.strip()
    if not 1 <= len(name) <= 30:
        parser.error("昵称需为 1 到 30 个字符")
    password = getpass.getpass("管理员密码（至少 8 位）：")
    if not 8 <= len(password) <= 128:
        parser.error("密码需为 8 到 128 个字符")
    if password != getpass.getpass("再次输入密码："):
        parser.error("两次密码不一致")
    try:
        Repository(args.database).create_admin(email, password, name)
    except AuthError as exc:
        parser.error(str(exc))
    print(f"管理员已创建：{email}")


if __name__ == "__main__":
    main()
