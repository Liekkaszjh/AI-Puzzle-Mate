# 慢慢想 · 海龟汤推理桌

Python 3.9+ 实现的本地游戏，只使用 Python 标准库，无需安装依赖。在浏览器中围桌推理，右侧独立显示完整对话记录。

## 启动

在本目录执行：

```powershell
python run.py
```

打开 <http://127.0.0.1:8000>。也可以在上级目录执行 `python .\海龟汤游戏\run.py`。

## DeepSeek 配置

项目已经创建 `.env` 文件，只需要填写这一项，再重启服务：

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek密钥
```

密钥可在 [DeepSeek 开放平台](https://platform.deepseek.com/) 创建。程序统一使用 `deepseek-flash`，请求地址固定为 `https://api.deepseek.com/v1/chat/completions`，出题、队友、汤主共用同一个配置。不设置其他厂商或模型，也不会在失败时切换到其他模型。

其余可选配置：

```dotenv
DEEPSEEK_TIMEOUT=60
DEMO_MODE=false
HOST=127.0.0.1
PORT=8000
```

进程环境变量优先于 `.env`。密钥保留在 Python 后端，不传给网页，`.env` 已加入 Git 忽略规则。`.env.example` 是无密钥备份模板。没有密钥或设置 `DEMO_MODE=true` 时使用离线演示；有密钥后远程调用失败会提示错误，不会自动换成演示答案。

## 围桌玩法

如果遇到网络报错，在正常网络终端运行 `python run.py --check-api`。这个命令只读取 DeepSeek 模型列表，验证连接与密钥，不产生文本生成费用。若提示连接被拒绝，请检查 `HTTP_PROXY` / `HTTPS_PROXY` 是否指向已经关闭或无效的代理，并在修正后的终端重启服务。超时可通过 `.env` 中的 `DEEPSEEK_TIMEOUT` 调整（1到180秒）；401代表密钥无效，402代表账户余额不足。

- **汤主老陈**坐在桌子上方，**你**坐在下方。**AI 队友小夏**在合作模式中坐到另一侧。人物均有本地 SVG 形象、发言气泡与当前回合高亮。
- 首页选择 **和 AI 一起玩** 或 **我自己来**，再选择题目来源。**随机已有题目**直接抽取题库进入桌面，不调用出题模型；**出一道新题**进入主题输入页，输入主题后点击“生成新题并入座”，成功后进入桌面。
- 新生成题目包含汤面、汤底和若干条 `key_points` 关键事实，保存到 `module1_puzzles/generated_puzzles.json`。以后随机已有题目也可以抽到。离线演示只抽取支持本地判题的内置题。返回选题不会删除当前局，可点击“回到当前推理桌”恢复。
- **合作模式**：你提问 → 汤主判断 → 小夏自动提问 → 汤主判断 → 再轮到你。不能在队友回合连续提问或提交还原。失败可点击“重试队友回合”，刷新也能恢复尚未完成的队友回合。
- **单人模式**：只有你与汤主，提问后可以继续提问，不调用队友模块。
- 桌面纸张显示汤面，较长内容可在纸张内滚动阅读。右侧“桌边的对话”按顺序保留问题、发言者及汤主的正确／错误／无关判定，可独立滚动。
- 想通后点击 **我要交答案**，打开独立的故事还原输入框，填写完整解释，再点击 **提交答案并评分**。与平时的问题输入框分开，避免误提交。
- 交卷后结束本局并展示总分、逐条事实评估、自己的答案与完整汤底。满分状态为 `won`，非满分为 `scored`，都可以重新选题。得分可通过“查看本局得分”再次打开，刷新后保留。
- 输入框按 Enter 提问，Shift + Enter 换行。桌面端对话记录在右侧，小屏幕位于场景下方。

## 四个模块文件夹

```text
海龟汤游戏/
├── module1_puzzles/        模块1：出题提示词、汤面与汤底、内置演示题
├── module2_teammate/       模块2：根据汤面和公开对话提问
├── module3_host/           模块3：根据汤底判定提问或最终还原
├── module4_frontend/       模块4：Python HTTP 服务、网页、人物 SVG
├── run.py                  启动入口
├── llm.py                  DeepSeek 单次请求、配置读取
├── test_game.py            端到端与模型协议测试
├── .env                    填写你的 DeepSeek 密钥
├── .env.example            配置模板
└── .gitignore
```

| 模块 | 接口 | 输入 | 输出 |
| --- | --- | --- | --- |
| 出题 | `generate_puzzle(client, theme="")` | 题材 | `title`、`surface`、`bottom`、`key_points` |
| 队友 | `propose_question(client, surface, history)` | 汤面、公开历史，无法读取汤底 | 问题字符串 |
| 汤主 | `judge(client, puzzle, text, kind="question")` | 含汤底的题目、提问或还原 | `verdict`、`feedback` |
| 汤主评分 | `score_reconstruction(client, puzzle, text)` | 汤底、关键事实、玩家答案 | 百分制总分、逐条状态与说明、命中条数 |
| 前端 | `create_server(client, host, port)` | 模块输出、玩家操作 | 围桌交互与右侧记录 |

