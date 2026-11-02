# 汤主模块（Module 3：AI Host）设计说明

## 1. 文档目的

本文说明“问渊”项目中 AI 汤主模块的职责边界、内部结构、接口契约、判定策略、泄底防护和测试方案，作为模块3开发、联调和验收的依据。需求编号引用 [软件系统功能规格说明书](../requirements/functional_spec.md) 与 [非功能规格说明书](../requirements/nonfunctional_spec.md)。

## 2. 模块范围

### 2.1 范围内

- 接收玩家的一条自然语言问题，依据汤底返回 **是 / 不是 / 无关**。
- 识别开放式、包含多个独立判断、索要汤底/答案/提示词、提示词注入等问题，返回不影响推理公平性的澄清提示。
- 读取公开问答历史，复用同一问题的既有判定，并在提示词中约束语义等价问题保持一致。
- 接收玩家的最终还原，逐条核对关键事实，返回 **正确 / 部分正确 / 错误** 和百分制报告。
- 保证所有面向玩家进行中状态和判题反馈不包含汤底、关键事实、线索或未解锁提示。
- 输出调用来源和耗时，供复盘、日志和 NFR-7.1 观测使用。

### 2.2 范围外

- 题目生成、难度控制与题库保存（模块1）。
- AI 队友的提问与提示（模块2）。
- HTTP 会话、Cookie/CSRF、回合制、页面渲染、数据库持久化（模块4）。
- 账号、多人联机、排行榜和管理后台。

## 3. 系统上下文

```text
模块1 出题 ──> puzzle(title/surface/bottom/key_points)
                         │
玩家提问 ──> 模块4 会话 ──> 模块3 汤主 ──> llm.ModelClient ──> DeepSeek
                         │        │
                         │        └──> 是/不是/无关 + 安全反馈
                         └──> 公开问答历史（仅 question 回合）
```

汤主可以读取完整汤底和关键事实；模块2（AI 队友）的接口不接收这些字段。汤主与模块4之间只传递判定结果、公开反馈和交卷报告，不把汤底下发到浏览器。

## 4. 组件设计

| 组件 | 文件 | 职责 |
| --- | --- | --- |
| 契约层 | `contracts.py` | 判定词表、别名归一、题目/文本校验、`HostAnswer`、百分制结论 |
| 提示词 | `prompts.py` | `QUESTION_PROMPT`、`SCORING_PROMPT`；只描述任务与 JSON 协议 |
| 前置检查 | `question_guards.py` | 开放式、多判断、索要答案、提示词注入的本地拦截 |
| 历史层 | `history.py` | 公开历史过滤、问句签名归一、重复问题定位 |
| 防泄底 | `leak_guard.py` | 汤底/关键事实片段检测与反馈兜底 |
| 演示层 | `demo.py` | 离线内置题关键词判定 |
| 评分层 | `scoring.py` | 逐事实评分、模型输出严格校验、总分计算 |
| 服务层 | `service.py` | `HostService.ask/submit`、`judge`/`judge_detailed` 适配、耗时统计 |

依赖方向为 `service → guards/history/demo/scoring → contracts`，评分与问句判定共享 `llm.py` 的单次 JSON 调用；不存在循环依赖。

## 5. 接口契约

### 5.1 输入：题目

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `bottom` | str | 是 | 非空；汤主私有，不向玩家下发 |
| `key_points` | list[str] | 是 | 1–20 条，每条 1–200 字；评分等权 |
| `surface` | str | 否 | 公开汤面；不作为问句判定输入，避免与汤底混淆 |
| `rules` | list | 否 | 仅演示模式使用 |
| `fact_rules` | list | 否 | 仅演示模式评分使用 |

### 5.2 输入：问题/历史

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `text` | str | 问句 1–300 字；还原答案 1–1500 字 |
| `history` | list[dict] | 每项含 `kind`、`question`、`verdict`；只取 `question` 回合 |

### 5.3 输出：问句判定

```json
{"verdict": "是|不是|无关", "feedback": "可为空的安全澄清语"}
```

`verdict` 只允许三个值；`feedback` 不超过 120 字，且不得包含汤底或关键事实。模型返回的 `feedback` 被丢弃，公开反馈由本地规则生成。

### 5.4 输出：交卷评分

```json
{
  "verdict": "正确|部分正确|错误",
  "feedback": "已命中 2/3 条关键事实，得分 66.7；未命中的事实不会提前公开。",
  "report": {
    "score": 66.7,
    "max_score": 100,
    "outcome": "部分正确",
    "matched_count": 2,
    "partial_count": 0,
    "missing_count": 1,
    "contradicted_count": 0,
    "total_facts": 3,
    "facts": [{"fact": "…", "status": "matched", "credit": 1.0, "reason": "…"}],
    "answer": "玩家原文"
  }
}
```

