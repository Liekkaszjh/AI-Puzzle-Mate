# 问渊 · AI Puzzle Mate

AI 海龟汤推理游戏。保留圆桌围坐展示，支持单人或多名 AI 队友合作（默认2位，可选1至3位）、已有题库与生成新题、对话判定、完整还原评分和刷新/重启恢复。

![产品封面](docs/assets/product-cover.png)

## 当前技术架构

| 部分 | 技术 | 目录 | 职责 |
| --- | --- | --- | --- |
| 出题模块 | LangGraph + DeepSeek | `code/module1_puzzles` | 题库 RAG → 规划 → 图谱辅助出题 → 审核 → 专门修改 |
| 队友模块 | DeepSeek | `code/module2_teammate` | 根据汤面与公开对话提问 |
| 汤主模块 | FastAPI + DeepSeek + SQLite | `code/module3_host` | 判题、评分、用户、回合、数据持久化 |
| 前端模块 | Vue 3 + Vite | `code/module4_frontend` | 游戏桌面、对话记录、评分展示 |

共用的模型客户端、接口协议和引擎装配分别放在 `code/llm.py`、`code/contracts.py`、`code/engine.py`。旧实现已归档至 `legacy/`。

新系统使用本地 FastAPI 与 SQLite。当前支持匿名用户与 AI 合作，不含多人实时房间或密码登录。旧的 Supabase/原生 JS 技术栈说明已被本架构取代。

## 启动

需要 Python 3.11+、Node 22.12+。在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe code/run.py --demo
```

另开终端启动前端：

```powershell
cd code/module4_frontend
npm ci
npm run dev
```

浏览器打开 <http://127.0.0.1:5173>；后端接口文档 <http://127.0.0.1:8000/docs>。

离线演示无需密钥。接入真实模型：在根目录 `.env` 填写 `DEEPSEEK_API_KEY`，设置 `DEMO_MODE=false`，不带 `--demo` 重启后端。模型可通过 `DEEPSEEK_MODEL` 调整；密钥只保留在后端。生成审核默认最多七次模型请求，失败不自动网络重试。真实 API 需要自行配置额度。

## 协作与验证

分工、依赖方向、接口字段、数据库表和已知范围详见 [架构与协作约定](docs/software/architecture.md)。前端可直接使用 [OpenAPI 快照](docs/software/openapi.json) 对接。建议按 frontend/backend/agents/model/storage 分支开发，经 PR 审查后合并。

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts/evaluate_teammates.py
cd code/module4_frontend
npm test
npm run build
```

`scripts/evaluate_teammates.py` 是队友提问质量的离线评测：默认演示模式、不联网，输出重复率、判题无关率、确认覆盖与每回合模型调用数，指标不达标时退出码为 1。加 `--live` 才对真实模型采样（需要 `.env` 配置 API Key 并关闭演示模式）。

Python 安装定义在 `pyproject.toml`，前端依赖锁定在 `package-lock.json`。数据库首次启动自动建立于 `data/`；重启保留，会话创建24小时后过期。JSON 题库可以运行 `python scripts/import_puzzles.py` 导入。四个 module 目录均为当前实现，旧代码在 `legacy/` 备查。

后端已验证依赖快照见 `requirements-dev.lock`。端到端联调在前端目录运行 `npm run test:e2e`（需要根目录 `.venv` 与 Chrome）；GitHub Actions 配置位于 `.github/workflows/ci.yml`。

## 项目文档

- [架构与协作约定](docs/software/architecture.md)
- [架构决策记录](docs/adr/README.md)
- [出题](code/module1_puzzles/README.md) / [队友](code/module2_teammate/README.md) / [汤主](code/module3_host/README.md) / [前端](code/module4_frontend/README.md)
- [需求分析](docs/requirements/functional_spec.md)
- [GitHub 协作流程](docs/mgmt/github_workflow.md)
- [项目管理](docs/mgmt/README.md)
- [产品介绍视频](promo-video/out/wenyuan-promo-final.mp4)
