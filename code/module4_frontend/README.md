# 前端模块 · Vue 3 + Vite

```powershell
cd code/module4_frontend
npm ci
npm run dev
```

访问 <http://127.0.0.1:5173>。Vite 将 `/api` 转发到 `127.0.0.1:8000`，前后端均使用 `127.0.0.1`，避免混用 localhost 导致 Cookie 不一致。

`src/api.js` 负责请求、Cookie 与 CSRF；`App.vue` 管理页面和操作；`components/GameTable.vue`、`ConversationLog.vue`、`ScoreReport.vue` 分别负责汤面、对话和评分。组件不接触 API Key、汤底判定逻辑和 SQL。

未登录时只显示注册/登录入口，不能进入游戏。玩家登录后可选择单人或1至3名 AI 队友、已有题/新题、提问、交卷、揭晓，并修改自己的昵称和密码。管理员登录后进入注册用户管理界面，可搜索、查看、改昵称及启用/禁用玩家账号；不显示游戏操作。刷新恢复当前局；玩家重新登录后可接续账号最近一局。

`GameTable.vue` 与 `components/roundtable.css` 恢复圆桌、纸质汤面、汤碗、人物头像和发言气泡。`public/avatars` 保存本地 SVG 人物。默认两名 AI，可在开局时选1至3名；人物高亮和记录按实际队友身份展示。前端逐个执行队友回合，失败后继续当前队友，已完成回合不会重复执行。

`npm run build` 输出 `dist/`；生产环境由 Web 服务托管它，并将同域 `/api` 反向代理到 FastAPI。`npm run preview` 仅预览静态构建，不提供生产 API 代理。`npm test` 检查 API 客户端协议。

`npm run test:e2e` 使用 Playwright 启动真实 Chrome 验证完整前后端链路（需要根目录已安装依赖的 `.venv` 和本机 Chrome，缺失时先 `npx playwright install chrome`）。测试独占8001/5174端口，使用 `data/e2e.sqlite3` 和演示模式；不消耗模型额度。桌面与手机截图输出到 `data/verification/`。
