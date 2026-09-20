# IrsBot 日志与控制台功能实施计划

> 版本：v1.1 ｜ 日期：2026-09-21 ｜ **状态：✅ 已全部完成（2026-09-21 实机验收）**
> 上游文档：[istbot-implement-plan.md](./istbot-implement-plan.md)（全局规划）｜ [PROGRESS.md](./PROGRESS.md)（运行态）
> **本文档只覆盖一件事：为 IrsBot 增加运行时日志体系 + 网页端「控制台」页（实时查看后端日志）。**
>
> 依据：
> - `istbot-implement-plan.md` §8.6 迁移清单保留项：**「16.3 日志分级与脱敏（api_key 不进日志）🔶 保留在本项目」**（本计划 Phase L1 落地）。
> - §6.1 能力矩阵 #27「日志分级与敏感信息脱敏」P2。
> - 用户 2026-09-20 提出需求：「为项目添加日志与控制台功能」。

---

## 〇、定位与目标（一句话）

**让使用者在网页上有一个「控制台」页：实时看到后端运行日志（分级、可过滤、可搜索、自动滚动），且日志中的敏感信息（API Key / Token）保证脱敏。**

| 目标 | 非目标（本轮不做） |
|---|---|
| ✅ 后端统一 logging 配置 + 内存环形缓冲 | ❌ 日志落库（DB 表）/ 日志文件轮转 —— 容器 `docker compose logs` 已覆盖持久化诉求 |
| ✅ 敏感信息脱敏（api_key、Bearer Token、`enc:v1:` 密文） | ❌ 日志导出下载（后续可加） |
| ✅ `GET /api/v1/logs` 轮询 API（仅 superuser） | ❌ WebSocket/SSE 实时推送 —— 2 秒轮询对本机单用户足够，复杂度不进主栈 |
| ✅ 前端 `/console` 控制台页（侧边栏入口、superuser 守卫） | ❌ 普通用户可见日志（本机单用户场景无此需求，多租户模式下天然由 superuser 守卫挡住） |
| ✅ 后端 pytest + 前端 Playwright（8000 实机）全覆盖 | ❌ 审计日志（谁在何时改了什么）—— 与运行日志是两回事，后续另立 |

---

## 一、现状盘点（2026-09-20 实查）

| 项 | 现状 |
|---|---|
| logging 配置 | **无统一配置**。仅 `logging.getLogger(__name__)` 零散使用（`agent_ws.py`、`pipeline/hooks.py`、`reranker.py`、scripts），输出全靠 uvicorn 默认 |
| 敏感信息 | `provider_balance.py` 等处已有「不打印明文 Key」的自觉，但**无系统性脱敏过滤器**；api_key 加密落库（`enc:v1:`） |
| 前端页面 | 无任何日志相关页。已有 admin 页（superuser `beforeLoad` 守卫 + redirect 范式可复用）、stats 页 |
| 侧边栏 | `components/Sidebar/AppSidebar.tsx`，已有「管理」入口（admin） |
| 端口形态 | **单端口 8000**：backend 托管 `frontend/dist`（SPA fallback），e2e baseURL=`http://127.0.0.1:8000`（2026-09-20 已纠偏，**严禁回退 5173 dev server**） |

---

## 二、设计决策

| # | 决策 | 理由 |
|---|---|---|
| **C1** | 日志用**进程内内存环形缓冲**（`collections.deque(maxlen=2000)` + 自定义 `logging.Handler`），不落库、不写文件 | 单机单用户，2000 条足够回看；持久化交给 `docker compose logs`；避免为日志建表/迁移 |
| **C2** | 前端拿日志走 **HTTP 轮询**（`after_id` 增量拉取，2s 间隔、可暂停） | 本机场景 WS/SSE 属过度设计；`agent_ws.py` 的 WS 是对话专用协议，不复用不混入 |
| **C3** | 脱敏做在 **logging.Filter 层**（对所有经过 handler 的记录统一处理），不逐处改调用点 | 「api_key 不进日志」必须是兜底保证，不能依赖每个开发者自觉 |
| **C4** | 权限 = **仅 `is_superuser`**（与 `/admin` 页一致）；多租户模式下普通用户 403 | 复用现有 superuser 守卫范式，前后端双层 |
| **C5** | 级别开关 `LOG_LEVEL` 进 `core/config.py`（默认 `INFO`），环形缓冲**全量收集**（DEBUG 也进缓冲），前端再按级别过滤 | 后端不重启就能改前端看到的内容；过滤逻辑放前端 |
| **C6** | API 形态：`GET /api/v1/logs?after_id=&level=&q=&limit=` → `{ items, latest_id }` | `after_id` 增量 = 轮询高效；`level`/`q` 服务端过滤可选，初版可全量+前端过滤 |

