# 四个核心业务模块

```text
code/
├── module1_puzzles/       出题、审核、修改、题目校验与题库导入源
├── module2_teammate/      AI 队友提示词与提问逻辑
├── module3_host/          汤主判题与评分
│   ├── api/               FastAPI、用户与游戏回合服务
│   └── storage/           SQLite 持久化与事务
├── module4_frontend/      Vue 3 + Vite 游戏界面
├── llm.py                 共用 DeepSeek 客户端与配置
├── contracts.py           共用引擎/模型接口协议
├── engine.py              组合三个业务模块
└── run.py                 后端启动入口
```

四个模块均为当前运行代码。旧代码已归档至根目录 `legacy/`，不参与新链路。

后端：根目录 `python code/run.py --demo`。前端：进入 `code/module4_frontend` 执行 `npm run dev`。

[安装步骤](../README.md) · [分工与接口](../docs/software/architecture.md)。