### 5.5 `HostAnswer`（`judge_detailed`/`HostService`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `verdict` | str | 判定值 |
| `feedback` | str | 安全反馈 |
| `source` | str | `guard` / `history` / `demo` / `model` / `model_corrected` / `scoring` |
| `canonical` | str | `yes` / `no` / `irrelevant` / `correct` / `partial` / `wrong` |
| `history_size` | int | 进入判定前公开问句数 |
| `report` | dict? | 仅交卷时有值 |
| `timings_ms` | dict | `total_ms` |

## 6. 核心流程

### 6.1 问句判定 `ask`

1. 校验题目与问题长度、类型；失败抛 `ValueError`，不调用模型。
2. 执行本地前置检查；命中则返回“无关”+澄清语，`source=guard`，不调用模型。
3. 在公开历史中查找签名相同的最近问句；默认返回历史判定，`source=history`，不调用模型；传入 `recheck=True` 时跳过复用，继续调用模型按汤底复核。
4. 演示模式按内置关键词规则判定；否则构造 `{bottom, key_points, kind:"question", history, text}`，单次调用 `complete_json`。
5. 严格校验模型 JSON：只允许 `verdict`/`feedback`，判定值必须可归一；协议错误抛 `ModelError`。
6. 丢弃模型反馈，必要时用 `leak_guard` 兜底，返回 `HostAnswer`。

### 6.2 交卷 `submit`

1. 校验还原答案长度和题目结构。
2. 单次调用评分模型（或演示规则），按 `key_points` 原序核对。
3. 校验事实条数、序号、状态枚举和说明长度；非法则抛 `ModelError`，不写入会话。
4. Python 计算百分制总分，映射为 `正确/部分正确/错误`。
5. 生成本地反馈（只报告命中条数和分数），经泄底检查后返回。

## 7. 判定与一致性算法

### 7.1 三值判定

提示词采用“汤底至上 → 还原单一命题 → 三值判定 → 未知不判否 → 前提错误判无关”的顺序。模型必须区分主体、行为/状态、必要条件、因果方向和否定关系；否定问句按断言本身判断。

### 7.2 问句签名

```text
NFKC 归一 → 小写 → 去空白 → 去句首礼貌词
→ 是否/是不是/有没有/会不会/能不能/可不可以 形式归一
→ 去句尾标点 → 去句尾语气词/“了”
```

示例：

| 原问句 | 签名 |
| --- | --- |
| 他是否带伞？ | 他带伞 |
| 他带伞了吗？ | 他带伞 |
| 他是不是学生？ | 他是学生 |
| 他是学生吗？ | 他是学生 |
| 他没带伞吗？ | 他没带伞 |

签名只做保守的形式归一，不替换同义词；否定词保留，避免把肯定与否定合并。签名相同即复用最近一次公开判定，从机制上满足“同一问题回答一致”。需要纠正历史误判时使用 `recheck=True`：强制调用模型，若新判定与旧记录不同，`source=model_corrected` 并在反馈中说明已按汤底更正。

### 7.3 同义问题

签名不同的同义改写由模型在提示词内依据 `history` 保持一致；提示词同时声明“历史与汤底冲突时以汤底为准”。本地不做事后语义覆盖，避免把正确纠正误判为不一致。

### 7.4 前置检查优先级

`INJECTION → ANSWER_REQUEST → OPEN_ENDED → MULTI_CLAIM`。越靠前的规则越涉及安全边界；全部命中时返回最严格的一条。

## 8. 泄底防护

| 层 | 措施 |
| --- | --- |
| 提示词 | 禁止 feedback 包含汤底、关键事实、线索、提示和推理过程 |
| 服务层 | 模型 feedback 一律丢弃，只使用本地文案 |
| 检测层 | 6 字连续片段重合率 ≥ 50% 或完整包含关键事实时替换为兜底文案 |
| 输出层 | 交卷反馈只报告条数和分数，不点名未命中的事实 |
| 集成层 | 模块4进行中只下发标题/汤面/事实条数，结束后才下发 `solution` |

`leak_guard` 以“连续片段”而非单字重合为判据，避免正常澄清语被误伤；完整包含汤底或任一关键事实时直接判定泄底。

## 9. 错误处理与可观测性

| 场景 | 异常 | 调用方处理 |
| --- | --- | --- |
| 空/超长/类型错误/题目缺字段 | `ValueError` | 模块4返回 400 或直接提示 |
| 模型 JSON/字段/枚举非法 | `llm.ModelError` | 模块4返回 502，保留当前局 |
| 网络超时/HTTP 错误 | `llm.ModelError` | 同上；模块4不把失败回复写入历史 |
| 评分条数/序号/状态非法 | `llm.ModelError` | 保留当前局，允许重新提交 |

