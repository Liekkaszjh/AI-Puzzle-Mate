# ADR-0002：共享黑板与队友维度分工

- 状态：已采纳
- 日期：2026-11-26
- 范围：`code/module2_teammate/board.py`、`code/module2_teammate/__init__.py`、`code/module3_host/api/service.py`、前端 `GameTable.vue`
- 前置：[ADR-0001](ADR-0001-teammate-question-contract.md)（结构化提问与命题级去重）

## 背景

ADR-0001 之后，队友每回合仍然只拿到「汤面 + 最近 80 条原始问答」，是否重复、哪些维度已验证、什么时候该收手，全靠模型每次自己从对话里重新推断；三位队友之间除了共享对话没有任何分工，容易扎堆在同一维度上。具体表现为：

1. 判断依据不可复用：同样的推断每个回合重做一次，token 与不确定性都随轮数增长。
2. 没有分工：小夏、阿澄、小墨只是提示词里的侧重点不同，实际挑题没有约束。
3. 没有收敛：真实模型下除 200 回合上限外没有「够了，可以交卷」的信号。

## 决策

### 1. 每局一份共享黑板，纯本地推导

`board` 挂在该局状态里（`games.state` 的 JSON，与 `teammates/pending_question` 同级），结构：

```python
{
  "asked": 6,                    # 已完成队友回合数
  "confirmed": ["…"],            # 判为“正确”的命题
  "excluded": ["…"],             # 判为“错误”的命题
  "covered": {"人物": 2, "物品": 1, …},   # 各维度被问过几次
  "stalled": 0                   # 连续“无关”次数
}
```

更新规则全部在 `board.record_turn()` 里，无模型调用：`正确` 进 confirmed、`错误` 进 excluded、`无关` 累加 stalled；前两者都会把 stalled 清零（排除也是新信息）。输入只有判题结果、提问文本与 target，都是公开信息，不触碰 `bottom/key_points`。

### 2. 固定六个维度，归类有明确优先级

`DIMENSIONS = (人物, 物品, 时间, 因果, 动机, 反例)`，关键词表在 `board.DIMENSION_KEYWORDS`。同一短语命中多个维度时按 `CLASSIFY_PRIORITY`（人物 → 时间 → 因果 → 物品 → 动机 → 反例）取第一个：例如「忘关设备」同时像物品与因果，归因果才符合它实际验证的东西。识别不出返回 `None`，不硬猜。

### 3. 分工写在档案里，不额外花调用

`TeammateProfile.dimensions` 声明每位队友负责的维度：小夏=人物/物品，阿澄=时间/因果，小墨=反例/动机。`board.next_focus()` 返回该队友负责维度中「还没有任何问答」的第一个，作为本轮 `focus_dimension`。

### 4. 覆盖驱动选目标

- LLM 模式：payload 增加 `board`（confirmed/excluded 最近 6 条、open_dimensions、asked、stalled）与 `focus_dimension`；提示词要求优先验证 focus，并禁止重复黑板里的同义命题。
- 演示模式：先挑落在 focus 维度上的未问线索；该维度没有线索时退回原有轮换顺序（不硬凑其他题的答案）。

### 5. 收敛提示是经验阈值，不冒充覆盖率

`board.hint(board, fact_count)`：
- `len(confirmed) >= fact_count` → 「已确认 N 个命题，可以尝试提交完整还原。」
- `stalled >= 3` → 「连续 N 次没有得到肯定回答，换个维度或直接提交还原试试。」

**刻意不写「已还原 X 条关键事实」**：`confirmed` 是「被判为正确的命题数」，`key_points` 是「关键事实数」，两者单位不同（一条事实可能需要多个命题才能锁定，也可能一个命题就命中）。把 `confirmed/fact_count` 当覆盖率展示会虚报，所以在 API 里 `board` 与 `puzzle.fact_count` 分开暴露，文案只说「命题」。

### 6. 增量字段与兼容

- `/api/state` 新增 `board`（见 `board.view()`）与 `hint`（仅 `playing` 时有值）；请求模型无变化，OpenAPI 快照不变。
- 老存档没有 `board`：`restore_board()` 按空黑板补齐，沿用项目已有的 `setdefault` 兼容惯例，不做数据库迁移。
- `Engine.teammate(surface, memory, teammate=None, board=None)` 增加可选参数；不传时黑板按空处理，旧调用方照常工作。

## 备选方案

| 方案 | 不采纳的原因 |
| --- | --- |
| 让模型每轮维护黑板 | 每位队友回合再多一次调用；不可复现、不可单测，且模型可能把推测写进「已确认」 |
| 黑板单独建表 | 黑板是一局的派生态，和 `games.state` 同生命周期；建表就要迁移与版本兼容，收益为零 |
| 用 `key_points` 对齐黑板算覆盖率 | 直接把汤底喂进队友链路，破坏「队友不知道真相」的核心边界 |
| 把 `confirmed/fact_count` 直接当进度展示 | 单位不同，会让玩家以为已还原 4/3 条事实（实测演示局已确认 4 个命题、事实 3 条） |
| 用模型做 target→维度归类 | 归类只是路由，规则足够且零成本；模型归类还会引入不一致 |

## 后果

正面：

- 队友的输入从「80 条原始对话」变成「黑板摘要 + 少量对话」，token 更省、行为更稳。
- 分工是声明式的：加队友只需在档案里写 `dimensions`。
- 收敛提示让玩家知道什么时候可以交卷，也让评测多了一个可观察量（`board.confirmed`）。
- 黑板纯本地推导，可单测、可回放，不新增任何模型调用。

代价与已知局限：

- 维度关键词是启发式，跨题材新题可能归错或归不进（返回 `None`，退回轮换）。
- 演示题「电梯」没有时间/因果线索，阿澄在该题上会退回轮换、问到物品维度——分工在演示题库上不完整，真实模型下由提示词约束。
- `confirmed` 与 `fact_count` 仍是两套度量，收敛阈值只是经验值；是否引入「按关键事实对齐的覆盖率」留到 P2（需要更严格的信息隔离设计）。
- 前端的 `已确认 N 个命题` 是新增展示，尚未做更细的维度进度条。

## 验收

- `pytest` 全绿（新增 `test_shared_board.py`：归类、黑板更新、分工、收敛提示、老存档恢复、API 字段）。
- `scripts/evaluate_teammates.py` 基线不退化（8 回合、重复率 0、无关率 0、覆盖 1.0）。
- 页面显示「已确认 N 个命题」，收敛时在回合条显示提示，且不出现「已还原 4/3 条事实」这类虚报。
