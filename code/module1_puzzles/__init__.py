"""模块1：出题，输出汤面和汤底。"""

import copy
import random
import json
import threading
import uuid
from pathlib import Path

from llm import ModelError, require_text
from .prompts import SYSTEM_PROMPT


# 演示判题规则随题保存于服务端，不会被传给队友或浏览器。
DEMO_PUZZLES = [
    {
        "id": "elevator", "title": "没下雨的日子",
        "surface": "一个人住在二十楼。每天出门，他都会乘电梯直接到一楼。回家时，下雨天他能直接乘电梯到二十楼；没下雨又没人同行时，他却只到十五楼，再走楼梯回家。电梯一直正常，他也并不想锻炼。这是为什么？",
        "bottom": "这个人身材矮小，能按到一楼和十五楼的按钮，却够不到二十楼的按钮。晴天独自回家时，他只能先到能按到的十五楼，再爬五层楼梯。下雨天他带着雨伞，可以用伞尖按到二十楼；有人同行时，也可以请别人帮忙按按钮。",
        "key_points": ["他个子矮，够不到二十楼按钮", "雨天用伞按按钮", "晴天独自先到十五楼再走楼梯"],
        "rules": [
            {"keys": ["坏", "故障", "停电", "维修"], "answer": "不是"},
            {"keys": ["锻炼", "健身", "省电", "收费", "害怕", "怕水"], "answer": "不是"},
            {"keys": ["按钮", "身高", "个子", "矮", "够不到", "按不到", "雨伞", "带伞", "伞尖", "帮忙", "同行"], "answer": "是"},
            {"keys": ["十五", "15", "楼梯", "二十", "20", "下雨", "晴天"], "answer": "是"},
        ],
        "fact_rules": [
            [["矮", "身高不够", "个子小"], ["够不到", "按不到", "无法按"], ["按钮"]],
            [["伞"], ["按", "够", "戳"]],
            [["十五", "15"], ["楼梯", "走", "爬"]],
        ],
    },
    {
        "id": "recording", "title": "准时的声音",
        "surface": "小林每天晚上八点都会听见独居的邻居在屋里练钢琴。某天，邻居出差去了外地，小林却又在八点听见一模一样的琴声。他确认屋里没有任何人，也没有会自动弹奏的钢琴。小林得知原因后，一点也不惊讶。为什么？",
        "bottom": "小林听到的其实一直是邻居设置的定时音箱播放的钢琴录音。邻居常在白天练习，将自己的演奏录下来，晚上八点定时播放，方便自己回听。出差前他忘了关闭定时播放，所以空屋里仍准时响起同一段琴声，并没有人在现场弹奏。",
        "key_points": ["琴声来自录音", "音箱设置了晚上八点定时播放", "邻居出差忘了关闭"],
        "rules": [
            {"keys": ["鬼", "灵异", "闯入", "躲", "自动钢琴", "自动弹", "现场弹", "有人弹", "有人在"], "answer": "不是"},
            {"keys": ["录音", "录下", "播放", "音箱", "音响", "定时", "忘", "白天", "回听"], "answer": "是"},
            {"keys": ["出差", "外地", "八点", "8点", "独居"], "answer": "是"},
        ],
        "fact_rules": [[["录音", "录下", "录制"]], [["定时", "自动播放"], ["八点", "8点"]], [["忘", "没关", "未关"], ["关闭", "没关", "未关", "关掉"]]],
    },
]


LIBRARY_PATH = Path(__file__).with_name("generated_puzzles.json")
LIBRARY_LOCK = threading.Lock()


def _read_saved():
    if not LIBRARY_PATH.exists():
        return []
    try:
        items = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            raise ValueError()
        for item in items:
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("id", "title", "surface", "bottom")):
                raise ValueError()
            if not isinstance(item.get("key_points"), list) or not 2 <= len(item["key_points"]) <= 6 or not all(isinstance(p, str) and p.strip() for p in item["key_points"]):
                raise ValueError()
        return items
    except (ValueError, OSError) as exc:
        from llm import ModelError
        raise ModelError("已生成题库无法读取，请检查 module1_puzzles/generated_puzzles.json") from exc


def choose_existing(client, previous_id=None):
    """随机已有题：不调用模型。离线只抽取带演示判题规则的内置题。"""
    with LIBRARY_LOCK:
        library = list(DEMO_PUZZLES) + ([] if client.demo else _read_saved())
    candidates = [p for p in library if p["id"] != previous_id] or library
    return copy.deepcopy(random.choice(candidates))


def save_generated(puzzle):
    from llm import ModelError
    try:
        with LIBRARY_LOCK:
            library = _read_saved()
            library.append(puzzle)
            temporary = LIBRARY_PATH.with_suffix(".tmp")
            temporary.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(LIBRARY_PATH)
    except OSError as exc:
        raise ModelError("新题保存失败，请检查题库目录的写入权限") from exc


def generate_puzzle(client, theme="", previous_id=None):
    """输入题材；输出 title、surface、bottom、key_points。"""
    if client.demo:
        candidates = [p for p in DEMO_PUZZLES if p["id"] != previous_id] or DEMO_PUZZLES
        return copy.deepcopy(random.choice(candidates))
    data = client.complete_json(SYSTEM_PROMPT, {"theme": theme or "日常生活，适合初学者"}, max_tokens=2400)
    return validate_generated(data)


def validate_generated(data):
    """结构约束落实为本地校验，不替模型编造或补全故事。"""
    if not isinstance(data, dict) or set(data) != {"title", "surface", "bottom", "key_points"}:
        raise ModelError("出题结果必须且只能包含 title、surface、bottom、key_points")
    points = data.get("key_points")
    if not isinstance(points, list) or not 3 <= len(points) <= 6:
        raise ModelError("出题模块必须返回3到6条独立关键事实")
    title = require_text(data, "title", 12)
    surface = require_text(data, "surface", 500)
    if len("".join(surface.split())) > 100 or len(surface.splitlines()) != 1:
        raise ModelError("新题汤面必须是单段且不超过100字符，当前结果未通过校验")
    normalized = [require_text({"point": p}, "point", 120) for p in points]
    if len(set("".join(p.split()).rstrip("。.!！") for p in normalized)) != len(normalized):
        raise ModelError("新题关键事实存在重复，当前结果未通过校验")
    return {
        "id": "generated-" + uuid.uuid4().hex,
        "title": title,
        "surface": surface,
        "bottom": require_text(data, "bottom", 1200),
        "key_points": normalized,
    }
