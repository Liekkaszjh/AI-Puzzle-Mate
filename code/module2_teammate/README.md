# 模块2 · AI 队友

核心实现在 `__init__.py`，负责队友小夏、阿澄、小墨的角色档案、公开对话推理、命题级去重和演示线索。决策记录见 [ADR-0001](../../docs/adr/ADR-0001-teammate-question-contract.md)。

## 接口

```python
propose_turn(client, surface, history, teammate=None, board=None) -> {
    "question": str,    # 中文是非问题，<= 80 字符
    "target": str,      # 想确认的维度，<= 32 字符
    "rationale": str,   # 为什么先问它，<= 120 字符
}
```

- 只接收公开汤面、公开问答记录与公开黑板；不接收汤底、评分事实、数据库连接或整个游戏对象。
- `teammate` 是公开角色信息 `id/name/focus`；`strategy/dimensions` 由模块内的 `PROFILES` 按 id 取出，只进提示词与分工，不进入公开状态。
- 共用模型客户端来自 `code/llm.py`；模型错误抛 `ModelError`。

## 角色

`TeammateProfile(id, name, focus, strategy, dimensions)` 是唯一注册表 `PROFILES`，`TEAMMATES` 由它的 `public()` 派生。加队友只需加一条记录；老存档里未知 id 回落到 `FALLBACK_PROFILE`，按 `id/name/focus` 还原。

## 共享黑板与分工

`board.py` 维护每局的 `asked/confirmed/excluded/covered/stalled`，全部由判题结果与 `target` 本地推导（不调用模型、不读汤底），随 `games.state` 持久化。`next_focus()` 取该队友负责维度中尚未被问过的第一个作为本轮 `focus_dimension`：LLM 模式的 payload 带上黑板摘要与 focus，演示模式优先挑该维度的未问线索、没有则退回轮换。收敛提示 `hint()` 在确认命题数达到关键事实数或连续三次无关时触发。决策记录见 [ADR-0002](../../docs/adr/ADR-0002-teammate-shared-board.md)。

## 去重与交还

- 新提问与公开历史做命题级比对：剥掉“这和…有关吗”一类提问框架后算 2-gram 余弦，阈值 `DUPLICATE_THRESHOLD = 0.7`。
- 命中重复只重试一次（payload 带 `avoid` 与 `duplicate_of`），仍重复抛 `DuplicateQuestion`。
- `TeammateYield` 的子类表示“把发言权交还玩家”，由模块3 转成 `notice`；其余 `ModelError` 按 502 处理。

## 演示模式

线索按公开汤面的标记匹配，不读取出题模块的私有答案；匹配不到时给通用维度线索，绝不套用别的题的答案。线索用尽抛 `DemoCluesExhausted`。

合作模式默认两位 AI，可选 1 至 3 位。每轮玩家提问后，按阵容顺序让每名队友各提问一次，再回到玩家。全部队友共享有发言者身份的公开问答与 `target/rationale`，避免重复提问；未配置独立私有记忆。回合控制、失败重试与记忆持久化由模块3 负责；本模块不操作浏览器、HTTP 或数据库。

协作时主要修改本目录；接口变更需同步根目录 `contracts.py`、`engine.py`、`docs/software/architecture.md` 及相关测试。
