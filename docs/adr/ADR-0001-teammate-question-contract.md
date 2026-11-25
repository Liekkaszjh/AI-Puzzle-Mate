# ADR-0001：AI 队友的结构化提问契约与命题级去重

- 状态：已采纳
- 日期：2026-11-26
- 范围：`code/module2_teammate`、`code/engine.py`、`code/contracts.py`、`code/module3_host/api/service.py`、`scripts/evaluate_teammates.py`

## 背景

优化前的队友是「无状态单轮提示词 + 轮询调度」：`propose_question(client, surface, history, teammate) -> str` 一次模型调用直接产出一个问句，角色差异只靠把 `focus` 一行字塞进 payload，防重复只做 `question in {已问句}` 的精确字符串比较。

这带来四个具体问题：

1. **重复挡不住同义改写**。「这和身高有关吗？」与「这与他的身高有关吗？」是同一命题，精确比较判不出来，两位队友会连续问同一件事。
2. **决策过程不可见**。只有一个问句字符串，无法知道队友想确认什么、为什么先问它；前端只能显示一句话，评测也只能靠人工读。
3. **重复与线索耗尽会变成 502**。演示线索用尽抛 `ModelError` 之外的自定义异常、重复问题抛 `ModelError`，前者被 service 特判，后者直接变成请求失败，玩家看到的是「卡住」而不是「这一轮交还给你」。
4. **角色与提示词硬编码**。`SYSTEM_PROMPT` 里写死「队友小夏」，再用 `.replace("队友小夏", "队友")` 打补丁加人，加第四位队友必须改代码和提示词。

同时项目里没有任何队友质量的量化指标，无法判断改动是否让队友变好。

## 决策

### 1. 队友回合改为三字段结构化契约

```python
Engine.teammate(surface, memory, teammate=None) -> {
    "question": str,    # 一个中文是非问题，<= 80 字符
    "target": str,      # 这次想确认的维度，<= 32 字符
    "rationale": str,   # 为什么现在先问它，<= 120 字符
}
```

`target/rationale` 由公开汤面推导，不含汤底，可以进入公开历史。service 把三者写进 `pending_question/pending_target/pending_rationale`，判题后落到该回合（以及 `teammate_memories` 白名单），供下一位队友、前端和评测共用。

**兼容**：`service.teammate_turn()` 仍接受纯字符串（旧引擎、monkeypatch 测试），按 `target=""、rationale=""` 处理。

### 2. 角色档案注册表

`TeammateProfile(id, name, focus, strategy)` 冻结数据类；`PROFILES` 是唯一注册表，`TEAMMATES = [p.public() for p in PROFILES]` 保持 API 里只有 `id/name/focus`。`strategy` 只进提示词，不进公开状态。提示词用 `string.Template` 的 `$name/$focus/$strategy` 组装，删除 `.replace()` 补丁；未知 id（老存档）回落到 `FALLBACK_PROFILE`，按 `id/name/focus` 还原，不丢角色。

### 3. 命题级去重：剥框架 + 2-gram 余弦

- 先删掉只承载提问骨架的词（`是不是/是否/有关/关系/这/那/他/她/它/的/了/吗/呢/与/和`），再用字符与双字词向量算余弦。
- 阈值 `DUPLICATE_THRESHOLD = 0.7`，实测标定：同义改写 0.77–1.00（`这和身高有关吗` vs `这与他的身高有关吗` 为 1.00），异义 ≤ 0.33（`这和录音有关吗` vs `这和录像有关吗` 为 0.33）。
- 命中重复时**只重试一次**：第二次调用的 payload 增加 `duplicate_of` 与 `avoid` 列表，提示词追加「必须换一个尚未验证的命题」；仍重复则抛 `DuplicateQuestion`。
- 提示词同时下发最近 12 条已问句（`avoid`），把去重前移，降低重试概率。

### 4. 发言权交还走 `TeammateYield`，不再 502