每个 AI 模块每次执行只有一次 DeepSeek 请求，无 Agent 循环、无自动网络重试。出题一次请求；单人提问一次请求；合作模式一轮为玩家判定一次、队友提问一次、队友判定一次，共三次请求。最终交卷评分一次请求。队友判题失败时保留已经生成的问题，手动重试只继续判题。

## 关键事实与评分

出题提示词位于 `module1_puzzles/prompts.py`，参考 `AI-Puzzle-Mate-main/code/core_engine/puzzle_generator/prompts.py` 与其中 `skills/puzzle-authoring/SKILL.md` 的创作约束，适配为单次生成：先确定完整因果，再压缩汤面，内部自查信息来源、行为动机和必要条件。新题汤面单段且不超过100字符，关键事实3至6条，重复事实或结构不合格不会入库；旧题库保持可读。未引入额外审核模型调用。

请求指定 `response_format: {"type":"json_object"}`、`stream:false`、`thinking:{"type":"disabled"}`。三个模块仍分别执行单次请求。解析器区分截断、空正文和非法JSON，不补全残缺内容，不接受重复字段或非标准数值；模型不支持这些请求参数时会明确报错，不静默改用其他模型。这些协议行为已通过本地模拟测试，真实接口兼容性需实际请求验证。

题目中的 `key_points` 既是出题者给出的关键事实，也是评分依据。推理时只显示事实条数，交卷或揭晓后才公开内容。DeepSeek 逐条核对玩家答案的语义，允许同义表述，判断为：

| 状态 | 每条计分 |
| --- | --- |
| 完整命中 `matched` | 1 |
| 部分命中 `partial` | 0.5 |
| 未提及 `missing` | 0 |
| 存在矛盾 `contradicted` | 0 |

总分由 Python 计算：`round(各事实计分之和 / 事实条数 × 100, 1)`，所有事实等权。例如4条事实，2条完整、1条部分、1条遗漏，得到62.5分。模型不能直接指定总分。服务端会验证事实数量、顺序和状态，结果无效时保留当前局，允许重新提交。

## HTTP 协议

先 `GET /api/state` 获取会话 Cookie 与 `csrf`。POST 带相同 Cookie、`Content-Type: application/json` 和 `X-CSRF-Token: 返回的csrf`。

| 方法 | 路径 | JSON 请求体 | 作用 |
| --- | --- | --- | --- |
| GET | `/api/state` | 无 | 读取或恢复当前局 |
| POST | `/api/new` | `{"source":"existing","play_mode":"coop"}` | 随机已有题；新题用 `source:"new"` 并传非空 `theme` |
| POST | `/api/question` | `{"text":"和身高有关吗？"}` | 玩家回合提问，最多300字 |
| POST | `/api/teammate` | `{}` | 完成队友回合，仅合作模式轮到队友时可用 |
| POST | `/api/final` | `{"text":"完整还原……"}` | 玩家回合交卷，最多1500字，评分后结束 |
| POST | `/api/reveal` | `{}` | 揭晓并结束 |

状态含 `mode`（`demo/llm`）、`status`（`idle/playing/won/scored/revealed`）、`source`、`play_mode`、`next_actor`（`player/teammate`）、`pending_question`、`notice`、`history`、`report`。进行中 `puzzle` 仅含标题、汤面和 `fact_count`；结束后才返回含汤底的 `solution`。交卷后的 `report` 包含 `score`、`matched_count`、`total_facts`、`answer` 和逐条 `facts`。网页自动在玩家提问成功后调用队友接口，服务端强制检查回合。

## 演示与限制

无密钥时有两道轮换演示题，使用简单关键词判题，不支持复杂语义或自由题材。每题四条预设 AI 线索用完后，会提示玩家自行继续。完整语义判定需填写 DeepSeek 密钥。

会话存在内存，重启清空，同一浏览器多标签共享当前局，闲置24小时后过期，每局最多200次互动。服务默认仅监听本机，无账号和多人联机系统。队友最多收到最近80条公开互动。

## 验证

```powershell
python -B -m unittest -v test_game.py
```

覆盖完整通关、汤底隐藏、单人／合作模式、严格轮流、刷新恢复、队友失败恢复、演示线索用尽、输入校验、会话隔离、互动上限、评分、已有题不触发生成、新题保存与随机复用及 DeepSeek 请求格式。模型协议测试使用本地模拟服务，不消耗真实 API 额度。
