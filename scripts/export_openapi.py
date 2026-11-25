import json
from pathlib import Path

from module3_host.api.app import create_app

path = Path(__file__).resolve().parents[1] / "docs/software/openapi.json"
path.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(path)
