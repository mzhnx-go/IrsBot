# 交接文档：模型供应商功能改造（P5–P9 系列）

> 生成时间：2026-09-21 ｜ 交接对象：接手后续开发的 agent
> 项目根：`D:\AIpy\full-stack\IrsBot` ｜ 分支：`feat/agent-platform`（未推送远端）
> 上游文档：[providers-ui-plan.md](./providers-ui-plan.md)（总计划+P5–P9 实施设计）、[PROGRESS.md](./PROGRESS.md)（运行态，**必读**）

---

## 一、项目一句话与硬约束

IrsBot：本地部署单用户 AI Agent 应用，Docker 一条命令启动，**前后端统一 8000 端口**（backend 容器托管 `frontend/dist`，绑定挂载即生效）。

**违反任何一条都会白干，先背下来：**

1. **e2e/实机验收一律打 `http://127.0.0.1:8000`**，不是 5173（`playwright.config.ts` 已配好，勿动；`webServer` 块已删不许加回）。
2. **改后端代码后必须 `docker compose up -d --build backend`**（`up -d` 不触发 watch）；依赖变更前先重跑 wheelhouse（见 `backend/Dockerfile` 注释）。
3. **宿主机跑 pytest 必须 `POSTGRES_SERVER=localhost` 且用根 `.venv`**（db 容器故意不映射 5432）；conftest 有安全阀：库名非 `test_app` 直接 RuntimeError。
4. **测试可能被并行 agent 干扰**（共享 test_app 库）：偶发批量失败先原样重跑一次再判断。
5. 每完成一个小功能 **commit 一次**（用户明确要求，方便回退）。
6. e2e 机器空闲内存 <2GB 时 Chromium 大面积超时，跑前查内存、必要时 `--workers=1`。
7. **commit 前查 `git status`**：并行 agent 可能同仓提交，只 add 自己的文件。
8. 改前端路由文件后先 `npx vite build` 生成 routeTree 再 tsc，否则报「路由不存在」。
9. PowerShell stdout 常不回显，命令输出落盘再读。

## 二、当前状态（截至交接时）

### 已完成（提交链按时间序，全部已 commit）

| 提交 | 内容 |
|---|---|
| `984caab`–`00504df` | 模型源页 AstrBot 风格改造（Tab 栏/主从两栏/详情三分区/四个能力 Tab 占位） |
| `4755bcc`+`87b6e0c` | **P6 高级配置**：超时/代理/自定义请求头（config JSON 免迁移，`get_chat_model`+余额真实生效） |
| `5a2a1a7`+`bbc8e9d` | **P7 模型管理**：provider_models 表 + 上游 /models 拉取（三协议）+ 自定义模型（实机真拉 Agnes 12 个模型验证过） |
| `9ee9c14`+`67d2e21` | **P8 多 API Key**：provider_keys 表（迁移 `e2f6b3c7a9d4` 已在容器跑过、api_key 已回填 2 行）+ 轮换/冷却 + 前端面板 |
| `8da4c50` | P7 迁移修复（index=True 与显式建索引重名） |

后端测试基线：api+provider+core/agent **478 passed**；e2e 相关套件 24 passed；tsc/vite build 均通过。

### ⚠️ P8 收尾未做（第一优先级）

1. **P8 实机验收**：容器已重建（health 200），但浏览器端「添加更多」面板没做过人工/自动化闭环（批量粘贴→列表打码→启停→删除）。建议用浏览器自动化照 P7 的验收流程做一轮（登录 admin@example.com / 密码在 `.env` 的 `FIRST_SUPERUSER_PASSWORD`，进 `/providers` 点 Agnes → API Key 行点「添加更多」）。
2. **P8 的 PROGRESS.md 留档**：仿照待办 13/14 的格式在第十节进度表追加一行 + 待办表视情况加条目。
3. P8 轮换只接了 `get_chat_model`/余额/模型拉取三处；**Agent 聊天失败时的 mark_key_failure 没接**（见下文 P8 已知缺口）。

### P8 已知设计缺口（验收后决定是否补）

- 聊天流式失败（`agent_ws.py` 的 `except Exception` 分支）目前不区分鉴权失败与网络失败，**没有调 `mark_key_failure`**——多 Key 轮换对聊天路径只轮换不熔断。补法：`_run_turn_inner` 捕获异常时检查是否 `httpx.HTTPStatusError` 且 status in (401,403,429)，是则 `mgr.mark_key_failure(本次用的 key_row_id)`。难点：Key 行 id 在 `get_chat_model` 内部选中，没往外传——可能要给 Agent 实例加 `last_key_row_id` 属性。
- 全部 Key 冷却时 `resolve_api_key` 抛 RuntimeError（中文），聊天会显示通用错误提示，可接受但可在 `agent_ws.py` 特判给更明确文案。

## 三、剩余工作（按建议顺序）

全部详案在 **[providers-ui-plan.md](./providers-ui-plan.md) 第六节（P5–P9）**，以下是执行视角的摘要：

### 1. P8 收尾（见上，半天内）

### 2. P9：四类新能力集成（工作量最大，可拆三笔独立提交）

按依赖顺序做，每完成一项放开一个 Tab：

