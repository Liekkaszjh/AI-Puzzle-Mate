"""共享黑板：只由公开问答推导，不含汤底；队友、API 与评测共用同一份状态。

黑板不引入模型调用：确认/排除/维度覆盖都由判题结果与提问文本离线推导，
因此可测试、可回放，也不会把私有事实带进队友的输入。
"""

DIMENSIONS = ("人物", "物品", "时间", "因果", "动机", "反例")

DIMENSION_KEYWORDS = {
    "人物": ("人物", "身份", "职业", "关系", "同行", "邻居", "谁", "身高", "年龄"),
    "物品": ("物品", "按钮", "伞", "设备", "音箱", "录音", "录音机", "声源", "道具", "东西", "装置", "播放器"),
    "时间": ("时间", "八点", "几点", "顺序", "先后", "多久", "每天", "当天", "定时", "一直", "之前", "之后"),
    "因果": ("因果", "为什么", "条件", "导致", "影响", "忘", "没关", "未关", "必要"),
    "动机": ("动机", "故意", "目的", "为了", "刻意", "人为"),
    "反例": ("反例", "排除", "更简单", "其他解释", "否则", "另一种"),
}


# 同一短语命中多个维度时，按这个顺序归到更具体的解释维度：
# “忘关设备”既像物品又像因果，归因果才符合它真正验证的东西。
CLASSIFY_PRIORITY = ("人物", "时间", "因果", "物品", "动机", "反例")


def classify(text):
    """把 target 或问句归到固定维度；识别不出时返回 None，不硬猜。"""
    text = str(text or "")
    for dimension in CLASSIFY_PRIORITY:
        if any(word in text for word in DIMENSION_KEYWORDS[dimension]):
            return dimension
    return None


def new_board():
    return {"asked": 0, "confirmed": [], "excluded": [], "covered": {dimension: 0 for dimension in DIMENSIONS},
            "stalled": 0}


def restore_board(board):
    """兼容老存档：缺字段按空黑板补齐，不迁移数据库结构。"""
    board = board if isinstance(board, dict) else {}
    board.setdefault("asked", 0)
    board.setdefault("confirmed", [])
    board.setdefault("excluded", [])
    board.setdefault("stalled", 0)
    covered = board.get("covered")
    covered = covered if isinstance(covered, dict) else {}
    for dimension in DIMENSIONS:
        covered.setdefault(dimension, 0)
    board["covered"] = covered
    return board


def record_turn(board, turn):
    """一次队友回合之后更新黑板：确认、排除、停滞计数与维度覆盖。"""
    board = restore_board(board)
    board["asked"] += 1
    question = str(turn.get("question", ""))
    dimension = classify(turn.get("target")) or classify(question)
    if dimension:
        board["covered"][dimension] += 1
    verdict = turn.get("verdict", "")
    if verdict == "正确":
        board["confirmed"].append(question)
        board["stalled"] = 0
    elif verdict == "错误":
        board["excluded"].append(question)
        board["stalled"] = 0
    else:
        board["stalled"] += 1
    return board


def open_dimensions(board, profile):
    """该队友负责、且还没有任何问答落在上面的维度，顺序由档案决定。"""
    board = restore_board(board)
    return [dimension for dimension in (getattr(profile, "dimensions", ()) or ())
            if not board["covered"].get(dimension)]


def next_focus(board, profile):
    open_dims = open_dimensions(board, profile)
    return open_dims[0] if open_dims else None


def summary(board, limit=6):
    """给模型看的紧凑黑板：只放最近几条结论和仍待验证的维度。"""
    board = restore_board(board)
    return {"confirmed": board["confirmed"][-limit:], "excluded": board["excluded"][-limit:],
            "open_dimensions": [dimension for dimension in DIMENSIONS if not board["covered"].get(dimension)],
            "asked": board["asked"], "stalled": board["stalled"]}


def view(board):
    """给 API 的公开视图：只给计数与最近一条确认，便于前端显示进度。"""
    board = restore_board(board)
    return {"asked": board["asked"], "confirmed": len(board["confirmed"]), "excluded": len(board["excluded"]),
            "covered": dict(board["covered"]), "stalled": board["stalled"],
            "latest_confirmed": board["confirmed"][-1] if board["confirmed"] else ""}


def hint(board, fact_count, stalled_limit=3):
    """收敛提示：只用公开计数。

    confirmed 记的是“被判定为正确的命题数”，与 key_points 的“关键事实数”不是同一单位，
    所以这里只把 fact_count 当经验阈值，提示玩家可以尝试交卷，不宣称已经还原完整事实。
    """
    board = restore_board(board)
    if fact_count and len(board["confirmed"]) >= fact_count:
        return "已确认 %d 个命题，可以尝试提交完整还原。" % len(board["confirmed"])
    if board["stalled"] >= stalled_limit:
        return "连续 %d 次没有得到肯定回答，换个维度或直接提交还原试试。" % board["stalled"]
    return ""