---

## 三、任务分解（Phase L1–L4）

### Phase L1 — 后端日志基建（`backend/app/core/logging.py`）

- [x] **L1.1 统一配置**：`setup_logging()`（idempotent，`main.py` 启动时调用一次）：
  - root logger 级别取 `settings.LOG_LEVEL`（config 新增 `LOG_LEVEL: str = "INFO"`）；
  - 统一格式：`%(asctime)s %(levelname)s %(name)s %(message)s`；
  - 接管 uvicorn / uvicorn.access logger（propagate 关闭 → 自有 handler），否则访问日志不进环形缓冲。
- [x] **L1.2 环形缓冲**：`RingBufferHandler(logging.Handler)`：
  - 每条记录赋**进程内单调递增 `record_id`**（轮询游标）；
  - `deque(maxlen=2000)`，元素为 `{id, ts, level, logger, message}`；
  - 线程安全（`threading.Lock`；uvicorn 是 asyncio 但 logging 调用可能来自任意线程/工具子进程回调）。
- [x] **L1.3 脱敏过滤器**：`SensitiveDataFilter`（挂在 handler 上，`emit` 前处理）：
  - 正则覆盖：`sk-[A-Za-z0-9_-]{8,}`、`Bearer <token>`、`api_key=...` / `api-key: ...`、`enc:v1:...` 密文前缀；
  - 命中替换为 `***REDACTED***`（保留前 4 后 0 位，不回显部分明文）；
  - **纯函数实现**（`redact(text) -> str`），便于单测穷举。
- [x] **L1.4 埋点补课**：给关键路径补 `logger.info/error`（Provider 余额查询、KB 上传/删除、Agent 轮次开始/结束、登录成功/失败），让控制台页一打开有内容可看。

### Phase L2 — 日志 API

- [x] **L2.1** `backend/app/api/routes/logs.py`：
  - `GET /api/v1/logs`：query 参数 `after_id: int = 0`、`limit: int = 500`；
  - 返回 `LogsOut { items: [LogEntry], latest_id: int }`；
  - `Depends(get_current_user_superuser)`（与 users 管理端点同款依赖）；
  - `api/main.py` 注册 router（tag `logs`）。
- [x] **L2.2** 重新生成前端 client（`scripts/generate-client.sh` 对应流程），`src/client` 出 `LogsService`。
- [x] **L2.3** 测试 `tests/api/routes/test_logs.py`：
  - 匿名 401 / 非 superuser 403 / superuser 200；
  - `after_id` 增量语义（只返回更大 id）；`limit` 截断；环形缓冲溢出后旧行为；
  - 脱敏端到端：往 logger 写一条含 `sk-xxx` 的记录，API 返回中不出现明文。

### Phase L3 — 前端控制台页

- [x] **L3.1** 路由 `routes/_layout/console.tsx`：
  - `beforeLoad` 复用 admin.tsx 范式：非 superuser `redirect({ to: "/" })`；
  - `<Outlet/>` 教训不适用（叶子路由），但注意 **新路由文件首跑必须先 `npx vite build` 生成 `routeTree.gen.ts`，否则 tsc 报「路由不存在」**。
- [x] **L3.2** 组件 `components/Console/LogConsole.tsx`：
  - 轮询 hook `useLogStream`（`enabled` 可暂停；`after_id` 游标追加；2s 间隔，页面隐藏时 `document.visibilityState` 暂停）；
  - 视图：级别彩色徽标（ERROR 红 / WARNING 黄 / INFO 蓝 / DEBUG 灰）、级别过滤 chips、关键字输入、自动滚动（用户上滚即暂停自动滚动）、「暂停 / 继续」「清屏（仅前端视图）」；
  - 等宽字体、暗色底（终端观感），沿用 shadcn 既有 token。
- [x] **L3.3** 侧边栏入口：`AppSidebar.tsx`「管理」组下加「控制台」（Terminal 图标），与 admin 入口同款 superuser 可见逻辑（如现有 admin 入口未做条件可见则保持一致，不强改）。
- [x] **L3.4** zod/文案遵循项目约定：所有界面与校验文案用中文。

### Phase L4 — 测试、构建与实机验收