每次 `HostAnswer` 返回 `source` 和 `total_ms`；`judge_detailed` 把这些信息交给调用方，便于按 NFR-7.1 记录 Agent 类型、耗时、状态和错误类别。模块本身不写日志，避免在日志中落入问题原文或汤底。

## 10. 需求追踪

| 需求 | 设计/实现 | 测试 |
| --- | --- | --- |
| FR-3.1 是/不是/无关 | `QUESTION_PROMPT`、`HostService.ask`、枚举校验 | `test_model_verdict_aliases_are_canonical`、端到端通关 |
| FR-3.2 模糊/多判断拆分 | `OPEN_ENDED`、`MULTI_CLAIM` 前置检查 | `test_guards_block_before_model_call` |
| FR-3.3 与汤底/历史一致 | 历史注入、签名复用、`recheck` 复核纠正 | `test_repeated_question_reuses_history_without_model_call`、`test_repeated_question_can_be_rechecked_and_corrected`、签名测试 |
| FR-3.4 不泄露汤底 | 模型反馈丢弃、`leak_guard`、评分摘要 | `test_model_feedback_is_discarded_even_when_safe`、`test_submit_feedback_never_leaks_bottom_or_facts` |
| US-03 自然语言问答 | `judge(..., kind="question", history)` | 全部问句测试 |
| US-05 三级还原结论 | `HostService.submit`、`final_outcome` | `test_full_score_is_correct`、`test_partial_score_is_partial`、`test_zero_score_is_wrong` |
| NFR-3.2 队友越权边界 | 汤主不向模块2传汤底；历史只含公开问句 | 模块2接口测试、`test_public_history_filters_final_and_invalid_turns` |
| NFR-4.2 判定准确率 | 提示词+前置规则；需固定测试集评测 | 单元测试只验证协议，真实准确率见测试方案 |
| NFR-4.3 同义一致性 | 历史注入+签名复用 | 签名测试、重复问题测试 |
| NFR-7.1 调用可观测 | `source`、`timings_ms`、`judge_detailed` | `test_history_size_and_timings_are_reported` |

## 11. 测试方案

### 11.1 自动化测试

```powershell
cd code
python -B -m unittest -v test_module3_host.py
python -B -m unittest -v test_game.py
```

- `test_module3_host.py`：34 个用例，使用本地桩客户端，覆盖判定协议、前置检查、历史一致性、泄底防护、三级评分、演示模式和输入校验；不连接外部 API。
- `test_game.py`：27 个用例，覆盖模块1–4 完整流程、汤底隐藏、回合制、刷新恢复、评分和模型协议；使用本地模拟 HTTP 服务。

### 11.2 准确率评测（NFR-4.2/4.3）

1. 准备固定汤底和至少 100 条人工标注问句，标注“是/不是/无关”；另准备至少 50 组同义改写和 30 条剧透诱导。
2. 用 `judge(..., history=[])` 逐条运行，记录混淆矩阵、分类准确率、冲突数和泄露数。
3. 同义组内比较回答一致性；剧透诱导检查 `feedback` 和 `verdict` 是否泄露未公开信息。
4. 记录模型名称、版本、提示词版本、网络条件和测试时间；准确率不达标时先调整提示词和前置规则，再考虑更换模型。

### 11.3 手工验收

- 从“创建游戏”到“提交答案并查看复盘”完整闭环。
- 对明确是非问题稳定得到“是/不是/无关”，否定问句、前提错误问题表现合理。
- 开放式/多判断问题得到拆分提示，而不是误导性结论。
- 同一问题重复提问回答一致；刷新后历史仍在。
- 进行中页面和接口响应不出现汤底、关键事实或未解锁提示。

## 12. 配置与部署

- 模型配置由 `llm.ModelClient` 从 `.env`/环境变量读取，密钥不出服务端。
- 模块3本身无第三方依赖，随 `code/` 目录部署；模型地址、密钥和超时由统一配置层管理。
- `HostService` 无状态，可由模块4按请求创建或复用；并发安全由调用方和模型客户端保证。
- 演示模式由 `DEMO_MODE=true` 或缺少密钥触发，不访问远程模型。

## 13. 已知限制与后续工作

- 问句签名只做形式归一，同义改写的一致性依赖模型，建议在评测中单独统计。
- 前置检查是启发式规则，复杂问句可能漏检或需要玩家改写；模型提示词仍作为第二道约束。
- 交卷评分是单次模型调用，复杂因果或长答案可能需要更强模型；评分不合格时保留当前局并允许重提。
- 本模块不持久化历史、不做权限校验，相关能力属于模块4；联调时需确认 `history` 只包含公开问句。
- 真实准确率、P95 延迟和并发指标需在测试环境按 NFR-1.2、NFR-4.2、NFR-4.3 实测，不能由单元测试推断。