```python
class TeammateYield(ModelError)      # 交还玩家，正常流程
class DemoCluesExhausted(TeammateYield)
class DuplicateQuestion(TeammateYield)
```

service 只捕获 `TeammateYield`：写入 `notice`、`next_actor=player`、`teammate_index=0`，返回 200。其它 `ModelError`（协议错误、超时、鉴权）仍按 502 处理，失败不写入历史。演示线索按公开汤面标记匹配；匹配不到时给通用维度线索，绝不套用别的题的答案。

### 5. 评测脚本作为回归门禁

`scripts/evaluate_teammates.py` 用 `TestClient` 跑完整回合，统计：重复率、判题无关率、确认覆盖率（`正确` 数 / `fact_count`）、每回合模型调用数与最高值，并输出阈值判定（不达标退出 1）。默认强制 `DEMO_MODE=true`，`--live` 才允许真实模型；`--json` 供 CI 解析。

基线（演示模式，2 局 3 轮、每题 2 位队友）：

| 指标 | 基线值 | 阈值 |
| --- | --- | --- |
| 队友回合 | 8 | — |
| 重复率 | 0.000 | ≤ 0.05 |
| 无关率 | 0.000 | ≤ 0.50 |
| 确认覆盖 | 1.000 | ≥ 0.60 |
| 每回合模型调用 | 0（演示不调模型） | ≤ 3.0 |

演示基线天然接近满分（线索是题库自带脚本），它保证的是契约与管道不回归，不代表真实模型质量；真实基线需要 `--live` 且配置 `DEEPSEEK_API_KEY`，尚未采集。

## 备选方案

| 方案 | 不采纳的原因 |
| --- | --- |
| 继续用单字符串 + 拉长提示词约束去重 | 无法验证是否生效；没有结构就没有评测口径；提示词已经很长 |
| 用编辑距离判重 | 对中文改写不敏感，`这和录音有关吗`/`这和录像有关吗` 与同义改写的距离排序相反 |
| 让模型自己判重（多一次调用） | 每位队友回合从 2 次调用涨到 3 次，成本和延迟都升，且仍不可测 |
| 引入向量模型 / 嵌入检索 | 当前是本地 SQLite 单机部署，为一个 80 字符问句引入嵌入依赖过重；2-gram 在本项目语料上已可分离 |
| 重复直接返回 502 让前端重试 | 玩家视角是失败；实际语义是「这轮先交还给你」，应走 notice |

## 后果

正面：

- 队友的意图可见（`target/rationale`），前端、日志、评测可复用，为 P1 的共享黑板留好落点。
- 同义重复被本地规则拦掉，拦截不额外花钱；重复/耗尽不再表现成故障。
- 角色扩展从改代码变成加一条 `PROFILES` 记录。
- 有可执行的评测门禁，改提示词前后能对比数字。

负面与代价：

- 历史与公开记忆多两个字段，老存档靠 `setdefault` 与白名单缺省兼容，不迁移 schema。
- 阈值 0.7 是标定值，不是定理；换语言或换问句风格需要重标。
- 提示词新增 `target/rationale` 要求，理论上有模型不遵守的风险，已用严格字段校验兜住（不合规返回 502，不写入历史）。

后续（不在本 ADR 范围）：

- P1：共享黑板（确认/排除/待验证维度）、开局维度分工、覆盖率驱动的选目标、收敛建议。
- 真实模型基线采集，以及把「每回合调用数」压到 1 次（生成自带自评）。
- 前端展示 `target`（如「小夏想确认：身高」）与「换一位先问」的顺序控制。

## 验收

- `pytest` 全绿（新增 `test_teammate_contract.py`、`test_teammate_metrics.py`）。
- `python scripts/evaluate_teammates.py --json` 退出码 0 且 `failures` 为空。
- 演示对局中，队友回合带 `target/rationale`；连续同义提问时页面提示「这一轮先交还给你」而不是报错。
