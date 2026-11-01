# Python 题目生成模块

使用 Python 3.11+ 标准库实现，无第三方运行依赖。根据主题、难度生成汤面、汤底、关键事实、关键线索及三级提示，并执行独立审核和有限重试。

## 模块结构

| 文件 | 职责 |
| --- | --- |
| `__init__.py` | 对外导出生成服务、生成器、检查器和模型客户端 |
| `contracts.py` | 输入类型、模型接口约定、参数规则、JSON解析、错误类型 |
| `prompts.py` | 组合Skill与生成、审核的JSON输出协议 |
| `skill_loader.py` | 读取Skill正文，处理文件缺失或格式错误 |
| `skills/puzzle-authoring/SKILL.md` | 统一维护出题限制、难度指导及审核标准 |
| `generator.py` | 生成候选题目，不处理审核和重试 |
| `checker.py` | 结构、去重、审核依据和因果引用检查 |
| `hint_rules.py` | 从公开汤面提取一级提示，并校验原文引用 |
| `model_client.py` | 聊天补全HTTP(S)协议、状态码诊断、超时和响应解析 |
| `service.py` | 生成、审核、重新生成编排及阶段计时 |
| `config.py` | 显式加载.env及模型配置 |
| `cli.py` | 真实API测试与完整JSON报告保存 |
| `__main__.py` | 安装包后的命令行入口 |

这是同步Python API，调用模型时会等待网络结果。并发调用时，每次生成的计数和草稿相互独立；自定义模型适配器需要自行保证线程安全。

## 修改出题规则

在 [出题Skill](skills/puzzle-authoring/SKILL.md) 中修改内容限制、难度指导、提示递进和审核标准。生成与审核共用这份规则，每次构造模型请求都会重新读取，无需重启。Skill随Python安装包一起发布；使用已安装的普通包时，修改源码后需重新安装，或使用可编辑安装。

`prompts.py` 仅维护调用模式和JSON输出协议。字段类型、重试上限、审核结果校验以及一级提示原文提取仍由Python代码保障；这些程序行为不能只通过修改Skill改变。Skill读取失败时停止调用模型，不会静默使用缺少限制的提示词。

## 直接运行真实测试

在项目根目录填写已有的 `.env`，变量名称与原JavaScript版本一致：

```dotenv
PUZZLE_MODEL_ENDPOINT=https://api.deepseek.com/chat/completions
PUZZLE_MODEL_NAME=填写服务支持的模型名称
PUZZLE_MODEL_API_KEY=填写密钥
PUZZLE_MODEL_TIMEOUT_MS=120000
```

地址须为完整的聊天补全请求地址，不是只有域名的基础地址。密钥可为空以连接无需认证的本地服务。

```powershell
python tests/integration/puzzle_generator_live.py 校园 普通
```

当前电脑的默认 `python` / `py` 指向不可用的Windows商店安装，已验证可用的命令为：

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" tests/integration/puzzle_generator_live.py 校园 普通
```

测试脚本无需安装包，会从项目根目录自动读取 `.env`。命令行或现有进程环境变量优先于文件中的同名配置。`.env` 支持空行、注释、`KEY=value`、单/双引号与可选的 `export` 前缀；不展开变量、不执行内容、不处理转义序列。

可选参数：

```powershell
python tests/integration/puzzle_generator_live.py 友情 简单 --max-retries 3
python tests/integration/puzzle_generator_live.py 校园 普通 --env-file .env --output-dir tests/integration/output
```

手动测试默认最多重新生成3次，即首次加3次、最多4份候选题和8次模型调用；`--max-retries` 支持0至3。每轮显示生成、检查进度及拒绝原因，未通过时携带问题重新生成，不降低审核要求。可使用 `--max-retries 0` 只检查一题。真实调用可能产生费用；由于审核也调用模型，多轮任务可能耗时数分钟。生成质量未通过也会返回非零退出码，不代表网络连接失败。

成功或失败结果保存为 `tests/integration/output/` 下独立的UTF-8 JSON文件，打印文件路径及生成、检查、总耗时。成功结果包含完整汤底及未解锁提示，仅用于开发验收。`.env`、报告目录及Python缓存均已加入Git忽略。

## 在其他Python代码中使用

先在项目根目录安装本地包：

```powershell
python -m pip install -e .
```

运行时无第三方依赖；安装时由pip在隔离环境准备setuptools和wheel构建工具。源码中的测试脚本不需要此步骤。

```python
from puzzle_generator import ChatModelClient, PuzzleService
from puzzle_generator.config import ModelSettings, load_env_file

load_env_file('.env')
settings = ModelSettings.from_env()
model = ChatModelClient(
    endpoint=settings.endpoint,
    model=settings.model,
    api_key=settings.api_key,
    timeout_seconds=settings.timeout_seconds,
)
service = PuzzleService(model, max_retries=3)
result = service.generate({'theme': '校园', 'difficulty': '普通'})

if result['success']:
    print(result['puzzle']['surface'])
else:
    print(result['error']['code'], result['error']['message'])