- **P9a 嵌入/Rerank 走 Provider 体系**（依赖 P5）：
  - 现状：RAG 嵌入用 `.env` 的 `EMBEDDING_API_KEY/BASE_URL/MODEL`（`core/knowledge_base/` 下 EmbeddingClient），rerank 用 `ENABLE_RERANK`+SiliconFlow。
  - 目标：先查 `capability=embedding` 的默认 Provider，查不到回落 `.env`（读时兼容，P5 详案有写）。
  - ⚠️ 先做 P5 的 `capability` 列迁移，否则嵌入/rerank 无源可查。

- **P5 能力维度**（P9 的地基，必须最先做）：
  - `ProviderConfig` 加 `capability` 列（默认 `chat`，迁移注意存量兼容）；
  - `is_default` 部分唯一索引升级为 `(user_id, capability)` 维度（迁移前先按组去重，参照 `e7f8a9b0c1d2` 的做法）；
  - 列表/新增/PATCH 带 capability 过滤；
  - 前端 `CAPABILITY_TABS` 的 `enabled` 放开 + `useProviders` 查询参数化（缓存 key `["providers", capability]`）。

- **P9b STT（语音转文字）**：聊天输入框语音按钮 → 录音（MediaRecorder）→ 上传 → 新端点 `POST /agent/audio/transcriptions`（后端调 STT 上游，openai 兼容 `audio/transcriptions`）。

- **P9c TTS（文字转语音）**：回复气泡「朗读」按钮 → `POST /agent/audio/speech` → 前端 Audio 播放。先整段合成，不做流式。

### 3. 顺手项

- 详情面板「类型」行是只读（后端 PATCH 不支持 provider_type）——若要支持需后端加字段+前端解禁。
- 「可用模型 N」计数目前不含搜索过滤，符合预期。

## 四、关键代码地图

| 位置 | 职责 |
|---|---|
| `backend/app/api/routes/providers.py` | 全部供应商路由（CRUD/余额/模型清单/密钥，_get_owned_provider 归属校验范式） |
| `backend/app/core/agent/provider.py` | ProviderManager：`get_chat_model`（高级配置+Key 轮换接线、缓存键签名）、`resolve_api_key`/`mark_key_failure/success`、create/update 的密钥行同步 |
| `backend/app/core/agent/provider_models.py` | 上游 /models 拉取（三协议适配） |
| `backend/app/core/agent/provider_balance.py` | 余额查询（4 厂商适配器） |
| `backend/app/core/db/models.py` | ProviderConfig（config JSON 三键 property）/ProviderModel/ProviderKey |
| `backend/app/alembic/versions/` | `c5d9e2a4b8f1`（模型表）→ `e2f6b3c7a9d4`（密钥表，含回填）＝ 当前 head |
| `frontend/src/components/Providers/ProviderSettings.tsx` | 整页：Tab 栏/列表/详情（SettingRow）/ModelsSection/ProviderKeysPanel/AddProviderDialog |
| `frontend/src/hooks/useProviders.ts` | 查询与三写操作（缓存 key `["providers"]`） |
| `frontend/tests/` | e2e；`agent-pages.spec.ts` 有 provider-row/balance 的按行定位断言（改 UI 前先看） |
| `tests/api/routes/test_provider_*.py` | advanced/models/keys 三套测试（_patch_client monkeypatch 范式在 test_provider_models.py） |

## 五、近期踩坑速查（都在 PROGRESS.md 有详细留档）

1. 迁移里 `index=True` + 显式 `create_index` 同名 → DuplicateTable，prestart 挂（`8da4c50`）。
2. 测试 monkeypatch `httpx.AsyncClient` 必须模块级捕获原类一次，函数内捕获会嵌套递归且「第一个 handler 永远生效」。
3. httpx 0.28 的代理在 `_mounts` 传输层上（`transport._pool._proxy_url`），不在顶层属性。
4. e2e 切普通用户要 `test.use({ storageState: { cookies: [], origins: [] } })`。
5. `playwright test | tail` 退出码恒 0，结果必须落盘看。
6. IAB 浏览器自动化里按钮 `.click()` 常超时，用 `locator.evaluate(el => el.click())` 兜底；同名按钮用 `{ name: "x", exact: true }`。

## 六、验证命令速查（Git Bash）

```bash
# 后端测试（根 .venv）
cd backend && POSTGRES_SERVER=localhost ../.venv/Scripts/python.exe -m pytest ../tests/api -q

# 前端
cd frontend && npx tsc -p tsconfig.build.json --noEmit && npx vite build
npx playwright test tests/agent-pages.spec.ts --workers=1 --reporter=line

# client 再生成（改了后端路由后）
cd backend && ../.venv/Scripts/python.exe -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../frontend/openapi.json
cd ../frontend && npm run generate-client

# 容器重建（迁移也会跑）
docker compose up -d --build backend
```

## 七、交接检查单（接手后先做）

- [ ] 读 `plan/PROGRESS.md` 第十节（近三天进度）与 `plan/providers-ui-plan.md` 第六节
- [ ] `docker compose ps` 确认栈健康；`curl http://127.0.0.1:8000/api/v1/utils/health-check/` 200
- [ ] P8 实机验收（第二节「P8 收尾未做」）
- [ ] P8 PROGRESS.md 留档 + commit
- [ ] 决定是否补聊天路径的 mark_key_failure（P8 已知缺口）
- [ ] 按 P5 → P9a → P9b → P9c 顺序推进，每小功能一 commit