- [x] **L4.1 后端全量**：`pytest ../tests -q`（宿主）；脱敏纯函数单测另立 `tests/core/test_logging_redact.py` 穷举正则边界（空串/多 Key 同行/超长 token）。
- [x] **L4.2 前端构建**：先 `npx vite build`（生成 routeTree）→ `tsc -p tsconfig.build.json --noEmit` → `npm run build`。
- [x] **L4.3 Playwright e2e**（baseURL **`http://127.0.0.1:8000`**，`webServer` 块已删不许加回）：
  - superuser 登录 → `/console` 可见、日志条目渲染；
  - 非 superuser 访问 `/console` → 重定向首页；
  - ⚠️ 跑前确认空闲内存 ≥ 2GB（不足时 Chromium 大面积 30s 超时），必要时 `--workers=1`；⚠️ `playwright test | tail` 退出码恒 0，结果落盘再看。
- [x] **L4.4 容器同步与实机验收**：`docker compose up -d --build backend`（⚠️ `up -d` 不触发 `develop.watch`）→ 实机 `http://localhost:8000/console`：
  - 打开控制台能看到启动日志（prestart 之后 uvicorn 启动记录）；
  - 触发一次对话/查余额，新日志 2s 内出现；
  - 在模型源页故意触发一次失败查询，确认 ERROR 级别红色徽标；
  - 全链路日志中 grep `sk-` / `Bearer` 无明文泄露（在 API 返回 JSON 上验证，而非终端）。
- [x] **L4.5 文档收尾**：PROGRESS.md 待办表追加本计划条目 + 进度记录追加一行；本计划勾选状态。

---

## 四、验收标准（全过才算闭环）

1. `pytest ../tests -q` 全绿（Milvus 环境噪音除外，需单独说明）；
2. `tsc --noEmit` ExitCode 0；`npm run build` 成功且 `/console` 独立 chunk 出现；
3. Playwright 新增用例全过（8000 实机 dist，非 dev server）；
4. 实机 8000：控制台页实时滚动日志、过滤/搜索/暂停可用、刷新不掉线；
5. **安全红线**：API 返回的日志 JSON 中 grep 不到任何 `sk-` 开头明文 Key、`Bearer` 后明文 token、`enc:v1:` 密文。

---

## 五、风险与坑位登记（本项目实测沉淀，施工前必读）

| # | 坑 | 应对 |
|---|---|---|
| 1 | **单端口 8000**：backend 托管 dist；e2e/验收一律打 8000，vite dev server 的 5173 严禁作为被测对象（IPv6 `::1` 代理坑） | playwright.config baseURL 已是 `http://127.0.0.1:8000`，勿回改 |
| 2 | **新路由 tsc 先报错**：`routeTree.gen.ts` 由 vite 插件生成 | 先跑一次 `npx vite build` 再 tsc |
| 3 | **容器同步**：`docker compose up -d` 不含 `develop.watch`；改码后必须 `up -d --build backend` 或另开 watch 终端 | 验收前 `docker compose exec backend grep` 确认新代码已进容器 |
| 4 | **测试库安全阀**：conftest 只允许 `test_app` 库（曾发生真实库被清空事故） | 新测试沿用现有 fixtures，绝不 `POSTGRES_DB=app` 起进程 |
| 5 | **uvicorn 日志旁路**：uvicorn 自己配 handler，root logging 配置不接管就看不到 access log | `setup_logging()` 显式处理 `uvicorn`/`uvicorn.access`/`uvicorn.error` |
| 6 | **uvicorn reload 的 mtime 坑**：`docker cp` 旧版本文件不触发重载 | 验收一律走镜像重建，不走 docker cp 灌码 |
| 7 | **PowerShell stdout 不回显** | 命令输出一律 `Out-File` 落盘再 Read |
| 8 | **e2e 内存不足假失败** | 跑前查 `wmic OS get FreePhysicalMemory` |
| 9 | **脱敏正则误伤**：日志里合法出现的「sk- 开头用户聊天文本」会被改写 | 可接受（控制台是运维视角，非数据视图）；单测锁定行为即可 |
| 10 | **环形缓冲并发**：logging 可能来自任意线程（工具子进程回调） | Handler 内 `threading.Lock`，不赌 GIL |

---

## 六、依赖与顺序

```
L1 (基建) ──→ L2 (API) ──→ L3 (前端页) ──→ L4 (测试/构建/实机/文档)
```

L1.3 脱敏与 L1.2 缓冲可并行开发；L2.2（client 再生成）是 L3 的前置。预计改动面：
后端新增 2 文件 + 改 3 文件（`main.py`/`config.py`/`api/main.py`）+ 测试 2 文件；前端新增 2 文件 + 改 2 文件（`AppSidebar.tsx`、client 再生成）。