```

安装后也可运行 `python -m puzzle_generator 校园 普通 --env-file .env`。

## 输入和输出

输入为字典，`theme` 必填，去除首尾空白后为1至50个字符；`difficulty` 为简单、普通或困难，省略时默认普通。难度的事实数量为生成指导，不作为机械通过阈值。

成功结果：`{success: True, attempts, puzzle, review, timings}`。

| 题目字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | str | 审核通过后生成的UUID |
| `title` | str | 标题 |
| `theme` | str | 请求主题 |
| `difficulty` | str | 请求难度 |
| `surface` | str | 公开汤面 |
| `solution` | str | 完整汤底 |
| `key_facts` | list[str] | 非空关键事实列表 |
| `clues` | list[str] | 非空关键线索列表 |
| `hints` | list[str] | 恰好三级提示，由弱到强 |

一级提示由程序从公开汤面选取含转折或异常的句子（没有时使用第一句，最多80字符），固定为 `请留意汤面中的“汤面连续原文片段”。`。引号内须逐字出现在 `surface` 中，不附加隐藏机制解释，覆盖模型生成的第一级提示。只有题面及三级提示基本结构有效时才执行这一转换，缺失字段仍会拒绝。独立检查器也校验该引用规则；二、三级保留模型输出并继续审核递进程度。示例：`请留意汤面中的“画纸上没有颜料”。`。

审核报告 `review`：

- `passed`、`checks`、`issues`：整体结论、六项检查结果和具体问题。
- `reasons`：六项检查各自的简短依据。
- `causal_links`：汤面逐字引用、具体解释、从0开始的事实下标和是否已获得解释。
- `missing_premises`：故事成立所缺的必要前提。

结构检查拦截缺失字段、类型错误、重复事实/线索/提示，忽略空白与常见句读差异。同义重复交给模型检查。检查不通过不调用审核模型。

审核覆盖逻辑一致性、可解性、泄底、提示递进、内容安全和参数匹配。缺少审核依据、原文引用或事实下标无效时立即返回 `REVIEW_INVALID`；任何异常未解释或存在必要前提时，强制拒绝，即使模型输出六项全True。

`timings` 在成功与失败中均包含 `generation_ms`、`review_ms`、`total_ms`，单位毫秒，前两项是所有尝试的累计耗时。`review_ms` 包含结构校验及模型审核。

失败结果：`{success: False, attempts, timings, error: {code, message, issues?}}`，不包含草稿。

| 错误代码 | 含义 |
| --- | --- |
| `INVALID_REQUEST` | 参数错误，不调用模型 |
| `SKILL_LOAD_FAILED` | 出题Skill无法读取，立即终止 |
| `SKILL_INVALID` | Skill缺少元信息头或正文，立即终止 |
| `QUALITY_RETRY_EXHAUSTED` | 候选题或生成JSON连续不合格 |
| `REVIEW_INVALID` | 审核输出不合法，立即终止 |
| `MODEL_TIMEOUT` | 模型请求超时 |
| `MODEL_UNAVAILABLE` | 网络或HTTP状态失败 |
| `MODEL_OUTPUT_INVALID` | 模型响应无法解析或缺少内容 |
| `INTERNAL_ERROR` | 未预期错误，不返回原始异常 |
| `CONFIG_ERROR` | 配置读取或格式错误（配置层抛出，CLI捕获） |

审核问题可能包含答案，不应直接当作公开文案或普通日志内容。

## 重试与超时

`PuzzleService` 默认首次生成加3次重新生成，最多4份候选题、8次模型调用。每轮均重新检查，不通过时将问题摘要传给下一轮。网络失败、审核格式错误或超时立即停止，无隐式网络重试。

调用方可通过 `service.generate(request, on_progress=callback)` 接收进度事件：`generating`、`checking`、`rejected`、`accepted`。事件含 `attempt` 和 `max_attempts`，拒绝事件另含 `issues` 与 `will_retry`。回调异常不改变业务结果，回调中不应执行耗时操作。进度中的审核问题可能包含答案，仅用于可信调用方。

`ChatModelClient` 使用 `timeout_seconds`，默认30秒；CLI从 `.env` 中的 `PUZZLE_MODEL_TIMEOUT_MS` 转换毫秒到秒，缺省60秒，允许1至3600000毫秒。连接建立后通过计时器关闭停滞或持续慢速返回的socket。系统DNS解析可能受操作系统自身超时限制，无法承诺严格的整任务耗时。所有请求使用直连HTTP(S)，不自动跟随重定向，也不读取系统代理配置。

## 替换模型与独立检查

自定义模型只需实现同步方法 `complete(messages) -> str`，返回纯JSON文本。通过 `PuzzleService(model, review_model=another_model)` 分别设置生成与审核模型。自定义适配器应提供超时和受控错误，可抛出 `PuzzleError`。

`PuzzleChecker(model).check(puzzle, request)` 可独立审核题目；`request` 需包含有效主题、难度。结构失败返回 `{passed: False, issues, checks: None}`，模型异常会抛出。模型审核仍可能漏检，需要人工抽检和试玩；本版不包含题库存储、去重或局部修复。

## 离线测试

```powershell
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

当前电脑使用：

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m unittest discover -s tests/unit -p "test_*.py" -v
```

测试分为流程与质量规则、模型客户端、配置与CLI三部分，共享数据在 `tests/unit/puzzle_fixtures.py`。使用模拟模型及本地回环HTTP服务，不连接外部API，不需要密钥。覆盖已知学生代答因果缺口、重复内容、审核依据缺失、全部True与隐藏前提冲突、重试上限、并发隔离、网络异常、慢速响应、配置读取和完整JSON保存。
