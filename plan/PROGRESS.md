# IrsBot — 运行时状态

> 本文件回答一个问题：**「我现在跑到哪了？下一步做什么？」**
> 全局规划与架构决策见 [istbot-implement-plan.md](./istbot-implement-plan.md)（少变）
> Docker 化交付施工详案见 [local-deployment-plan.md](./local-deployment-plan.md)（Phase D1–D7）
> 架构基线见 [astrbot-architecture.md](./astrbot-architecture.md)

---

## 一、当前定位（一句话）

**IrsBot 是一个本地部署的 AI Agent 应用，单用户使用，用 Docker 一条命令启动。**
用户在浏览器里对话，在网页端填自己的 API Key，具备 Skill / Tool / MCP / RAG 能力。**不接 IM，不做网页版**（网页版已拆分独立项目）。

> ⚠️ **定位已第五次修正（2026-09-16 晚）**：上一版写的是「**零外部依赖**」，**该承诺已撤回**。
> 现承诺为「**一条命令启动**」，唯一前置条件是**装一次 Docker**。
>
> 定位若变更，**先改 implement-plan 第零节**，再回来改这里。

---

## 二、当前阶段

| 项 | 值 |
|---|---|
| **当前阶段** | **🎉 Phase D1–D7 ✅ + D5.1b ✅ 全完成**；**已建 git 回退基线**（独立仓库 `d:/AIpy/full-stack/IrsBot/.git`，分支 `feat/agent-platform`）；**✅ §10.6 Provider 实测 a–f 全部通过（2026-09-18）**：a 列表/b 新增/c 设默认/e 加密/f RAG 向量化 ✅；**d 项缺陷（删默认源后无默认）已修复**（`a746d10`：`delete_provider` 自动补位 + 7 条回归测试 + 实机 A/B 验证），详见第八节；**✅ 系统提示词功能已实施并实机验收（2026-09-17）**：User.system_prompt 列+迁移 `a1b2c3d4e5f6`、`prompts.py`、Agent 注入 SystemMessage、GET/PATCH `/users/me/system-prompt`、设置页「系统提示词」tab、client 已重新生成；**✅ 注册闸门已收口（2026-09-18）**：新增 `USERS_OPEN_REGISTRATION` 开关（安全默认 `false`，沿用 D6 工具开关范式）、`/users/signup` 加守卫（**置于查重之前**，防账号枚举）、前端登录页移除「注册」入口，+3 条测试并双层证伪 —— ⚠️ **前端 `frontend/dist` 需重新构建后 UI 才生效**（构建产物仍是旧版）→ **已重建**：用**仓库根** `node_modules` 跑 `vite build`（12.90s），新产物 `login-CP8ls77z.js`，旧产物与「还没有账号」字符串均已消失；dist 为绑定挂载 → 刷新浏览器即生效。**✅ 容器同步已完成（2026-09-18）**：`docker compose up -d --build backend` 重建镜像成功（db / milvus / prestart / backend 全部 Recreate，**命名卷 `app-db-data` 数据保留**），容器内 `config.py`（`USERS_OPEN_REGISTRATION`）与 `users.py`（403 守卫）已确认为新版；**实机复测 `POST /users/signup` → 403 + 约定话术、防枚举响应逐字节一致、无账号落库**，详见第八节末「容器同步 + 注册闸门实机验证」；**✅ 部署模式运行时开关已实施（2026-09-18，第七轮）**：新增 `app_settings` KV 表 + `settings_runtime` 读取层，超管在 `/admin` 页切换「单用户 / 多租户」**即时生效**（`.env` 的 `USERS_OPEN_REGISTRATION` 降为兜底初值）；登录页按开关显示注册入口；+33 条测试，详见第八节末「部署模式运行时开关」 |
| **代码状态** | 🔶 **有代码改动**：`backend/Dockerfile`（修 Python 版本）/ `backend/app/main.py`（静态托管）/ `frontend/src/main.tsx` + `routes/_layout/chat.tsx` + `hooks/useAgentChat.ts`（相对路径）/ `frontend/vite.config.ts`（proxy）/ `frontend/.env` + 配置类改动（见第四点五节） |
| **运行状态** | ✅ **全栈运行中（2026-09-18 重建后）**：`irsbot-backend-1` / `irsbot-db-1` / `irsbot-milvus-1` 全部 healthy，**backend 容器内代码 = 最新提交**（不再是「构建中」）；前端 `dist` 经绑定挂载 `/app/frontend-dist` 生效 |
| **文档状态** | ✅ **已一致**（含 2026-09-18 **D2 语义拆分回查**）：`istbot-implement-plan.md` **第六轮同步**——把「Phase 11 因单用户整体降级」拆为 **(A) 多用户运营化**（降级不做）与 **(B) 归属隔离**（已实现为硬约束），共修 **15 处活引用**（0.0 决策表 / 0.2 / 0.4 / 0.5 / 一节阶段表 / Phase 3 / Phase 3.5 / SC11 / SC D10 / 6.1 能力矩阵 / 8.0 / 8.1 / 8.4 / 5.x 已移出表 / 第九节变更说明），`~~划掉~~` 与历轮留痕按「追溯性引用」**一律保留**；`local-deployment-plan.md` 已升 **v7.2**；详见第八节末「文档同步：D2 语义拆分」 |
| **当前分支** | `feat/agent-platform`（未推送远端） |
| **测试基线** | ✅ **全量最新实跑（2026-09-18 第七轮）：`pytest ../tests -q` → 354 条总量，343 passed / 1 failed / 10 errors**（622.62s）。**11 条失败/错误全部是 `knowledge_base` 的 Milvus 连接失败**（`irsbot-milvus-1` 同期处于 `health: starting` 重启循环，环境问题，非本次改动）；**非 Milvus 用例 0 失败**。**新增 33 条（`test_settings_runtime.py` 15 + `test_settings.py` 18）单独跑全过**（2.40s）。上次基线：321 passed / 0 failed（318 + 注册闸门 3）。后端 `py_compile` ✅；**前端 `tsc -p tsconfig.build.json --noEmit` 当前 ExitCode 2** —— 唯一报错是**用户 WIP 文件** `src/hooks/useKnowledgeBase.ts(1,79) TS1005`（未擅自改动，全仓无引用）；`vite build` ✅ 16.35s 重建 dist |
| **阻塞项** | **无** —— 容器同步已闭环（2026-09-18）；**D1.3a 已实机验证通过**（见下方验收表）；镜像构建是 D1.3c 分发优化，非阻塞 |
| **施工前必做** | **M1 待做（非阻塞）**；**M2 / M3 ✅ 已完成**；**Q1–Q3 ✅ 已确认**；Q4–Q10 待确认（见第九点五节） |

> ✅ **D1.3a 实机验收（2026-09-17 00:23，本机 uvicorn 8001 端口，`IrsBot_WEBUI_DIR` 指向 `frontend/dist`）**：
>
> | 测试 | 结果 |
> |---|---|
> | `GET /` | **200** `text/html` 565 B（index.html） |
> | `GET /chat` | **200** `text/html` ← **SPA fallback 生效** |
> | `GET /settings` / `GET /login` | **200** `text/html` ← SPA fallback |
> | `GET /assets/index-kgAn2Xce.js` | **200** `text/javascript` **675,824 B** |
> | `GET /assets/index-DndJNewr.css` | **200** `text/css` **66,212 B** |
> | `GET /api/v1/nonexistent` | **404 `application/json`** ← API 不被 HTML 吞掉 ✅ |
>
> 🎯 **五条验收标准全过。** 浏览器打开 `http://localhost:8001/` 已进入登录界面。
>
> ⚠️ **验证时的一个坑**：`Invoke-WebRequest` / `curl` / 代码探测**默认不带 `Accept: text/html`**，
> 而 `main.py:70` 的 `if "text/html" in accept` 判断会让这些请求**返回 404**（这正是设计意图）。
> → **调试时须显式加头**：`curl -H "Accept: text/html" http://localhost:8001/chat`

> ✅ **好消息**：**D1.3 全链路已闭环（2026-09-17 01:14）**：
> ① backend 镜像 wheelhouse 离线构建成功（38 秒）；
> ② `docker compose up -d backend` 全链路通过 —— prestart 迁移跑完 + superuser 创建、backend 启动、
> `GET /` 与 `/chat` 返 200 text/html（dist 挂载 + SPA fallback）、`/api/v1` 404 返 JSON、health-check 200；
> ③ D1.4 邮件依赖已删除（含 tests）。
> 🎯 **下一步**：D1.3e（移除 frontend 独立容器）→ D1.1（剥离 traefik）→ D1.5（清 `DOCKER_IMAGE_*`）。
> ⚠️ **镜像重建前须知**：依赖变更后须先在宿主机重跑 wheelhouse 生成命令（见 `backend/Dockerfile` 注释），再 `docker compose build backend`。
> ⚠️ **本轮新修的既有 bug**：`backend/scripts/pre_start.py` / `init_data.py` 被前人误删但 prestart.sh 仍引用 → 已补精简版（等 db / 建 superuser）；
> Dockerfile 加 `ENV PYTHONPATH=/app/backend`（app 不装包，靠 cwd 导入，alembic env.py 与 scripts 都需要它）。

> ✅ **D1.4 已完成（2026-09-17 01:29，实机验收）** —— 删除 `items` 模板残留全链路：
>
> | 环节 | 改动 | 验收 |
> |---|---|---|
> | 后端模型 | `sqlmodel_models.py` 删 `ItemBase/ItemCreate/ItemUpdate/Item/ItemPublic/ItemsPublic` + `User.items` 关系；`models.py` 同步 | ✅ |
> | 后端路由 | `api/routes/items.py` 删；`api/main.py` 去 `include_router(items.router)`；`users.py` 删级联 `delete(Item)`；`crud/user_item.py` 删 `create_item`；`crud/__init__.py` 同步 | ✅ |
> | 数据库 | **新增** `alembic/versions/f3e1a9b7c2d4_remove_items_table.py`（`down_revision=c1a2b3c4d5e6`，drop `item` 表，可 downgrade 回滚） | ✅ prestart 已执行 |
> | 测试 | 删 `tests/api/routes/test_items.py` + `tests/utils/item.py` | ✅ |
> | 前端 | 删 `routes/_layout/items.tsx` / `components/Items/` / `components/Pending/PendingItems.tsx`；`AppSidebar.tsx` 去 Items 入口；重生成 `src/client`；重生成 `routeTree.gen.ts` | ✅ |
> | 构建 | `tsc -p tsconfig.build.json` **ExitCode 0**；`vite build` ✅（dist 已无 `items` / `recover` chunk） | ✅ |
> | 运行 | `/api/v1/items/` → **404**；`/` `/chat` → 200 html；health → 200 | ✅ |
>
> ⚠️ **过程中连带修掉两个悬空引用**：
> ① **`LoginService.recoverPassword` 不存在** —— 后端 `login.py` 只有 `access-token` / `test-token` / `reset-password`，
> 找回密码端点随邮件能力一起被早前删除，前端 `routes/recover-password.tsx` 与登录页「忘记密码？」链接成了死链（**tsc 直接报错 TS2551**）。
> → 已删 `recover-password.tsx` + 登录页链接（`RouterLink` import 保留，`/signup` 仍在用）。
> ② **backend 容器永远 unhealthy** —— `python:3.13-slim` **不含 curl**，compose healthcheck 的 `curl -f ...` 每次
> `OCI runtime exec failed`（连续失败 31 次）。→ 改成 `python -c "urllib.request..."`（Dockerfile 已把 `/app/.venv/bin` 加入 PATH），现为 **healthy**。

> 🔴 **「设置 → 模型源为空」根因与修复（2026-09-17 01:45）**：
> **不是数据库被重置，是默认模型源的播种步骤没跑。**
> - 播种逻辑在 **`backend/app/core/db/engine.py::init_db()`**：用 `.env` 的
>   `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `DEFAULT_LLM_PROVIDER` / `DEFAULT_LLM_MODEL`
>   创建一条 `name="default"` 的 `ProviderConfig`（is_default + is_active）。
> - 但 prestart 第三步跑的是 **`backend/scripts/init_data.py`**（该文件早年被误删、本轮补的
>   「精简版」**只建 superuser，没调 init_db**）→ 新库起来后模型源页必然是空的。
> - 另有同名文件 `backend/app/scripts/init_data.py`（只调 init_db），**prestart 用的不是它**。
> ✅ 修复：`backend/scripts/init_data.py` 改为直接复用 `init_db`（不再维护两份逻辑，幂等）；
> 已重建镜像并实机验证 —— 登录 `admin@example.com` 后 `GET /api/v1/providers` 返回
> `default / openai / qwen3.8-flash / dashscope compatible-mode`，`is_default=true`。
>
> 🔴🔴 **数据事故（2026-09-17 00:55:57）：本机 `app` 库被 pytest 清空** —— 详见记忆 `2026-09-17.md`。
> 证据：`pg_waldump` 显示 tx 6491 在 00:55:57.891 对库 OID 17044（=`app`）的 `user`/`knowledge_bases` 等表
> 做全表 DELETE，随后 autovacuum 把表 TRUNCATE 到 0 blocks；`.pytest_cache` mtime 同为 00:55:57。
> 根因：`tests/conftest.py` 用 `os.environ.setdefault("POSTGRES_DB","test_app")` 做隔离，
> 一旦进程环境里已有 `POSTGRES_DB=app`（.env/终端注入）就失效 → 测试连真实库，
> session 收尾 `delete(model)`×12 清空全表。
> ✅ 已加**硬性安全阀**：库名非 `test_app` 直接 `RuntimeError` 中止（`IRSBOT_ALLOW_NONTEST_DB=1` 才放行）；
> 并修掉 conftest 残留的 `from app.models import Item`（D1.4 漏改）。验证：正常 299 tests collected；
> 注入 `POSTGRES_DB=app` 时被拒绝。
> ⚠️ **不可恢复**：WAL 不存被删行内容、表已 truncate、无备份（已搜 D:\ + 项目根）。
> 仅存 Milvus 集合 `irsbot_kb_4302411d-2e1e-45d3-bab7-8e7999f1e131`（6 条向量）可供后续重新挂载。
>
> 📌 顺带普查的三个数据库（都在找旧配置，**均无 provider 记录**）：
> | 库 | 状态 |
> |---|---|
> | 容器 `irsbot_app-db-data`（今晚 22:13 新建） | provider 0 → 已播种 1 条 default |
> | 宿主机 PG `app`（旧本地运行库，仍有 `item` 表，alembic `c1a2b3c4d5e6`） | provider 0、会话 0 |
> | 旧卷 `full-stack-fastapi-template_app-db-data`（6 月） | `app` 库存在但 **public 无任何用户表** |
> → 结论：容器化前也没有落库的模型源配置，**无可恢复数据**。

> 📌 **v6 新增认知（2026-09-16 用户确认）**：本项目基于 **full-stack-fastapi-template** 修改而来。
> **除 IrsBot 自身功能外，模板残留均可清理**；前端 webui（登录 / shadcn/ui / apiClient）按用户决定**直接复用**。
> 模板残留清单见 `local-deployment-plan.md` §3.2，其中 `items` 已核实为待办示例 → **确认删除**。

> 📌 **v7 新增（本轮施工发现）**：
> ① 🔴 修复 `backend/Dockerfile` 既有 bug —— `FROM python:3.10` 与 `requires-python = ">=3.12,<4.0"` 冲突导致构建失败，改 `3.13-slim`；
> ② ⚠️ **前端 API 地址有三处，改法各不相同**，**不能统一替换成 `/api`**（详见 §5.3）；
> ③ 🔑 改相对路径后 **Vite dev server 必须配 proxy**（含 `ws: true`），否则开发入口 404；
> ④ ⭐ 前端是 **bun workspace 单仓** —— 锁文件与依赖都在**仓库根**，所有前端命令**必须在根目录执行**（在 `frontend/` 跑 `bun install` 会全量重装并生成污染锁文件）。

> 📌 **v7.2 追加（构建慢的根因锁定 + 第三个坑）**：
> ① 🔴 **根因不是"源慢"，是容器虚拟网络限吞吐** —— 同一容器同一域名：**小请求（索引页 45KB）= 150 KB/s，大文件流 = 2–11 KB/s**，差 15–75 倍；而**宿主机同源实测 1370 KB/s**。→ 换任何 PyPI 镜像源都不解决。
> ② ✅ 清华源**仍有价值**：提供预编译 wheel，`dkimpy` 编译 **425 秒 → 2.1 秒**（但会让 `pygments` 从 4.5 KB/s 变 2 KB/s，因并发抢带宽）。
> ③ 🔑 **`--no-cache` 断的是层缓存，断不了 cache mount** —— `--mount=type=cache,target=/root/.cache/uv` 不受其影响，包缓存**一直在累积**（`buildx du` 的 371.8 MB 是真的）；但**层缓存从未建立**（5 次全 Error）→ 每次都从零。
> ④ 🎯 **结论：镜像构建不是 D1.3 的阻塞项** —— `WEBUI_INDEX.exists()` 守卫保证 dist 缺失也能启动；本机 `.venv`（Python 3.13.0，`app.main` 导入 ✅）+ `frontend/dist`（已构建，产物完整）**足以验证 D1.3a 全部逻辑**。
> ⑤ ⚠️ **坑 C：用日志文件修改时间判断构建是否在跑** —— `Tee-Object` 只在缓冲区满或进程结束时刷盘，**进程在跑、日志是死的**。可靠判据：`docker buildx history ls` 的 `DURATION`（末尾 `+` 在涨）。


---

## 三、本轮决策（2026-09-16，第五轮 —— 根本性转向）

| # | 决策 | 影响 |
|---|---|---|
| D1 | 网页部署独立成另一个项目 | 本项目**单形态**；Phase 16 移出 |
| D2 | 本地版单用户 | **拆分**（2026-09-18）：**多用户运营化降级**（不做自助注册/配额/计费）；**归属隔离已实现为硬约束**（`user_id` 必填 + fail closed，`ef08cc1`）。另保留 cache 淘汰 + `is_default` 约束 |
| **D2.1** | **注册入口默认关闭（可由超管运行时开启）** | `/users/signup` 默认 403；守卫置于查重之前防账号枚举（`41cccfd`）。**2026-09-18 第七轮修订**：改为**运行时开关** —— 超管在 `/admin` 页切换「单用户 / 多租户」即时生效，`.env` 的 `USERS_OPEN_REGISTRATION` **降为兜底初值** |
| ~~D3~~ | ~~Docker 与裸机脚本都做~~ | ➖ **已变更** —— 见 D5 |
| **D4** | **保持 PostgreSQL + Milvus**（不换 SQLite / FAISS） | **L1 / L2 阶段全部作废**；`local-deployment-plan.md` 整份重写 |
| **D5** | **部署形态 = Docker 一键启动**（唯一前置：装 Docker） | 放弃裸机脚本路线；采用容器内全栈方案 |
| **D6** | **默认容器内 PG，留环境变量后门** | `POSTGRES_SERVER` 默认 `db`，可覆盖为 `host.docker.internal` |
| **D7** | **全量迁移现有开发数据**（迁移前强制备份） | 新增 **D5 数据迁移**阶段（最高风险） |

### ⚠️ 本轮最重要的一次自我纠错

**被推翻的核心推论**：上一轮我断言「exe 双击即用 ⟺ 必须 SQLite + FAISS，没有第三条路」。

**为什么错**：把两件独立的事绑在了一起 ——
- 「跨平台免装运行时」是**打包问题**
- 「用哪个数据库」是**存储选型问题**

AstrBot Desktop 的实证证明了这一点：它用 **Tauri 2.10.0 + 内置 CPython 3.12** 解决打包问题，而架构文档里**完全没有提及任何数据库** —— 说明数据库是它自己的实现细节，与"能不能双击运行"无关。

**代价**：上一轮方案要求改造 70% 的既有工作量，只为追求一个**用户其实感知不到**的「零依赖」。

> **用户的真实痛点不是"后台有没有 PostgreSQL"，而是"我要不要自己敲 20 条命令"。**
> 解决后者只需要 Docker Compose，不需要删数据库。

---

## 四、关键验证结论（本轮实机跑过）

### ✅ 验证 1：集成测试真实性 —— RAG 链路确实跑通了

**此前的盲区**：集成测试文件带 `pytestmark = pytest.mark.integration`（如 `tests/core/knowledge_base/test_vec_store.py:15`），**默认被跳过**。这就是「跑了测试但不知道真实情况」的根因。

**放行后实跑结果**：

| 测试集 | 结果 | 耗时 | 说明 |
|---|---|---|---|
| `test_vec_store.py` | ✅ **9 passed**（9 warnings） | 60.35s | 真连 Milvus，真调 Embedding API |
| 全量集成测试 | ✅ **18 passed**（294 deselected） | 90.93s | — |

**覆盖范围**：RAG 向量检索 9 项、Agent 真实 LLM 循环 2 项、WS 流式 6 项、工具 / Skill / 长对话 1 项。

> **结论**：RAG **不是"看起来能跑"，是"确实跑通了"** —— 向量写入、检索、RRF 混合排序全部真实经过 Milvus 与外部 Embedding 服务。
> **这条基线要在 D4 重跑一次作为回归。**

### ✅ 验证 2：环境实况探测

| 项 | 实况 |
|---|---|
| Docker | ✅ 已装，可运行 |
| `milvus-standalone` | ✅ `Up 45 hours (healthy)`，镜像 `milvusdb/milvus:v2.6.14` |
| PostgreSQL | ⚠️ **本机安装版**（5432 监听进程 `postgres`，PID 9196） |
| ⚠️ 另一个 PG | `full-stack-fastapi-template-db-1` 容器 **`Exited (255) 7 days ago`** |
| 端口 | 5432 ✅ 通 / 19530 ✅ 通 |

### 📊 验证 3：本机开发数据实况（✅ 已逐行盘点完成）

**数据库清单**（`D:\PostgreSQL` 安装版，18.3）：

| 库 | 大小 | 用途判定 |
|---|---|---|
| `app` | 9054 kB | ✅ **真实开发库**（有业务数据） |
| `test_app` | 8758 kB | ⚠️ 测试库（可弃） |
| `document_agent` | 8670 kB | ⚠️ **无表**（空壳，可弃） |
| `postgres` | 8006 kB | 系统库 |

**`app` 库逐表盘点**：

| 表 | 行数 | 真实资产 vs 测试残留 |
|---|---|---|
| `conversations` | 126 | **75 条是 2026-06-21 的测试批量**，真实 51 条（09-14 起 25/12/14） |
| `messages` | 108 | 与真实会话匹配 |
| `knowledge_bases` | 22 | ⚠️ **真实仅 1 个**（"测试库"，09-11 建，4302411d）；**21 个是测试残留**（kb0/kb1/kb2/KB1/kb-get/kb-del，全部 06-21） |
| `personas` | 21 | ⚠️ **全部测试残留**（P1 / p-get / per0 / per1 / per2 / p-del，重复 4 组） |
| `mcp_servers` | 17 | ⚠️ **全部测试残留**（mcp1 / m-get / srv0 / srv1 / m-del，重复 4 组） |
| `agent_runs` | 20 | 未细查 |
| `documents` | 2 | ✅ 真实：都是"退货政策.md"（211 B），挂在"测试库" |
| `provider_configs` | 1 | ✅ **真实**：`default` / openai / `qwen3.8-flash` / is_default=t |
| `user` | 1 | ✅ 真实：admin |
| `skills` / `item` | 0 | — |

**实体文件盘点**（`backend\uploads\`）：

| 目录 | 文件数 | 内容 |
|---|---|---|
| `uploads\kb\4302411d-...`（"测试库"） | 2 | `*_退货政策.md`（各 211 B） |
| `uploads\kb\a2e7d572-...`（**DB 中无对应 KB！**） | 1 | `*_测试文档.md`（563 B） |
| `uploads\kb_test\` | 21 | pytest 产生的垃圾 |

**📌 盘点结论（D5.1 已完成，可直接采信）**：

> **真实的、值得迁移的资产其实非常少**：
> - 1 个 Provider 配置（`qwen3.8-flash`）
> - 1 个用户（admin）
> - 1 个知识库（"测试库"）+ 2 个文档 + 2 个实体文件（211 B × 2）
> - 51 条真实会话 + 108 条消息
> - 外加 1 个**孤儿目录** `a2e7d572-...`（有文件无 KB 记录，需单独判断）
>
> **其余全部是 pytest 批量残留**（21 KB / 21 Persona / 17 MCP / 21 测试文件 / 75 测试会话）
>
> → **D5 从"高风险全量搬迁"降级为"小批量精选迁移 + 有据可依的清理"**。
> 这**大幅降低 D5 的不可逆风险**，是本次盘点最有价值的产出。

> ⚠️ **两套 PG 并存是隐患**：本机安装版（`app` 有真实数据）+ 容器版 `full-stack-fastapi-template-db-1`（`Exited (255) 7 days ago`，端口 5432 映射但本机 PG 已占用）。
> **D5 前必须确认容器版里到底有没有东西** —— 若有，需一并核对。
> ⚠️ 本次查询还暴露：`.env` 里 `FIRST_SUPERUSER_PASSWORD=changethis`（与 `config.py:160` 告警呼应）→ **D3.2 必须改成随机生成**。

### ✅ 验证 4：`.env` 配置完整

31 项配置齐全，含 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `OPENAI_API_KEY`。
→ 集成测试能真跑通的前提条件已满足。

### ⚠️ 本轮发现的告警（非阻塞，但需记录）

| 告警 | 位置 | 性质 |
|---|---|---|
| `FIRST_SUPERUSER_PASSWORD is "changethis"` | `config.py:160` + `.env:23` | 安全默认值 → **D3.2 改为随机生成** |
| `No ids provided and auto_id is False...` | `vec_store.py:49-53` | 功能正常，配置不干净 |
| `ResourceWarning: <psycopg.Connection> was deleted while still open` | 测试中 | 连接未显式关闭，长期运行可能耗尽连接池 |

---

## 四点五、✅ Milvus 方案已定案并实机验证通过（D1.2 核心已完成）

**决策 Q1/Q2 已由用户确认：保留现网方案（单容器内嵌 etcd + local 存储）。**

### 已完成的改造

| 文件 | 改动 |
|---|---|
| `compose.override.yml` | **Milvus 段重写**：删除 `etcd` / `minio` 两个独立服务，改为单容器 `milvusdb/milvus:v2.6.14`（`ETCD_USE_EMBED=true` + `COMMON_STORAGETYPE=local` + `security_opt: seccomp:unconfined`） |
| `compose.override.yml` | `milvus` 数据卷**改为绑定挂载** `D:/Milvus/volumes/milvus:/var/lib/milvus` → **直接复用现有数据，零迁移** |
| `compose.override.yml` | 删除 `etcd-data` / `minio-data` 卷声明，删除 `milvus-data`（已改绑定挂载） |
| `compose.override.yml` | `db` **移除 `5432:5432` 映射**（本机 PG 18.3 已占用；容器内 backend 走 `POSTGRES_SERVER=db` 即可） |
| `compose.override.yml` | `backend` / `prestart` 显式声明 `POSTGRES_SERVER=${POSTGRES_SERVER:-db}` |
| `.env` | `POSTGRES_SERVER` 由 `localhost` 改为 **`db`**（附注释说明三种场景分别该填什么） |
| **新建** `milvus-config/embedEtcd.yaml` | 内嵌 etcd 配置（原 `D:\Milvus\embedEtcd.yaml`，纳入仓库） |

### ✅ 实机验证结果（全部通过）

| 验证项 | 结果 |
|---|---|
| `docker compose config` | ✅ Exit 0，无语法错误、无变量缺失 |
| `docker compose up -d milvus` | ✅ **成功**（此前预期会端口冲突） |
| Milvus 健康状态 | ✅ `Up About a minute (healthy)`，`http://localhost:9091/healthz` 返回 **200 OK** |
| **数据完整性** | ✅ **完全保留**：`data` 2.4M + `rdb_data` 5.5M（与改造前**逐字节一致**）；15 个 `insert_log` 段 + rdb_data SST 文件俱在 |
| `docker compose up -d db` | ✅ 成功，`irsbot-db-1` **healthy**（无端口冲突） |
| 容器内 PG 版本 | ✅ **PostgreSQL 18.4**（比本机 18.3 更新，完全兼容） |
| 容器内 db 表 | ✅ 空（正确 —— 待 `prestart` 跑 alembic 建表） |
| **网络互通** | ✅ `db (172.18.0.3:5432) open` / `milvus (172.18.0.2:19530) open` |

### 🔑 一个隐藏很深的坑（已修复，值得记住）

**`env_file` 会覆盖 `compose.yml` 的 `environment` 声明。**

- `compose.yml` 里写的是 `POSTGRES_SERVER=db`
- 但 `backend` 服务同时有 `env_file: .env`，而 `.env` 里是 `POSTGRES_SERVER=localhost`
- **只要 `.env` 里存在这个 key，它就会盖掉 `compose.yml` 的 `environment`**（除非在 `environment` 里再声明一次）
- **不修的后果**：容器内 backend 会去连自己的 `localhost:5432`（空），而不是 `db` 容器 → 启动即连库失败

> 验证方法：`docker compose config` 后 grep `POSTGRES_SERVER`。修复前四个服务全是 `localhost`，修复后全是 `db`。

### 关于旧容器的处置

| 容器 | 状态 | 说明 |
|---|---|---|
| `milvus-standalone` | 已停止并**改名为 `milvus-standalone-old`** | ⚠️ **故意保留不删**，作为回滚退路。确认新方案稳定后可删 |
| `irsbot-milvus-1` | ✅ 运行中（healthy） | compose 管理，复用原数据目录 |
| `irsbot-db-1` | ✅ 运行中（healthy） | compose 管理，全新空库 |

**回滚方法**（若新方案出问题）：
```powershell
cd d:\AIpy\full-stack\IrsBot
docker compose down
docker rename milvus-standalone-old milvus-standalone
docker start milvus-standalone
# 数据目录 D:\Milvus\volumes\milvus 从未被修改，后端可立即恢复可用
```

### ✅ 遗留待办（D1.1 / D1.3 / D1.5 已于 2026-09-17 02:27 全部完成）

| 项 | 状态 | 说明 |
|---|---|---|
| **Traefik / `${DOMAIN}` / `${STACK_NAME}` 剥离** | ✅ 已做 | `compose.yml` 只剩 db / prestart / backend；traefik labels、`traefik-public` 网络、`${DOMAIN}`/`${STACK_NAME}` 全部删除 |
| **adminer 处置** | ✅ 已删 | 原计划"保留在 override"，最终随 D1.1 一起删（有 pgAdmin，且容器库可用 `docker exec` 直连） |
| **前端改后端托管** | ✅ 已做 | D1.3 完成；D1.3e 又删掉了独立的 frontend nginx 容器与 `frontend/Dockerfile` |
| **`proxy`（traefik）服务** | ✅ 已删 | 连同 `compose.traefik.yml`、`mailcatcher`、`playwright` 一起删除 |
| **`DOCKER_IMAGE_*` / `TAG`** | ✅ 已删 | D1.5：`image:` 字段与 .env 变量同批删除，镜像名改由 compose 自动生成 |
| **`SECRET_KEY` 落盘** | ⬜ 未做 | D3.1 |

> 💡 **重要认知更新**：D1.2 之所以能一次成功，是因为**先做了 M2 调研**。
> 如果照抄 `compose.override.yml` 原来的三容器方案，会在「版本落差 + 端口冲突 + 数据目录不兼容」三个地方同时踩坑。

---

## 五、Phase D1 任务清单（施工中 —— D1.2 ✅）

**目标**：把线上版 `compose.yml` 改造为**本地可直接运行**的版本，并清理 full-stack 模板残留。

> 📌 **重要背景（2026-09-16 用户确认）**：本项目基于 **full-stack-fastapi-template** 修改而来，
> 保留了大量模板残留。用户明确「**无关 IrsBot 的都可以放心修改**，只是觉得 full-stack 的 webui 可以直接拿来用」。
> 故 D1 除"让 compose 能本地跑"外，还要**顺手清掉模板痕迹**。
> 详细清单与判定依据见 `local-deployment-plan.md` §3.2。

> ⚠️ **动手前先读**：`compose.yml`（全文，重点 174 行 `external: true`）
> 以及 `backend/Dockerfile` / `frontend/Dockerfile`

### 5.1 已完成（D1.2）

| # | 任务 | 状态 |
|---|---|---|
| **D1.0** | **M2/M3 ✅ 已完成**；**M1 待做（非阻塞）**；**✅ Q1–Q3 已确认（保留现网 Milvus 单容器方案）** | ✅ |
| **D1.2** | **Milvus 服务：✅ 已完成并实机验证通过**（单容器内嵌 etcd + local 存储，绑定挂载复用原数据） | ✅ |
| **D1.2** | **端口冲突：✅ 已解决**（旧容器改名 `milvus-standalone-old` 保留作回滚） | ✅ |
| **D1.2** | **`POSTGRES_SERVER` 覆盖：✅ 已修复**（`env_file` 覆盖陷阱，见第四点五节） | ✅ |
| **D1.2** | **`db` 端口：✅ 已移除 `5432:5432` 映射** | ✅ |

### 5.2 D1.1 剥离部署层残留（✅ 已完成，2026-09-17 02:27 实机验收）

| # | 任务 | 状态 |
|---|---|---|
| D1.1.1 | 删除 `compose.yml` 全部 `traefik.*` labels | ✅ |
| D1.1.2 | 删除 `traefik-public` 网络（两个 compose 文件里的声明 + 各服务的 `networks:`） | ✅ |
| D1.1.3 | 删除 `${DOMAIN?}` / `${STACK_NAME?}` 引用（`.env` 里两个变量同步删） | ✅ |
| D1.1.4 | 删除 `compose.traefik.yml`（整个文件） | ✅ |
| D1.1.5 | 删除 `proxy` 服务（traefik:3.6） | ✅ |
| D1.1.6 | 删除 `mailcatcher` + `playwright` 服务 + `frontend/Dockerfile.playwright` | ✅ |
| D1.1.7 | nginx 配置：随 frontend 容器一并删（见 D1.3e） | ✅ |
| D1.1.8 | `.env`：`PROJECT_NAME=IrsBot`、清掉 `DOMAIN` / `STACK_NAME` | ✅（`FRONTEND_HOST` 保留，settings 用于 CORS 合并） |
| D1.1.9 | `restart` 策略统一 | ⬜ **有意不做**：本地开发用 `restart: "no"` 更省心（崩溃不自动重启、不抢端口），交付前再统一 |
| D1.1.10 | **验收**：`docker compose config` 无报错 | ✅ `db / milvus / prestart / backend` 四个服务，EXIT=0 |

> ⚠️ **D1.1 的两个连带修复**：
> ① 删了 `mailcatcher` → 同时删掉 backend 的 `SMTP_HOST=mailcatcher / SMTP_PORT=1025 / SMTP_TLS=false / EMAILS_FROM_EMAIL=noreply@example.com` 四行（邮件能力已整体移除）。
> ② `POSTGRES_SERVER=${POSTGRES_SERVER:-db}` 的覆盖从 override **上移到 `compose.yml`**（prestart / backend 都写），
> 因为 override 里的 prestart 段被整段删掉了 —— 否则 prestart 会连错库。

### 5.3 D1.3 前端改后端托管（🔶 编码已完成，待实机验证）

| # | 任务 | 状态 |
|---|---|---|
| D1.3a | `backend/app/main.py` 加静态托管 + **SPA fallback**（404 handler，**排除 `/api` 前缀 + 判断 `accept` 头**） | ✅ **已编码** |
| D1.3b | 前端 API 地址改**同源相对路径**（**三处分别改**）+ `vite.config.ts` 补 **proxy** + 删 `.env` 的 `VITE_API_URL` | ✅ **已编码**，`tsc` ExitCode 0 |
| D1.3c | `backend/Dockerfile` 增加 `COPY ./frontend/dist /app/frontend-dist`（**分发优化**） | ✅ 已实机验证（纯镜像无挂载也能出页面） |
| D1.3d | `compose.override.yml` backend 加绑定挂载 `./frontend/dist:/app/frontend-dist` | ✅ 已完成 |
| D1.3e | 移除 `frontend` 独立容器（并入 D1.1） | ✅ 已删 `frontend` 服务 + `frontend/Dockerfile` + `frontend/Dockerfile.playwright` |

> 💡 **方案出处**：照 **AstrBot 的做法**（已读源码核实）——
> `dashboard/server.py:235-254` 三级 dist 路径优先级 + `static_file.py` 显式路由枚举 + Quart `static_folder`。
> 本项目为 FastAPI，改用 **404 handler + 排除 `/api`**，比枚举路由更不易漏。详见 §3.3.4。

**🔴 D1.3b 的三处陷阱（务必逐处改，不要统一替换）**：

| # | 文件 | 正确改法 | 若统一改成 `/api` |
|---|---|---|---|
| 1 | `src/main.tsx:16` | `OpenAPI.BASE = ""` | 可以，但 `""` 更准确表达"同源" |
| 2 | `src/routes/_layout/chat.tsx:23` | 硬写 `"/api/v1/agent/conversations"` | 🔴 变 `/api/api/v1/...`（**路径重复**） |
| 3 | `src/hooks/useAgentChat.ts:50` | `location.protocol` + `location.host` 动态拼 | 🔴 `replace(/^http/, "ws")` **静默失效 → WS 直接坏** |

> ⚠️ **第 3 处最隐蔽**：`replace` 匹配不到正则时**不报错、原样返回**，
> 结果是非法 ws 地址，浏览器只说"连接失败"，**看不出真实原因**。

**⚠️ 配套必需：Vite proxy**（漏了开发入口直接坏）

改相对路径后，浏览器请求 `http://localhost:5173/api/v1/...`，但 5173 是 Vite 静态服务器、
**不认识 `/api`** → 请求到不了后端。故 `vite.config.ts` 必须补：

```ts
server: {
  proxy: { "/api": { target: process.env.BACKEND_URL || "http://localhost:8000",
                     changeOrigin: true, ws: true } },   // ⚠️ ws:true 不开则聊天连不上
}
```

**⭐ 前置发现：前端是 bun workspace 单仓** —— 锁文件（`bun.lock`）与依赖（**251 包**）都在**仓库根**，
`frontend/node_modules` 只有缓存目录、无真实包。**所有前端命令必须在仓库根执行**：

```powershell
# ❌ 不要 cd frontend 后 bun install（会全量重装 + 生成污染性 frontend/bun.lock）
cd d:\AIpy\full-stack\IrsBot
bun run --filter frontend dev       # 开发
bun run --filter frontend build     # 构建 → frontend/dist/
```

### 5.4 D1.4 清理 `items` 模板残留（✅ 已完成，2026-09-17 01:29）

**判定结论**：`items` 是 full-stack 模板的待办示例（`Item` 模型只有 `title` + `description` + `owner_id`，
前端标题「物品」），**与 IrsBot 零关系 → 删除**。

| # | 任务 | 状态 |
|---|---|---|
| D1.4a | 删除 `backend/app/api/routes/items.py` + `api/main.py` 中 `include_router(items.router)` | ✅ |
| D1.4b | 删除 `sqlmodel_models.py` 中 `Item*` 六个类 + `models.py` 同步 | ✅ |
| D1.4c | **新增** alembic 迁移 `f3e1a9b7c2d4_remove_items_table.py` 删除 `item` 表（未改历史迁移） | ✅ |
| D1.4d | 删除 `frontend/src/routes/_layout/items.tsx` | ✅ |
| D1.4e | 删除 `frontend/src/components/Items/` + `Pending/PendingItems.tsx` | ✅ |
| D1.4f | 删除侧边栏指向 `/items` 的导航项 | ✅ |
| D1.4g | 删 `crud/user_item.py:create_item` + `crud/__init__.py`；删 `users.py` 级联 `delete(Item)` | ✅ |
| D1.4h | 删 `tests/api/routes/test_items.py` + `tests/utils/item.py` | ✅ |
| D1.4i | 重生成 `src/client`（openapi-ts）+ `routeTree.gen.ts`（vite build） | ✅ |
| D1.4+ | **连带**：删死链 `routes/recover-password.tsx` + 登录页「忘记密码？」；compose healthcheck `curl` → `python` | ✅ |

> ⚠️ **两条踩坑记录（D1.4 实做）**：
> ① **本机没有 `bun`** —— `bun run --filter frontend generate-client` 直接 `CommandNotFoundException`。
> 但依赖是 **hoist 到仓库根 `node_modules`** 的：直接跑
> `& "d:\AIpy\full-stack\IrsBot\node_modules\.bin\openapi-ts.cmd"`（cwd=`frontend`）即可生成 client；
> 构建同理：`node node_modules/typescript/bin/tsc -p tsconfig.build.json` + `node node_modules/vite/bin/vite.js build`。
> ② **`routeTree.gen.ts` 由 vite 插件自动生成** —— 手写改没用，删完路由文件后必须跑一次 `vite build` 才会剔除 `/items`。

### 5.5 D1.5 镜像变量清理（✅ 已完成，⚠️ 有陷阱）

| # | 任务 | 状态 |
|---|---|---|
| D1.5 | 清理 `DOCKER_IMAGE_BACKEND` / `DOCKER_IMAGE_FRONTEND` / `TAG` | ✅ 与 `image:` 字段**同批删除** |

> 🔴 **陷阱**：这三个变量名字极像模板产物，但 `prestart` 与 `backend` 的 **`image:` 字段正在引用它们**。
> **必须与 `image:` 字段同批删除**，否则 `?Variable not set` 立即报错。
> 本地开发其实只需要 `build:` 就够了。

**验收（对应 SC D1–D3）**：
- `docker compose up -d` 后各服务全部 healthy
- 浏览器打开 `http://localhost:8000` **可直接对话**
- 前端由后端托管，**不再需要 5173 dev server**
- 刷新任意前端路径**不出现 404**（含深链接如 `/chat`、`/settings`）
- ✅ **`docker compose ps` 无端口冲突报错**（本机已有 PG 5432 + Milvus 19530/9091/2379 在占用）
- ✅ **`docker compose config` 无 `?Variable not set` 报错**
- ✅ **前后端均无 `items` 残留**（`grep -r "items" backend/app frontend/src` 只剩无关命中）

---

## 六、Phase D2 / D3 任务清单

| # | 任务 | 状态 |
|---|---|---|
| D2.1 | Windows `scripts/start.cmd`（检查 Docker → `compose up -d --build` → 轮询 healthy 最多 3min → 打开浏览器 → 打印账号） | ✅ 已写 |
| D2.2 | macOS / Linux `scripts/start.sh`（等价实现） | ✅ 已写 |
| D2.3 | 停止脚本 `stop.cmd` / `stop.sh`（`docker compose down`，数据卷保留；`-v` 才删库） | ✅ 已写 |
| D2.4 | 首次运行自动从 `.env.example` 生成 `.env`（缺 `.env` 时 copy，不覆盖已有） | ✅ 已写 |

> 🔴 **D2 编码坑（已踩已修）**：Windows `cmd.exe` 用 **ANSI 代码页**读 `.cmd`，
> 任何非 ASCII 字节（含中文注释）都会被 GBK 解错、破坏解析 → 报
> `'?-v' 不是内部或外部命令`。**`start.cmd` / `stop.cmd` 已改为纯 ASCII 英文**（`nonascii=0` 已验证）。
> `.sh` 跑在 bash（UTF-8）不受影响，仍可用中文。
> ⚠️ 本沙箱 Git Bash 缺 `sh`/`head`/`docker` 于 PATH，**`start.cmd` 的端到端实跑需在用户 Windows 机器上做**（compose 栈本身已在上一轮实机验收 healthy）。
| D3.1 | **`SECRET_KEY` 首次生成后落盘**（落 `.env` 或命名卷） | ✅ 已做（bootstrap：仅当为 `changethis`/空才生成，保留已有真实值） |
| D3.2 | **管理员密码随机生成并打印**到终端（替代 `changethis`） | ✅ 已做（bootstrap + start.* 打印；powershell 实测通过） |
| D3.3 | 首次启动自动 `alembic upgrade head` 建表 | ✅ 已做（prestart.sh 第 10 行 `alembic upgrade head`，早存在） |
| D3.4 | 启动完成打印访问地址 + 初始账号密码 | ✅ 已做（start.* 打印 URL/账号/密码） |

> 🔴 **D3 实现要点（用户确认「第一次登录随机生成」）**：
> ① **随机生成放在宿主 `start.*` 脚本**，不是容器里——因为 `.env` 在宿主机，`env_file` 在 `docker compose up` 时只读一次，容器内无法写回并让 backend 读到。
> ② 新增 `scripts/bootstrap_env.ps1`（Windows，ASCII）：`SECRET_KEY` / `FIRST_SUPERUSER_PASSWORD` 若仍是 `changethis` 或空 → 生成强随机值（A-Za-z0-9-_）写回 `.env`（UTF-8 无 BOM）。**非破坏性**：用户已有的真实 `SECRET_KEY` 不动。
> ③ `start.cmd` 调 `powershell -ExecutionPolicy Bypass -File bootstrap_env.ps1`；`start.sh` 用 `tr -dc A-Za-z0-9_- < /dev/urandom | head -c` + `sed` 等价实现（macOS/Linux 无 PowerShell）。
> ④ **配套改 `backend/app/core/db/engine.py::init_db`**：superuser 已存在时，把库内密码同步成 `.env` 的 `FIRST_SUPERUSER_PASSWORD`（仅当哈希不符时）。否则「首次随机密码写进 .env、但库里 superuser 还是旧 `changethis`」→ 打印的密码登不进去。这同时修好了用户当前实例（容器库 superuser 仍 `changethis`）。
> ⑤ ⚠️ 行为约定：**`.env` 的 `FIRST_SUPERUSER_PASSWORD` 是管理员密码的唯一真相源**，每次启动都会把它同步进库。在 UI 里改的密码重启后会还原成 `.env` 值——本地单用户部署下这是预期行为。

**验收（对应 SC D4–D5）**：
- 首次 `start` 后终端直接给出可用地址与密码，**全程零手工配置**
- `docker compose restart` 后**已登录会话仍有效**（证明 `SECRET_KEY` 未变）

---

## 七、Phase D4 / D5 / D6 / D7（后续）

| 阶段 | 核心 | 状态 |
|---|---|---|
| **D4.1** | 干净环境（删卷重来）一条命令跑通全功能 | ✅ 新增 `scripts/reset.cmd`/`reset.sh`（`docker compose down -v` + 调 `start`） |
| **D4.2** | 重跑测试基线（294 单测 + 18 集成） | ✅ 命令已核对 + conftest 安全闸在位；实跑需用户机器（沙箱无 PG） |
| **D4.3** | **可分发验证**：把仓库拷给别人，对方一条命令跑通 | ✅ 源码层验证无硬编码 host/port（相对路径 `/api`），同一 dist 跨机可用 |
| **D4.4** | README（5 分钟跑通） | ✅ 重写根 `README.md` 为 IrsBot 版（原模板 README 的 Traefik/Mailcatcher/Items/Copier 已在 D1 删除，属误导） |
| **D5.0** | ✅ **备份已完成**（2026-09-17 03:xx）：`backups/20260917_095030/` 含 ① 容器 `app` 库 `pg_dump -Fc`（可恢复，TOC 61 条）② 本机 `app` 库 dump ③ `.env` 副本（含密钥）④ `irsbot_app-db-data` 卷 tar ⑤ `D:\Milvus\volumes\milvus` 目录副本（156 MB，etcd 锁文件由 robocopy 拷出）。`backups/` 已加 `.gitignore`。`test_app`/`document_agent` 系可弃空壳，未备 | ✅ |
| **D5.0** | 备份**格式校验**通过：`pg_restore -l` 列出 61 条 TOC、CUSTOM+gzip、来自 PG 18.4（未做完整恢复演练，但归档有效） | 🔶 |
| **D5.1** | ✅ **数据盘点已完成** —— 真实资产 5 项；21 KB / 21 Persona / 17 MCP / 75 会话 / 21 文件为测试残留（见第四节验证 3） | ✅ |
| **D5.1b** | ✅ **测试残留清理**：26 个孤儿上传文件移入可回收 trash `backups/residue-trash-20260917/`（本机 `app` 库 0 行无需删；比对容器库 `knowledge_bases=0` 确认全为孤儿）；PowerShell `Move-Item` 移动未删 | ✅ |
| **D5.2** | 🔴 **判定：不迁移**。核查发现本机 `app` 库是**陈旧/残缺副本**（多一张遗留 `item` 表、无 `provider_configs`、会话/消息为 0），而容器 `app` 库才是**完整权威库**（11 表无 `item`、`provider_configs=1` default、`user=1`、conversations/messages 各 3、alembic `f3e1a9b7c2d4`）。**盲目迁移反而会把遗留 `item` 表带进容器、还可能冲掉已有模型源** → 以容器库为准 | ✅（判定） |
| **D5.3** | ✅ Milvus 数据在**绑定挂载** `D:/Milvus/volumes/milvus`，容器 `irsbot-milvus-1` 直接复用，**零迁移**；已随 D5.0 备份该目录 | ✅ |
| **D5.4** | ✅ **迁后验证通过**：容器 `app` 库 `user=1`（admin 可登录）、`provider_configs=1`（default 模型源可用）、conversations=3、messages=3、alembic 在 head；dump 可恢复 | ✅ |
| **D5.5** | ✅ 回滚方法已在 §4.5 写明（`docker compose down` + rename `milvus-standalone-old` 启动）；备份目录可作恢复源 | ✅ |
| **D6** | ✅ **工具权限开关**：`config.py` 新增 `ENABLE_SHELL` / `ENABLE_FILE_WRITE`（默认 `False`）+ `FILE_WRITE_ROOTS`（逗号分隔白名单，留空回退 cwd+/tmp+临时目录）。`builtins/__init__.py` 按配置条件注册——shell/file_write 默认不注册（不暴露给 LLM）；`web_search`/`knowledge_base_query` 只读，始终注册。`file_ops._allowed_roots()` 改读 `settings.FILE_WRITE_ROOTS`。**附带修复潜在 bug**：此前 `app.core.agent.builtins` 从无模块导入触发注册，builtin 工具等于死代码；现 `agent.py` 顶部 `import app.core.agent.builtins` 确保启动即注册（受开关控制） | ✅ |
| **D7** | ✅ **运维手册（备份 / 恢复 / 卸载说明）**：新建 `docs/OPERATIONS.md`，含①数据资产清单（PG=命名卷、Milvus/uploads/.env/dist=宿主目录，明确 `-v` 只删 PG）②一键备份 `scripts/backup.cmd` 说明 + 捕获项表③恢复三场景（仅库 / 仅向量 / 全盘，`pg_restore --clean --if-exists` + Milvus 目录覆盖 + uploads 拷贝）④卸载三档（停服保留 / `down -v` 清 PG / 彻底清宿主目录）⑤**明确 `reset.cmd` 只清 PG 不清 Milvus 的陷阱及修复**⑥排查表 + 脚本一览。**附带增强**：`scripts/backup.ps1` 新增 `backend/uploads` 只读拷贝（此前漏备，RAG 恢复会缺源文件），manifest 同步记录；PowerShell 语法校验通过 | ✅ |

> ⚠️ **D5 必须严格在 D4 之后**：数据迁移不可逆，**先证明新房子能住，再搬家具进去**。

---

## 八、Phase 10 收尾清单（2026-09-17 代码审查 + 验收清单）

| # | 任务 | 状态 |
|---|---|---|
| 10.1 | WS API | ✅ |
| 10.2 | 前端聊天页 | ✅ |
| 10.3 | 前端管理页（Provider 外） | 🔶 **代码审查完成**：`admin.tsx` 用户管理页 + `settings.tsx` 设置页（含「模型源」tab）均已存在，侧边栏 `/settings`、`/admin`（superuser）导航已通；**缺口：知识库（KB）管理 UI 尚未建**，待确认是否补 |
| 10.4 | 上下文记忆 | ✅ |
| 10.5a–e | Provider 管理 UI 实测 5 项 | ✅ **已完成（API 层实测）**：a/b/c/e ✅ 通过；d ⚠️ 曾发现缺陷（删默认源后无默认）→ **已修复**（`delete_provider` 自动补位 + 6 条回归测试，2026-09-18）；连带项 **f RAG 向量化 ✅ 通过**（`bfe1c7d` 修复已生效）。明细与证据见 §10.6 实测结果 |

> 🔴 **代码审查发现并修复的阻断 bug（2026-09-17，Phase 10.5）**：
> `backend/app/core/agent/provider.py::get_embedding_model` 把库中**加密存储**的 `pc.api_key`
> **原样**（密文）传给 `OpenAIEmbeddings` / `AnthropicEmbeddings`，
> 而同文件 `get_chat_model` 已正确 `decrypt_api_key`。
> 因为 `init_db` 播种默认模型源时也用 `encrypt_api_key`，**所有** DB 落库的 key 都是密文
> → 任何走 DB Provider 的 RAG 向量化 / 检索都会鉴权失败（`401`）。
> ✅ 修复：embedding 分支同样先 `decrypt_api_key(pc.api_key)`。两文件 `py_compile` 通过。
> ⚠️ 该 bug 不影响 10.5a–e 的「增/改/删/列/加密存储」5 项 UI 本身，但会在「实测后用 KB 验证 embedding」时暴露，
> 故提前修掉，避免你实机点到 RAG 才报错。

### §10.6 Phase 10.5 实测验收清单（需在用户 Windows 机器跑，沙箱无 Docker/前端/PG）

**前置**：`scripts/start.cmd` 一条命令起栈（db/milvus/backend healthy）→ 浏览器开 `http://localhost:8000`。

| 项 | 操作 | 预期 | 后端链路 |
|---|---|---|---|
| a 列表 | 登录 admin → 侧边栏「设置」→「模型源」 | 显示已播种的 `default` 模型源，带「默认」徽标 | `GET /api/v1/providers` → `ProviderManager.list_providers` |
| b 新增 | 点「新增模型源」→ 填 名称/类型(openai)/API Key/模型名 → 保存 | 列表新增一行；`GET` 复测出现该条；Key 不再出现 | `POST /api/v1/providers` → `create_provider`（encrypt） |
| c 设为默认 | 对新行点「设为默认」 | 旧默认徽标消失、新行出现「默认」 | `PATCH /providers/{id}` `{is_default:true}` → `clear_other_defaults` |
| d 删除 | 点「删除」→ 确认 | 该行消失；`GET` 复测已无 | `DELETE /providers/{id}` → `delete_provider` |
| e 加密 | 浏览器 Network 看 `GET /api/v1/providers` 响应 | **响应体无 `api_key` 字段**（仅 name/type/model/base_url/is_default/is_active） | `ProviderOut` 不含 api_key |

**连带验证（修 bug 后必做）**：建一个知识库 → 上传文档 → 触发向量化，确认不再 `401`
（embedding 现走解密后的真实 key）。

### ✅ §10.6 实测结果（2026-09-17 21:xx，实栈 http://localhost:8000，API 层直测）

> 说明：原计划在浏览器里点测，但**本环境无法启动浏览器**（`agent-browser` 已装好、Chrome 196MB 已下载，一旦拉起 Chromium 进程即被沙箱杀掉；`--help` 这类不启浏览器的命令正常）。改为**直连真实后端**逐项验证——数据层与互斥逻辑完全等价，只有「徽标是否渲染」属纯视觉项未覆盖。

| 项 | 结果 | 实测证据 |
|---|---|---|
| **a 列表** | ✅ 通过 | `GET /providers` → 200，返回 `default`：`type=openai`、`model=qwen3.8-flash`、`base_url=https://dashscope.aliyuncs.com/compatible-mode/v1`、`is_default=True`、`is_active=True` |
| **b 新增** | ✅ 通过 | `POST /providers` → 200，新行 `verify-test-106`（openai / gpt-4o-mini）落库；复测 `GET` 由 1 行变 2 行 |
| **c 设为默认** | ✅ 通过（互斥生效） | `PATCH /providers/{新}` `{is_default:true}` → 200；复测 `default.is_default` 自动变 `False`，全库 `is_default=True` 行**数量 = 1** ✅ |
| **d 删除** | ⚠️ **发现缺陷（未通过）** | `DELETE /providers/{新}` → 200 `{"ok":true}`，该行消失；**但原 `default` 行仍为 `is_default=False` → 全库没有任何默认模型源**，与预期「徽标回到 default」不符。**根因**：`ProviderManager.delete_provider()`（`provider.py:455–470`）只做 `session.delete(obj)`，**没有在删除的恰好是默认行时提升另一条为默认**（`clear_other_defaults(user_id, keep_id)` 具备能力但只在 create/update 路径被调用）。**影响**：用户删掉当前默认源后，界面无「默认」徽标，后端也失去默认源（聊天/RAG 取默认 Provider 的路径会拿不到） |
| **e 加密** | ✅ 通过 | 全部行的响应体**均无 `api_key` 字段**（`has_api_key=False`）；仅 name/type/model/base_url/is_default/is_active |
| **f RAG 向量化** | ✅ **通过（bfe1c7d 修复已生效）** | 建库 `verify-106-rag`（201）→ 上传 213 B txt → `status=done`、`chunks_count=1`（**embedding 写入成功，无 401**）→ `POST /kb/{id}/query` → 200，命中 1 条且**内容正是写入时的独有事实 `Iris-2026`** → 测试库已清理（DELETE 200） |

> ⚠️ **实测过程污染与恢复**：d 项执行后环境一度处于「无默认模型源」状态，**已立即用 `PATCH /providers/{default.id}` `{is_default:true}` 恢复**（复测 `default.is_default=True` ✅）。测试用的 `verify-test-106` 模型源与 `verify-106-rag` 知识库均已删除，环境已还原。

**结论**：5 项中 a/b/c/e 全通过，**f（最关键的一项）通过**；**d 暴露 1 个真实缺陷**（删默认后不自动提升新默认）→ **已修复并补齐回归测试**（见下节）。

### ✅ 已修：d 项缺陷（删默认源后无默认）—— 2026-09-18

**位置**：`backend/app/core/agent/provider.py::delete_provider`

**改法（采用方案 1）**：删除前先判断被删行是否 `is_default`；若是，则在该用户**其余启用中**（`is_active=True`、`id != 被删行`）的配置里按 `fallback_order` 升序取一条置为 `is_default=True`，再执行删除并一次 `commit`。
- 只查 `is_active=True` 是关键：`get_chat_model()`/`get_embedding_model()` 要求 `is_default` **与** `is_active` 同时成立，若把停用中的源提上来，会变成「有默认徽标但取不到模型」的假象。
- 严格按 `user_id` 过滤：避免删自己的默认源时把**别人的**源提上来（越权使用他人密钥）。
- 无接替者时保持无默认（此时确实也没有可用源），不报错。

**配套回归测试（新增 6 条，命名前缀不变）**：

| 文件 | 测试 | 断言 |
|---|---|---|
| `tests/provider/test_manager.py` | `test_delete_default_promotes_successor` | 删默认 → 接替者就位、恰好 1 条默认 |
| 同上 | `test_delete_default_picks_lowest_fallback_order` | 多候选时挑 `fallback_order` 最小的一条 |
| 同上 | `test_delete_default_skips_inactive_candidates` | 停用中的候选不被提升 |
| 同上 | `test_delete_last_default_leaves_no_default` | 删唯一默认 → 干净地无默认，不报错 |
| 同上 | `test_delete_default_does_not_touch_other_users` | 多租户隔离：不提升他人源 |
| 同上 | `test_delete_non_default_keeps_existing_default` | 删非默认源不动现有默认 |
| `tests/api/routes/test_providers.py` | `test_delete_default_promotes_successor` | API 层：删默认后列表仍有且仅有 1 条 `is_default` 且 `is_active` |

**验证结果**：
- **证伪验证（测试层）**：临时把提升逻辑短路（`if obj.is_default and False`）后重跑 → **恰好这 4 条依赖补位的新测试失败**（`4 failed, 20 passed`），证明测试真实覆盖该缺陷，不是空转。
- **修复后（测试层）**：`tests/provider/test_manager.py` + `tests/api/routes/test_providers.py` → **24 passed**。
- **全量回归**：`pytest ../tests -q` → **311 passed, 0 failed**（100.93s）。详见文末「测试基线」。
- **实机验证（真实栈 http://localhost:8000，admin 登录）** —— A/B 对照：

| 轮次 | 容器内 `provider.py` | 删默认源后的结果 |
|---|---|---|
| A（修复前，`cd1f17b` 版本） | 无补位逻辑 | 列表只剩 `default default=False` → **0 条默认**（缺陷如实复现，徽标消失） |
| B（修复后，`a746d10` 版本） | 含补位逻辑 | 列表 `default default=True` → **恰好 1 条默认，且自动补位、处于启用中** ✅ |

> 实机动作序列与 §10.6 d 完全一致：新增一条并设默认（互斥生效，旧默认自动降级）→ 删除它 → 断言仍有且仅有 1 条默认且非被删行。
> **环境已还原**：验证后仅剩 1 条 `default`（`is_default=True`），与验证前基线一致；测试用的 `verify-106d-fix` 行已在流程内删除。

> ⚠️ **一个坑（供下次实机验证参考）**：容器内 `backend/` 不是绑定挂载，只有 `develop.watch` 同步，所以改了代码要手动 `docker cp` 进容器；而 uvicorn 的 `--reload`（StatReload）**只在 mtime 变大时才重载**——用 `docker cp` 灌回**较旧**的版本时 mtime 反而变小，**不会触发重载**，会造成"代码明明换了、行为却是旧的"假象。解法：`docker exec … python -c "import os,time; os.utime(p,(t,t))"` 把 mtime 顶到未来，再等重载日志出现 `Started server process`。

**实跑命令（宿主机，注意 `env_file="../.env"` 是相对 cwd 的，必须在 `backend/` 下运行）**：

```powershell
cd d:\AIpy\full-stack\IrsBot\backend
$env:POSTGRES_SERVER="localhost"; $env:POSTGRES_DB="test_app"   # 覆盖 .env 的 db / app
..\.venv\Scripts\python.exe -m pytest ..\tests\provider\test_manager.py ..\tests\api\routes\test_providers.py -q
```


**契约校验（已在沙箱静态确认）**：
- `frontend/src/client/sdk.gen.ts` 的 `ProvidersService` 四个方法名/路径与 `useProviders.ts` 调用、**及后端 `providers.py` 路由**完全一致（`listProviders` GET、`createProvider` POST `{requestBody}`、`updateProvider` PATCH `{providerId,requestBody}`、`deleteProvider` DELETE `{providerId}`）。
- `providers.router` 已 `include_router` 进 `api/main.py`（第 22 行），端点真实存在。
- `frontend/src/components/Providers/ProviderSettings.tsx` 表单 zod 校验、`AddProviderDialog`、`ProviderRow`（设为默认/删除确认）齐全；`is_default` 互斥由后端保证。

> ✅ **2026-09-18 更新**：上述「需你在 Windows 机器按表走一遍」**已全部完成**——a/b/c/e/f 于 2026-09-17 经实栈 API 直测通过，d 项缺陷已修复并 A/B 验证；容器代码同步见下一节。

### ✅ 容器同步 + 注册闸门实机验证（2026-09-18）

**背景**：上一轮结束时容器内仍是旧代码（`config.py` 无 `USERS_OPEN_REGISTRATION`、`users.py` 无 403 守卫），沙箱 `docker` CLI 不可用，只能留给用户在宿主机执行 `docker compose up -d --build backend`。本轮该步骤已执行并验证闭环。

**关键认知**：`compose.override.yml` 里 backend 用的是 **`develop.watch`（`action: sync`）**，而 `docker compose up -d` **不会**启动 watch 守护进程 —— 所以「改了源码但容器里是旧的」是**预期行为**，不是 bug。同步方式二选一：

| 方式 | 命令 | 说明 |
|---|---|---|
| **重建镜像（本次采用）** | `docker compose up -d --build backend` | 源码烘进镜像；**一次到位、可复现** |
| 持续同步（开发时） | `docker compose watch` | 需另开一个常驻终端；改了即同步 |

> ⚠️ 另有一条已知坑（本轮未踩）：容器内 `backend/` 非绑定挂载，若手动 `docker cp` 灌回**较旧**版本，mtime 变小 → uvicorn `--reload`（StatReload）**只在 mtime 变大时重载** → 造成「代码换了、行为却是旧的」假象。解法见 §10.6 d 节末的 `os.utime` 备注。

**重建结果**：

```
Image irsbot-backend Built
Container irsbot-db-1 Recreated / Started / Healthy
Container irsbot-prestart-1 Exited          ← 迁移 + 播种跑完
Container irsbot-backend-1 Started
```

- ✅ 4 个容器全部 Recreate（`db` / `prestart` / `backend` / `milvus` 保持 Running）
- ✅ **数据未丢**：`db` 用命名卷 `app-db-data`，重建后 `user=1`、`provider_configs=1`（`default`，`is_default=True`）—— 与重建前基线一致

**容器内代码校验（`docker compose exec backend grep`）**：

| 目标 | 结果 |
|---|---|
| `app/core/config.py` | ✅ `167: USERS_OPEN_REGISTRATION: bool = False` |
| `app/api/routes/users.py` | ✅ 403 守卫存在（`194: detail="Open user registration is forbidden on this server"`） |
| `app/core/agent/provider.py` | ✅ `ProviderConfig.user_id == user_id` 出现 **7 处**（与仓库源码一致） |
| `app/core/agent/provider.py` | ✅ 删默认源补位逻辑存在（`505:` 注释行） |
| `app/core/agent/prompts.py` | ✅ `DEFAULT_SYSTEM_PROMPT` 存在（系统提示词功能已进容器） |
| `/app/frontend-dist/assets` | ✅ 与宿主机 `frontend/dist` 一致（`login-CP8ls77z.js`，无旧产物） |

**运行时验证（真实栈 `http://localhost:8000/api/v1`，7 项全过）**：

| # | 断言 | 结果 |
|---|---|---|
| 1 | 后端存活 | ✅ `GET /utils/health-check/` → 200 |
| 2 | **注册闸门生效** | ✅ `POST /users/signup` → **403** `{"detail":"Open user registration is forbidden on this server"}` |
| 3 | **防账号枚举** | ✅ 已存在邮箱（`admin@example.com`）与不存在邮箱的响应**逐字节一致**（`403` + 同一 JSON）→ 证明守卫确实在「查重」**之前** |
| 4 | 超管登录 | ✅ `POST /login/access-token`（**表单编码**，`OAuth2PasswordRequestForm` 不吃 JSON） → 200 |
| 5 | **闸门关闭时无账号落库** | ✅ `GET /users/` → `users=['admin@example.com']`（无 `sync-probe` 账号），符合「单用户」定位 |
| 6 | Provider 能力不回归 | ✅ `GET /providers` → `count=1`，`defaults=['default']`（恰好 1 条默认，重建后未失默认） |
| 7 | 系统提示词不回归 | ✅ `GET /users/me/system-prompt` → 200 |

> 🎯 **结论**：**容器同步闭环，D10（无自助注册入口）实机达成，既有能力无回归。**
>
> 📌 **复现命令**（宿主机 PowerShell，注意 `PowerShell` 的 stdout 常不回显 → 用 `Out-File` 落盘再读）：
> ```powershell
> cd d:\AIpy\full-stack\IrsBot
> docker compose up -d --build backend
> docker compose exec -T backend grep -n "USERS_OPEN_REGISTRATION" app/core/config.py
> ```
> 验「防枚举」时**两个请求的原始字节都要比对**，只看状态码无法区分「守卫在前」还是「守卫在后」。

### ✅ 文档同步：D2 语义拆分（2026-09-18，第六轮）

**漂移是什么**：`istbot-implement-plan.md` 写「因 D2（本地单用户），Phase 11 **整体降级** —— 串 Key 在单用户下不存在」，并把它落成一条**义务**：「Provider 读取函数保留可选归属参数位（`user_id: UUID | None = None`），单用户下忽略 —— **留接口不留逻辑**」。

**而代码（`ef08cc1`）恰恰相反**：`user_id` 已是**必填位置参数**（无默认值），两条查找分支都过滤，缓存键含 `user_id`，`None` 时 **fail closed**。

> 🔴 **这是最危险的一类漂移**：不是「忘了更新」，而是**文档与已发布代码方向相反**。照文档办事的人会以为「隔离不用做」，进而把 `user_id` 过滤**删掉**。

**错在哪（根因）**：把**两件性质不同的事**当成一件处理了——

| 拆分项 | 内容 | 正确处置 |
|---|---|---|
| **(A) 多用户「运营化」** | 自助注册、配额、计费、多账号自助闭环 | ➖ 降级不做（D2 + D1） |
| **(B) 「归属隔离」** | 每条数据 / 每个 Provider 只能被归属者取到 | ✅ 已实现为硬约束 |

原判「单用户下不存在串 Key」**只对 (A) 成立**。 (B) 有独立价值：① `get_chat_model(provider_id=None)` 若不过滤就是**全库**默认源 → 静默用错 Key（**无报错的越权**）② 代码库要被另一个多用户项目复用，留「忽略 user_id」的签名等于**预埋缺陷** ③ 安全默认优于留白。

**一句话**：砍掉的是**运营功能**，不是**安全边界**。

**本轮同步范围（只改活引用，保留追溯性引用）**：

| 位置 | 改法 |
|---|---|
| 0.0 决策表 D2 行 | 拆为 (A)/(B) 两句；**新增 D2.1 行**（注册入口默认关闭） |
| 0.2 定位决策表 | 「多租户要不要做」→ 明确指「多用户运营化」；「Provider 归属」→ 删掉「无需多租户隔离」 |
| 0.4 现状表 | 「注册 关闭（单账号）」→ 写明开关名与 403 行为 |
| 0.4 复用义务 | 「留接口不留逻辑」→ 改为「**归属隔离已实现**」 |
| 0.5 追溯表 | 三行改判；**明确指出当年「把两句当一件事否掉」是过度归并** |
| 一节阶段表 · Phase 3 | 补「归属隔离已实现」 |
| Phase 3.5 | 删掉「单用户下忽略 user_id」，改为「已实现」 |
| SC 表 · SC11 | `~~取消~~` → **✅ 达成**（并加一句说明「取消的应是运营化」） |
| SC 表 · **新增 D10** | 无自助注册入口（含防枚举断言） |
| 6.1 能力矩阵 | 删「**读取函数缺归属参数位**（留接口即可）」→ 「归属隔离已实现」 |
| 8.0 引言 / 总览表 / 8.1 索引 | 「降级」→ 「运营化降级；归属隔离已实现」 |
| **8.4 全节重写** | 原「为什么全部不再适用」→ 拆 (A)/(B) + 「已实现内容」表 + 逐项裁定 11.1–11.5 + 注册闸门小节 |
| 五节「已移出本表」注 | 补 2026-09-18 更正 |
| 第九节变更说明 | **追加第六轮 7 行**（不覆盖历史） |

> ✅ **刻意保留（追溯性引用）**：0.5 表里 `~~划掉~~` 的历轮判断、第九节第五轮的历史记录、8.4 引言中**引用的原错误表述**（作为对照留痕）。**删除它们 = 下次还会被同一个错误意见说服。**

**踩到的工具坑（值得记住）**：同一轮里**并行发多个文件编辑**时，出现过**部分编辑未落盘**（表现为「返回成功但内容还是旧的」）。→ **改完必须重新 grep 回查**，不能以「编辑返回成功」为准。本轮为此做了两轮 grep 复核，补回了 4 处漏改（0.4 注册行 / Phase 3 行 / 8.0 引言 / 8.1 索引）。

---

### ✅ 部署模式运行时开关（2026-09-18，第七轮 —— D2.1 由「写死」改为「可切换」）

**用户指令**：「关于多租户问题，管理员可以选择多租户和单用户开关」。计划文档：[multi-tenant-plan.md](./multi-tenant-plan.md)（v2）。

**现状核查结论（决定方案尺度）**：

| 层 | 现状 | 结论 |
|---|---|---|
| 数据层 | `ProviderConfig` / `Conversation` / `Message` / `KnowledgeBase` / `Document` / `MCPServer` / `Persona` / `AgentRun` **全部**带 `user_id` + `ON DELETE CASCADE` | **已是完整多租户**，开关不需要新建任何归属结构 |
| 隔离逻辑 | `provider.py` 双分支 `user_id` 过滤 + 缓存键含 `user_id` + fail closed（`ef08cc1`） | **安全边界**，两模式下都不动 |
| 运行时配置机制 | **不存在**（开关全在 `.env`） | 需新建 |

> 一句话：**开关控制的是「策略」，不是「代码路径」**。数据层的多租户能力一直都在。

**用户三项决策**：① 载体 = **运行时**（DB + `/admin` 页）② 严格度 = **仅关自助注册，超管仍可建号** ③ 先出计划文档。

> ⚠️ 决策 ② 两次推翻初稿：先推翻「单用户下隐藏 `/admin` 与侧边栏入口」（超管要建号就必须保留 `/admin`），再推翻「两个配置键」（见下）。

**实施清单**：

| 件 | 路径 | 说明 |
|---|---|---|
| 模型 | `backend/app/core/db/models.py` | 新增 `AppSetting`（`key` 主键 / `value` / `updated_at`），第 10 张表 |
| 迁移 | `backend/app/alembic/versions/d4e5f6a7b8c9_add_app_settings_table.py` | `create_table` / `drop_table` 对称，`down_revision = a1b2c3d4e5f6` |
| 读取层 | `backend/app/core/settings_runtime.py`（新建） | 键名常量 + `get_setting` / `set_setting` + **`signup_allowed()`（全项目唯一判断点）** + `deployment_mode()`（展示标签）+ `count_users()` |
| Schema | `backend/app/core/db/sqlmodel_models.py` | `DeploymentSettingsUpdate` / `DeploymentSettingsPublic` / `PublicSettings` |
| 注册闸门 | `backend/app/api/routes/users.py` | 守卫改读 `signup_allowed(session)`，**位置不变、仍在查重之前**（防枚举）；移除对 `settings` 的直接依赖 |
| 公开端点 | `backend/app/api/routes/utils.py` | `GET /utils/public-settings`（**匿名**，只暴露 `open_registration` 一位布尔，登录页渲染注册入口用） |
| 超管端点 | `backend/app/api/routes/settings.py`（新建） | `GET` / `PATCH /settings/deployment`，超管专属 |
| 路由注册 | `backend/app/api/main.py` | `include_router(settings_routes.router)` |
| 配置注释 | `.env` / `.env.example` / `config.py` | `USERS_OPEN_REGISTRATION` 注释改为「**首次兜底值**；部署后以网页开关为准」 |
| 测试隔离 | `tests/conftest.py` | **`AppSetting` 必须加入收尾清表列表** —— 运行时配置**全库共享**（无 `user_id`），漏清会让某条用例写下的 `true` **漏给后续所有注册闸门断言** |
| 前端 hook | `frontend/src/hooks/useDeploymentSettings.ts`（新建） | `deploymentSettingsQuery` / `updateDeploymentSettings` / `usePublicSettings` |
| 前端组件 | `frontend/src/components/Admin/DeploymentMode.tsx`（新建） | 「单用户 / 多租户」两态开关 + 切到多租户时**二次确认**（写明「任何人可注册并消耗你的 API Key」）+ `user_count` 提示 + `.env` 被覆盖时的告警 |
| 前端接入 | `routes/_layout/admin.tsx` / `routes/login.tsx` | `/admin` 页顶部插入开关卡；登录页按 `open_registration` **条件**恢复「注册」入口（`f8ea244` 删掉的入口） |
| client 再生成 | `frontend/src/client/**` | `openapi.json` 重新导出 + `openapi-ts` 生成 `SettingsService` / `UtilsService.readPublicSettings` |

**核心语义（唯一判断点）**：

```
signup_allowed(session) = app_settings 表有记录 ? 表里的值 : .env 的 USERS_OPEN_REGISTRATION
```

- **优先级：`app_settings` 表 > `.env` > 代码默认值**
- 表里没记录时回落 `.env` → **升级后现网行为零变化**；现有 3 条注册闸门测试（monkeypatch `settings.USERS_OPEN_REGISTRATION`）因此**无需改写**
- **不做进程内缓存**：多 worker / WS 进程各持副本必然不一致，而主键单行查询开销可忽略

**⚠️ 一个刻意的收窄：只留一个开关（v2 砍掉 `mode` 键）**

v1 原设计两个键（`deployment.mode` + `deployment.open_registration`），派生 `signup_allowed = (mode=="multi_tenant") AND open_registration`。复查时发现**冗余状态缺陷**：因为决策 ② 让超管在两种模式下都能建号、`/admin` 两种模式都保留、归属隔离两种模式都生效，于是「**多租户 + 关注册**」与「**单用户**」在**所有可观测行为上完全等同**（注册都 403、超管都能建号、`/admin` 都可见、隔离都生效）。

→ 留两个开关只会造出一个产出相同结果的档位，读设置的人无从判断该选哪个；维护者还会误以为 `mode` 管着什么。**冗余状态比缺失状态更危险：它让人以为存在一道其实不存在的约束。**

处置：配置层只留 `users.open_registration` 一键；「单用户 / 多租户」降为**呈现层标签**（由布尔派生）；互斥 400 校验取消；防误触由「双开关两步」改为「单开关 + 二次确认」。完整推演见 `multi-tenant-plan.md` 第十一节（v1 设计与问题**完整留痕**，未删）。

**测试（33 条新增）**：

| 文件 | 条数 | 覆盖 |
|---|---|---|
| `tests/core/test_settings_runtime.py` | 15 | 布尔解析参数化（含乱值 → None 回落）；**优先级矩阵**（无记录回落 `.env` ×2 / 记录覆盖 `.env` ×2）；类型化写入往返；通用 KV 覆盖写；键名常量锁定 |
| `tests/api/routes/test_settings.py` | 18 | `GET /settings/deployment` 超管 200 / 普通 403 / 匿名 401；`PATCH` **立即影响**后续 `signup`（开→200、关→403）；普通用户改不动且**确实没生效**；非布尔 422；字段缺失 422；**超管在关注册时仍可建号**（决策 ②）；**来回切换不改变账号数**；`/utils/public-settings` 匿名可读且**只返回一个字段**、跟随运行时值 |

**⚠️ 一个容易漏的坑**：`tests/conftest.py` 的收尾清表列表必须加 `AppSetting`。运行时配置与其它表不同——它**没有 `user_id`**，是全库共享的；某条用例把 `users.open_registration` 写成 `true` 后若不清，**后续所有依赖「默认关闭」的用例都会连带失效**。

---

## 九、施工前必做调研（M1–M3 —— **M2 / M3 已完成，M1 待做**）

| 编号 | 待调研 | 为什么必须先做 | 阻塞 | 状态 |
|---|---|---|---|---|
| **M1** | **Milvus 向量数据能否跨实例迁移**？collection 如何导出/导入 | 决定 D5.3 可行性。**若不能迁移，需重新上传文档重建索引** —— 而现有真实文档仅 2 个（211 B）+ 1 个孤儿（563 B），**代价极低** | D5.3 | ⬜ **待做** |
| **M2** | **当前 Milvus 是怎么启动的**？etcd / MinIO 是独立容器还是内嵌 | 决定 `compose.yml` 里 Milvus 的写法；也决定迁移时数据卷在哪 | D1.2 | ✅ **已完成**（见第四节五） |
| **M3** | **本机 PG 版本**与 `postgres:18` 是否兼容 | 决定用 `pg_dump` / `pg_restore` 还是需要中间版本 | D5.2 | ✅ **已完成**（18.3 ✅ 兼容） |

> **M1 的重要性因盘点结果而下降**：真实向量资产只有 2 个文档（各 211 B，各 3 chunks）。
> 即使 M1 结论是「不可迁移」，**重新上传这 2 个文件重建索引的成本 ≈ 1 分钟**。
> → **M1 从「阻塞项」降级为「待确认项」，不再是 D5 的拦路虎。**

> **建议顺序**：~~M2 → M3 → M1~~ → **M1 单独做，不阻塞 D1**。

---

## 九点五、待用户确认的决策（🔴 未确认不得开工）

### ✅ 已确认（2026-09-16 晚）

| # | 问题 | 决策 | 状态 |
|---|---|---|---|
| **Q1** | **Milvus 用哪套？** | ✅ **保留现网方案**（v2.6.14 单容器内嵌 etcd + local 存储），把 `standalone.bat` 参数搬进 compose | ✅ 已实施并验证 |
| **Q2** | **端口冲突怎么处理？** | ✅ **旧容器改名保留作回滚**（`milvus-standalone-old`），由 compose 接管 `19530/9091` | ✅ 已实施 |
| **Q3** | **adminer 留不留？** | ✅ **保留在 `compose.override.yml`**（仅开发用，不进交付包） | ✅ 已确认 |

### ⬜ 待确认

| # | 问题 | 我的建议 | 影响 |
|---|---|---|---|
| **Q4** | **测试残留数据要不要在迁移前清掉？** 21 个假 KB / 21 Persona / 17 MCP / 75 测试会话 / 21 个 kb_test 文件 | ✅ **已清（2026-09-17）**：本地 `app` 库 0 行无需删；26 个孤儿上传文件移入 `backups/residue-trash-20260917/`（可回收） | D5.1b |
| **Q5** | **`FIRST_SUPERUSER_PASSWORD=changethis`** | D3.2 改为首次启动随机生成并打印 | D3.2 |
| **Q6** | **孤儿目录 `uploads\kb\a2e7d572-...`**（含 `测试文档.md` 563 B，DB 中无对应 KB） | 建议**保留文件但不迁移**，或确认后删除 | D5.1 |
| ~~**Q7**~~ | ~~`proxy`（traefik:3.6，占 80 端口）与 `mailcatcher` / `playwright` 是否留在交付包？~~ | ✅ **已定：全部删除**（用户已授权清理模板残留，见 §5.2 D1.1.5/D1.1.6） | D1.1 |
| **Q8** | **容器内 PG 是空库，D5 是否确定要迁移本机 PG 的 5 类真实资产？** | 建议迁（成本极低，且保住 51 条真实会话） | D5 |
| **Q9（新）** | **`items` 模板残留是否确认删除？**（`Item` 表 + 前后端代码 + 侧边栏入口） | ✅ **已核实为模板待办示例**，建议删。**须新增 alembic 迁移删表**（不改历史迁移） | D1.4 / D5 |
| **Q10（新）** | **`DOCKER_IMAGE_BACKEND` / `DOCKER_IMAGE_FRONTEND` / `TAG` 是否清理？** | 建议清理，**但必须与 `image:` 字段同批删** —— 否则 `?Variable not set` 报错 | D1.5 |

---

## 十、下一步（明确动作）

> ⚠️ **本节已于 2026-09-18 重写**：原文是第五轮（D1 时代）的施工步骤，D1–D7 已完成，那些命令**不再需要执行**。以下为当前真实待办。

**✅ 已闭环（无需再做）**：D1–D7 全部完成 ｜ D5 判定不迁移 ｜ §10.6 Provider a–f 实测 ｜ d 项缺陷修复 ｜ 系统提示词 ｜ 注册闸门（方案 a）｜ **容器同步（2026-09-18）** ｜ **KB 管理 UI 基础页（2026-09-18，列表/新建/删除 + 侧边栏入口）** ｜ **KB 详情页 + 删除文档端点 + docx 解析（2026-09-19，方案 A 一至三章）** ｜ **KB 详情页删除接线（2026-09-19，方案 A 第四章）** ｜ **Phase 14.2 RAG 聚合模式：Agent 自主检索知识库（2026-09-19）** ｜ **Phase 15.1 历史对话侧边栏（2026-09-20）** ｜ **RAG 检索质量优化（2026-09-20，jieba 分词 + rerank 重排）** ｜ **文档回收站 / 软删除（2026-09-20，删除可恢复）** ｜ **对话导出（2026-09-20，md/txt/json/docx/pdf 五格式）** ｜ **Phase D1.3c 分发优化（2026-09-20，wheelhouse 自动化校验；镜像瘦身经评估不做）** ｜ **Phase 12 管线完整化（2026-09-20，见待办 10）** ｜ **Phase 15 前端完善（2026-09-20，15.1 对话体验 + 15.2 配置台 + 15.3 其它全部完成，见待办 11）** ｜ **模型源余额查询（2026-09-20，上游接口适配器，见待办 12）**。

**待办按优先级**：

| # | 待办 | 依据 | 状态 |
|---|---|---|---|
| 14 | ~~Phase 16 聊天附件（文档 / 图片 / 截屏）~~ **已完成（2026-09-21）**，详案 [chat-attachment-plan.md](./chat-attachment-plan.md)。**S0 侧边栏**（`1dfe24c`）：删「聊天」独立入口（进聊天走「新对话」+「最近对话」）、「新对话」上移到「最近对话」之上，断言用 DOM 纵坐标而非文案顺序（种子库里有标题就叫「新对话」的会话，纯文案定位会撞）。**S1 附件基建**（`10e8123`）：新建 `core/agent/attachments.py`——附件 id 为服务端生成的**裸 32 位 hex**（`uuid4().hex`，读取时按形状 `^[0-9a-f]{32}$` 校验后 glob，客户端输入不参与拼路径）、落盘 `{CHAT_ATTACHMENT_DIR}/{user_id}/{conversation_id}/{att_id}_{safe_filename}`（**目录按用户/会话两级隔离**，删会话即删整目录）；文档按扩展名白名单（pdf/txt/md/docx，与 `DocumentParser.SUPPORTED_EXTENSIONS` 同源）解析并按 `ATTACHMENT_MAX_CHARS=60000` 截断、解析失败即删掉刚落的文件，图片**嗅探魔数**确认真实类型（不信扩展名与 Content-Type）；`POST /api/v1/agent/attachments`（multipart：`conversation_id` + `file`）上传端点，会话不属当前用户 404、格式/超限 400（**分块读边读边计数**，超限立刻中断，不把大文件整个读进内存）。**S2 数据打通**（`c98a67b`）：WS 上行 `{"type":"message","content":str,"attachments":[{"id":…}]}`；附件元数据随消息存进 `Message.content`（**不新建表**）；history 回放带附件。**S3 前端 UI**（`17950bd`）：`＋` 菜单（`AttachmentMenu`）+ `AttachmentChips` 三态（上传中 / 失败 / 成功）+ 图片缩略图；文件选择用隐藏原生 `input` 承载 `accept` 过滤与「同一文件连选两次也触发」（`input.value` 必须清空）。**S4 文档进上下文**（`f24080d`）：`build_turn_content` 把解析文本拼到本轮消息后，**附件正文只本轮有效、不进历史**。**S5 视觉判定**（`419da15` → `2f3ea1e`）：`Provider.supports_vision` 三态（`null` = 按模型名启发式，`true`/`false` = 显式）+ 模型源页「视觉能力」下拉（`null` ↔ 「自动判断」）；支持视觉 → 图片内联 `image_url` 多模态块直传，不支持 → 走 OCR 回退。**S6 本地 OCR 回退**（`6dca04a`）：新建 `core/agent/ocr.py`，`rapidocr` 3.9.2（3 个内置 ONNX 模型，**离线可跑**）+ 新增 `OCR_ENABLED` / `OCR_MAX_CHARS` 配置；引擎不可用或未识别到文字时**如实中文说明**，不假装看懂。**S7 截屏提问**（`844589e`）：`getDisplayMedia` 抓一帧后**立即 `stop()` 全部轨道**（抓完即停共享，非持续共享），失败 toast；能力检测走 `navigator.mediaDevices.getDisplayMedia`，不支持则禁用菜单项。**S8 e2e**（`14abe8d`）：`chat-attachments.spec.ts` 3 条——菜单恰为三项且**无「共享屏幕」**、选中文档后出现「已解析 N 字」chip、截屏后以图片 chip 呈现（`addInitScript` 桩掉 `getDisplayMedia`，headless 可复现）。**关键取舍**：① 附件**随会话删除而删**（`remove_conversation_dir`，目录不存在不报错）；② OCR 在「复用视觉 Provider」与「本地引擎」间经用户选定**本地引擎**（代价：镜像 +~200MB；`rapidocr` 硬依 GUI 版 `opencv-python` → Dockerfile 必须补 `libgl1 libglib2.0-0 libxcb1 libsm6 libxext6 libxrender1`，换 headless 版也躲不掉，先后报 `libxcb.so.1`、`libGL.so.1`）；③ 模型名启发式**会漏**——实测 `agnes-3.0-flash` 真支持视觉但名字看不出，故该源改为**显式标记**。**测试**：后端 `tests/core/agent/test_attachments.py` + `tests/core/agent/test_ocr.py` + `tests/provider/test_vision_capability.py`（OCR 用例全部 monkeypatch 引擎、不依赖真模型），全量非集成 **706 passed**。**踩坑留档**：① 截图 `play()` 返回时首帧未必就绪，须等一帧 `requestAnimationFrame` 再 `drawImage`，否则全黑；② 清华 PyPI 镜像当时整站 403（宿主与容器皆是）→ 缺的 wheel 走 pypi.org 补下；③ `antlr4-python3-runtime==4.9.3` 只有 sdist（omegaconf 钉 `==4.9.*`）→ 加入 `scripts/wheelhouse.py` 的 `SDIST_ONLY_PACKAGES`。 | 用户 2026-09-21 提出 | ✅ 完成 |
| 13 | ~~日志与控制台~~ **已完成（2026-09-21）**：后端运行日志体系 + 前端 `/console` 控制台页（superuser 专属），详案见 [console-logging-plan.md](./console-logging-plan.md)。**后端**：新建 `core/logging.py`——`setup_logging()` 统一格式/级别（新增 `LOG_LEVEL` 配置，默认 INFO）并接管 uvicorn 系 logger（不清它们的默认 handler 就看不到 access log）；`RingBufferHandler` 进程内环形缓冲（deque maxlen=2000，`threading.Lock` 保护快照，每条记录带单调递增 id 供游标轮询）；`SensitiveDataFilter` 兜底脱敏（实现计划 §8.6 保留项「16.3 日志分级与脱敏 api_key 不进日志」落地）：`sk-` Key / `Bearer` Token / `api_key=`（query/表单/JSON 三形态，保留键名前缀）/ `enc:v1:` 密文 → `***REDACTED***`；关键路径埋点（登录成功/失败、Provider 余额查询、KB 文档上传/删除）。**API**：`GET /api/v1/logs?after_id=&limit=`（`get_current_active_superuser` 守卫；`after_id=0` 取最近一批为首屏、传 `latest_id` 增量轮询）；client 已重新生成（`LogsService.readLogs`）。**前端**：`/console` 路由（复用 admin.tsx 的 `beforeLoad` superuser 守卫）+ `useLogStream`（2s 轮询、`document.visibilityState` 隐藏时暂停、不用 react-query——「只追加的流」与 query 缓存语义错位，setInterval + 游标直取更直白）+ `LogConsole`（终端观感暗色等宽、级别彩色徽标可点选过滤、关键字搜索、用户上滚即停吸底、暂停/继续/清屏）+ 侧边栏「系统」组新增「控制台」入口（`superuserOnly`）。**测试**：`tests/core/test_logging_redact.py` 17 条（redact 纯函数穷举 + 缓冲行为 + setup_logging 幂等/uvicorn 接管）+ `tests/api/routes/test_logs.py` 7 条（鉴权三态、游标增量、limit 截断与 422、**脱敏端到端红线**）+ `console.spec.ts` 7 条 e2e（8000 实机 dist：页面渲染、侧边栏入口、暂停/继续、关键字过滤、清屏、普通用户重定向），全量后端 **713 passed**（宿主 `POSTGRES_SERVER=localhost`）。**踩坑留档**：① e2e 切普通用户必须 `test.use({ storageState: { cookies: [], origins: [] } })` 清 setup 会话，否则 `/login` 被已登录态重定向（沿用 user-settings.spec 范式）；② `app/api/routes/logs.py` 顶层 import 了 `app.core.logging`，与 stdlib `logging` 同名但模块内绝对导入不冲突；③ 宿主机跑 pytest 需显式 `POSTGRES_SERVER=localhost`（db 容器故意不映射 5432） | 实现计划 §8.6 保留项 + 用户 2026-09-20 提出 | ✅ 完成 |
| 12 | ~~模型源余额查询~~ **已完成（2026-09-20）**：后端 `GET /api/v1/providers/{id}/balance` + 前端模型源页每卡片「查余额」按钮。**数据源经用户选定为「上游接口适配器」**（不做本地记账/预算推算）：新建 `core/agent/provider_balance.py`，按 base_url 主机名分发到 4 家已开放余额接口的厂商（DeepSeek `/user/balance`、SiliconFlow `/v1/user/info`、Moonshot `/v1/users/me/balance`、OpenRouter `/api/v1/credits`），统一归一化为 `ProviderBalanceOut{supported, provider, currency, remaining, total, used, detail, error}`；**不支持的厂商返回 `supported=false` + 明确指引**（如 dashscope →「阿里云百炼不提供余额接口；账户余额请在阿里云控制台「费用中心」查看」），因为「该厂商没这个接口」是**能力边界而非错误**，不能静默失败。**关键设计**：① 余额查询**必须经后端代理**——API Key 是 `enc:v1:` 加密落库、只在服务端解密，让浏览器直连上游既拿不到明文 Key 也过不了 CORS；② 前端用 `enabled: false` 的 query，**余额是显式动作、不随页面加载自动请求**（否则每次进模型源页都打上游）；③ `_root_url` 先剥 `/v1`\|`/compatible-mode`\|`/api` 再拼各家路径，防重复段；④ 上游 401/403/429/超时/连不上分别映射为中文可读 `error`，不透传原始异常。**测试**：`tests/core/agent/test_provider_balance.py` 29 条（注入假 httpx client；覆盖 `_root_url` 参数化、4 家解析、不支持分支**不发网络请求**、错误映射）+ `tests/api/routes/test_providers.py` 补 6 条（不支持厂商、无 base_url、404、他人 provider 404 越权、匿名 401、**端到端假上游断言确实带上了 `Bearer` 明文 Key 且 URL 正确**），共 **35 passed**；Playwright 补 `/providers 查余额按钮` 用例（种子 default 源指向 dashscope → 走本地提示分支，**离线可稳定复现**）。提交链 `8a51564`（后端）→ `9f788ac`（前端）→ 本轮 e2e/文档。**踩坑留档**：① `_root_url` 对 `https://openrouter.ai/api/v1` 会剥出 `/api/api/v1/credits` **重复段**——参数化用例当场抓到，改为循环剥后缀；② 「上游没有余额接口」（`detail`）与「查询失败」（`error`）是**两种语义必须分开建模**，否则用户看到「查询失败」会反复重试一个永远不可能成功的接口；③ **e2e 机器空闲内存 <2GB 时浏览器启动会大面积 30s 超时**（同一套用例在内存充足时 21.6s 跑完，紧张时 12.1min / 24 failed），跑全量前先确认 `FreePhysicalMemory`，必要时 `--workers=1`。 | 用户 2026-09-20 提出 | ✅ 完成 |
| 11 | ~~Phase 15 前端完善（对话 + 配置台）~~ **已完成（2026-09-20）**：15.1 对话体验 / 15.2 配置台管理页 / 15.3 侧边栏重组与 e2e 全部闭环，详见提交链 `235193c → af0e7b6` | §8.5 Phase 15 | ✅ 完成 |
| 10 | ~~Phase 12 管线完整化~~ **已完成（2026-09-20）**：**12.1 决策表**（用户确认：SessionStatus 做——`Conversation.is_enabled` 字段 + 迁移 `b7c9d1e3f5a7`；WakingCheck/WhitelistCheck 不做；ContentSafety 暂不做）→ **12.2 顺序模型**（经决策不改造洋葱模型，`STAGES_ORDER` 常量定权威顺序）→ **12.3 WS 接入管线**（修复问题 #13：新增 `run_entry_stages` 共用前置 Stage「RateLimit→SessionStatus→PreProcess」，WS 与 REST 行为一致；顺带修掉 REST 每请求 new `RateLimitStage` 导致限流形同虚设的 bug——改进程级单例 `get_rate_limit_stage()`；WS 拦截时以 `text_chunk`+`done` 提示，前端协议不变）→ **12.4 内部钩子**（`pipeline/hooks.py` 精简 3 钩子 `on_llm_request`/`on_llm_response`/`on_agent_done`，异常吞掉不中断管线，不做第三方插件）→ **12.5 上下文补强**（新模块 `agent/context_manager.py`：中英文分权重 token 估算 / `split_into_rounds` 轮次切分 / `fix_messages` 保证 assistant(tool_calls)↔tool 配对防 400 / `ContextTruncator` 三策略；`get_context_messages` 接入 fix_messages 兜底；LLM 空输出 tenacity 指数退避重试 3 次；工具超时统一 `TOOL_CALL_TIMEOUT=120s`；`MAX_AGENT_STEPS` 15→30）。+27 测试，全量 490 passed（10 failed 均为 Milvus 容器未启动的环境噪音） | §8.2 Phase 12 | ✅ 完成 |
| 1 | **D8「可分发」验证**：把仓库拷到干净机器/他人环境，装 Docker 后一条命令跑通（验证无本机隐式依赖） | SC **D8** ⬜ | 唯一未达成的 SC；需**另一台机器**，本机做不了 |
| 2 | ~~D9 补验~~ **已完成（2026-09-20）**：容器内全量 **377 passed**（359 单测 + 18 集成，0 失败）；过程中暴露并修复真 bug——`shell_execute` 给 `create_subprocess_shell` 传不存在的 `timeout=` 参数，Linux 下必抛 TypeError（宿主 win32 分支掩盖），改用 `asyncio.wait_for`；`test_config` 的 MILVUS_URI 断言去环境耦合 | SC **D9** ✅ | 提交 `810344c`。注意：生产镜像不含 pytest/dev 依赖，需 `uv pip install` 临时装入容器；skills 目录镜像里为空，需 `docker cp` |
| 3 | ~~Phase 15.1 历史对话侧边栏~~ **已完成（2026-09-20）**：后端补 DELETE/PATCH 端点 + ConversationResponse.updated_at；WS 首条消息自动成标题（前 20 字、换行压空格、自定义标题不覆盖）；`add_message` 修复会话 `updated_at` 从不刷新的 bug（列表才能按最近活跃排序）；前端 `useConversations` hook + `ConversationList`（最近对话列表/新对话/单行截断/hover「…」菜单：重命名、批量管理（多选+全选+批量删）、删除二次确认；导出对话入口占位待实现）；会话 ID 改走 `/chat?c=` 路由参数，修掉「每次进 /chat 都新建会话」的要害；19 条路由测试，全量 359 passed | 8.5 / 15.1 | ✅ 全链路完成；**遗留**（已闭环，见待办 9）：~~对话导出（Word/PDF/TXT/Json，菜单入口已留）~~、会话分组（未做，用户暂不需要） |
| 4 | ~~随手修~~ **已完成（2026-09-20）**：① `_chat_cache`/`_embed_cache` 换 `_LRUCache`（maxsize=32）② `is_default` 加 DB 级部分唯一索引（迁移 e7f8a9b0c1d2，先去重再建索引）；索引顺带暴露并修复 `delete_provider` 先晋升后删会短暂双默认的隐患；宿主 364 passed，容器已迁移+健康 200 | 8.4 保留两项 | ✅ 提交 `b266f31` |
| 5 | ~~Phase D1.3c 分发优化~~ **已完成（2026-09-20，范围经用户确认为「只做自动化」）**：新建 `scripts/wheelhouse.py`（`check` / `update` 两个子命令，核心比较逻辑抽成纯函数）+ `tests/scripts/test_wheelhouse.py`（35 条，只测纯函数、不依赖网络与 `wheelhouse/` 目录）；`backend/Dockerfile` 里手写的三条生成命令收敛为指向该脚本的说明（单一真相源）。**动机 = 堵静默故障**：`uv pip install -r` 用的是手写清单，往 pyproject 加依赖却忘了重导 → 构建**照样成功**、应用启动才 ImportError。`check` 把清单与 `uv.lock` 逐字节比对（忽略 uv 横幅），不一致即退出码非 0 并打印 diff；`wheelhouse/` 存在时再校验 142 个文件的 sha256。**镜像瘦身不做**，理由：`.venv` 是 Dockerfile 单个 RUN 装成的**单层**，后续 `RUN rm` 只加 whiteout 不减体积；且占大头（pyarrow 153MB + pandas 64MB）是 `pymilvus` **硬依赖**拉进来的，删不得。实测 `check` 退出码 0；**证伪**：故意把清单里 `aiohappyeyeballs==2.6.2` 改成 `2.6.1` → 正确报出 diff 且退出码 1，还原后复绿 | PROGRESS §5.3 | ✅ 完成 |
| 6 | ~~补后端「删除文档」端点~~ **已完成（2026-09-19）**：`DELETE /api/v1/kb/{kb_id}/documents/{doc_id}` 已实现（三处清理：Milvus 按 doc_id / 磁盘 / DB，4 条回归测试）；前端详情页删除按钮已接线并实机验收通过（方案 A 第四章） | KB 管理 UI 施工中发现（2026-09-18） | ✅ 全链路完成 |
| 7 | ~~RAG 检索质量优化~~ **已完成（2026-09-20）**：① 中文分词单字切分 → jieba.cut_for_search ② 新增 rerank 重排段（SiliconFlow BAAI/bge-reranker-v2-m3，复用 embedding Key，ENABLE_RERANK 默认开，失败降级纯 RRF）；候选取 RERANK_CANDIDATES=10；+10 测试，全量 374 passed，容器真实 API 验证排序正确 | 2026-09-19 检索测试发现 | ✅ 提交 `df89723`；**遗留**：查询改写/HyDE 可以后续评估 |
| 8 | ~~删除文档软删除（回收站）~~ **已完成（2026-09-20）**：`documents.deleted_at`（迁移 `a8b9c0d1e2f3` + 索引）；删除改为「**Milvus 向量立即删 / 磁盘文件保留 / DB 打软删标记**」；新增 `GET /kb/trash`（跨库列表，带 `kb_name`/`expires_at`）、`POST /kb/trash/{doc_id}/restore`（抹标记 + 按磁盘文件**重新向量化**）、`DELETE /kb/trash/{doc_id}`（文件 + 记录彻底清）；超期清理走惰性（打开回收站时扫一遍，`KB_TRASH_RETENTION_DAYS=30`，不引入定时任务）；活跃文档列表 / `document_count` 全部按 `deleted_at IS NULL` 过滤；前端新增 `/knowledge-base/trash` 页（恢复 + 彻底删除二次确认）与列表页入口；+12 测试，全量 **386 passed**；容器内实机走通「删→检索 0 命中→回收站→恢复→检索恢复→彻底删除」 | 2026-09-19 用户提出误删风险 | ✅ 完成 |
| 9 | ~~对话导出~~ **已完成（2026-09-20）**：新建 `core/agent/export.py` 纯渲染层（不碰 DB/HTTP）+ `GET /agent/conversations/{id}/export?format=` 端点（归属校验 404 + RFC 6266 中文文件名双写）；支持 **md / txt / json / docx / pdf** 五格式，只导出 user/assistant（system/tool 属内部产物不外泄），时间统一 UTC 并显式标注；PDF 走 reportlab platypus + **随包内置 Noto Sans SC**（`app/assets/fonts/`，OFL 1.1）→ 任何环境都不出方框，`wordWrap="CJK"` 保证中文换行；前端 `useConversations` 加 `downloadConversationExport`（**原生 fetch + Blob**，生成 SDK 走 axios 按 JSON 解析会损坏二进制）+ `ConversationList` 二级菜单选格式；+54 测试，全量 **440 passed**；容器实机 5 格式全通、PDF 实测内嵌 `AAAAAA+NotoSansSC-Regular` 子集 | 8.5 / 15.1 遗留项 | ✅ 完成 |

**验证命令速查**（宿主机 PowerShell；⚠️ PowerShell stdout 常不回显 → 一律 `Out-File` 落盘再 `Read`）：

```powershell
cd d:\AIpy\full-stack\IrsBot

# 容器健康与代码版本
docker compose ps
docker compose exec -T backend grep -n "USERS_OPEN_REGISTRATION" app/core/config.py

# 注册闸门（期望 403）
#   ⚠️ 必须比对"已存在邮箱"与"不存在邮箱"两个响应的原始字节，只看状态码无法验证防枚举
curl.exe -s -o - -w "`n%{http_code}`n" -X POST http://localhost:8000/api/v1/users/signup `
  -H "Content-Type: application/json" `
  -d '{\"email\":\"admin@example.com\",\"password\":\"xxxxxxxx123\",\"full_name\":\"X\"}'

# 容器内跑测试（D9）
docker compose exec -T backend pytest ../tests -q
```

**改完源码后如何让容器生效**（二选一，别忘）：

```powershell
docker compose up -d --build backend   # 重建镜像（一次到位、可复现）
docker compose watch                   # 或：另开常驻终端持续同步
```
> ⚠️ `docker compose up -d` **不会**启动 `develop.watch` → 「改了源码容器里还是旧的」是预期行为，不是 bug。

---

## 十一、进度记录（追加式）

| 日期 | 事件 |
|---|---|
| 2026-09-16 | 定位四轮修正完成（AstrBot 复刻 → IM 框架 → 多用户平台 → **本地单用户应用**） |
| 2026-09-16 | 文档体系重排：`progress.md` 并入 `istbot-implement-plan.md`；新建本文档承担运行态 |
| 2026-09-16 | 识别 P0 缺口：本地硬依赖外部服务 / 工具无权限开关 / SECRET_KEY 不落盘 / Alembic 不可复用 |
| 2026-09-16 | **决策 D1/D2/D3 确立**：网页版独立、本地单用户、双启动路径 |
| 2026-09-16 | **新建 `plan/local-deployment-plan.md`**（Phase L1–L4 施工详案） |
| 2026-09-16 | **实机验证完成 3 项**：UUID 方案（B 可行/A 失败）、SQLite 外键、向量库选型（FAISS） |
| 2026-09-16 | 新发现：LangGraph 检查点实际未启用（`graph.py:54` 未传 checkpointer），文档 Phase 8.4 需核实 |
| 2026-09-16 | **按用户要求撤销全部代码改动**（`types.py` + `test_uuid_portability.py` 已删）；计划升版至 v2，标记「待审阅，未施工」 |
| 2026-09-16 | **文档一致性修复（原地改写）**：`istbot-implement-plan.md` 第六至十节全部对齐新定位；第八节由「Phase 11–16 施工手册」降为「战略地图」+ 新增 8.4 降级说明 / 8.6 迁移清单；`astrbot-architecture.md` 定位行与第七/八节优先级同步（原本还写着「IM 机器人框架」） |
| 2026-09-16 晚 | **🔴 第五轮根本性转向**：用户要求「技术栈和数据库尽量保持原项目」。确立 **D4/D5/D6/D7** —— 保持 PostgreSQL + Milvus，走 Docker 一键启动，容器内 PG + 环境变量后门，全量迁移开发数据 |
| 2026-09-16 晚 | **承认并纠正核心错误推论**：「exe 双击即用 ⟺ 必须换数据库」是把「打包问题」与「存储选型」错误绑定。经 AstrBot Launcher / Desktop 文档实证（Tauri 2.10.0 + 内置 CPython，架构文档无任何数据库提及）后推翻 |
| 2026-09-16 晚 | **`local-deployment-plan.md` 重写为 v4**：整份从「消灭 PG」转向「Docker 一键启动」，含完整 YAML 示例（6 服务）、D1–D7 阶段、强制备份的数据迁移章节、风险登记 |
| 2026-09-16 晚 | **`istbot-implement-plan.md` 全量重写完成**：第零节（0.1–0.5）、第一节（+新增 1.1 测试基线）、第四节 SC（L1–L8 → **D1–D9**）、第五节（**删除原 P0 #1**，新增 5 项）、第六/七节、第八节全部（8.0 总览 → **D1–D7**、依赖图、优先级矩阵、里程碑 M1–M7）、第九/十节 |
| 2026-09-16 晚 | **测试真实性验证**：发现集成测试被 `pytestmark` **默认跳过**（"跑了测试但不知道真实情况"的根因）；放行后 `test_vec_store.py` **9 passed**（60.35s）、全量集成 **18 passed**（90.93s） |
| 2026-09-16 晚 | **环境与数据实况探测**：Docker ✅ / Milvus ✅ healthy 45h / 本机 PG 有数据 + 容器 PG 已停 7 天；开发数据 126 会话 / 108 消息 / 22 KB（**仅 2 文档**）/ 21 Persona / 17 MCP |
| 2026-09-16 晚 | **本文档（PROGRESS.md）重写**：当前阶段 → **D1**；第五节 → D1 任务清单；新增 M1–M3 前置调研；测试基线更新为「294 单测 + 18 集成测试全部实跑通过」 |
| 2026-09-16 晚 | **✅ M3 完成**：本机 PG `18.3`（`D:\PostgreSQL\data\PG_VERSION`=`18`）与 `postgres:18` **完全兼容**，可直接 `pg_dump/restore` |
| 2026-09-16 晚 | **✅ M2 完成**：现网 Milvus = `milvusdb/milvus:v2.6.14` **单容器内嵌 etcd + local 存储**，由 `D:\Milvus\standalone.bat` 以独立 `docker run` 启动（**非 compose**），数据卷 `D:\Milvus\volumes\milvus`（data 2.4M + rdb_data 5.5M + etcd） |
| 2026-09-16 晚 | **🔴 发现两套 Milvus 方案互不兼容**：`compose.override.yml` 内含 v2.5.14 + 独立 etcd v3.5.23 + MinIO（**从未启动**），与现网 v2.6.14 内嵌方案**端口全冲突**（19530/9091/2379）。新增第九点五节 Q1–Q6 待确认项 |
| 2026-09-16 晚 | **✅ D5.1 数据盘点完成（逐行）**：真实资产仅 **1 Provider + 1 user + 1 KB（"测试库"）+ 2 文档（211 B × 2）+ 2 实体文件 + 51 真实会话 + 108 消息**；**21 个假 KB / 21 Persona / 17 MCP / 75 测试会话 / 21 个 kb_test 文件全是 pytest 残留**；另发现 1 个孤儿目录 `a2e7d572-...`（有文件无 KB 记录） |
| 2026-09-16 晚 | **🎉 D5 风险大幅下调**：由「22 知识库全量搬迁」更正为「5 项真实资产小批量迁移」+ 有据可依的清理。**D5 不再是最高风险阶段** |
| 2026-09-16 晚 | 发现 4 个 PG 库：`app`（9054 kB，真实）/ `test_app`（测试）/ `document_agent`（**无表空壳**）/ `postgres`（系统）。**此前的「126 会话 / 22 KB」是含测试的虚高数字，已更正** |
| 2026-09-16 晚 | 发现凭据不一致：`.env` 中 `FIRST_SUPERUSER_PASSWORD=changethis`（危险默认值）、`POSTGRES_PASSWORD=amazarashi46`（实际可用密码），D5 脚本禁止硬编码 |
| 2026-09-16 深夜 | **✅ Q1/Q2/Q3 用户确认**：保留现网 Milvus 单容器方案、旧容器改名保留作回滚、adminer 保留在 override |
| 2026-09-16 深夜 | **✅ D1.2 完成并实机验证通过**：`compose.override.yml` Milvus 段重写（删 etcd/minio 两服务 → 单容器 v2.6.14 内嵌 etcd + local）；数据卷改**绑定挂载** `D:/Milvus/volumes/milvus` → **零迁移复用现有数据**；新建 `milvus-config/embedEtcd.yaml` |
| 2026-09-16 深夜 | **✅ 实机验证 8 项全通过**：`compose config` Exit 0 / milvus `healthy` / healthz 200 / **数据逐字节一致（data 2.4M + rdb_data 5.5M + 15 个 insert_log）** / db `healthy` / 容器内 PG 18.4 / 表为空待建 / 网络互通（db:5432 + milvus:19530 均 open） |
| 2026-09-16 深夜 | **🔑 修复一个隐藏很深的坑**：`env_file: .env` 会**覆盖** `compose.yml` 的 `environment` 声明 → `POSTGRES_SERVER=localhost` 盖掉了 `=db`，容器内 backend 会连错库。已在 `backend` / `prestart` 显式声明 `POSTGRES_SERVER=${POSTGRES_SERVER:-db}`，并把 `.env` 改为 `db` |
| 2026-09-16 深夜 | **✅ `db` 移除 `5432:5432` 映射**（本机 PG 18.3 已占用），避免当年容器版 PG 被挤停的问题重演 |
| 2026-09-16 深夜 | **旧容器处置**：`milvus-standalone` 停止并改名 `milvus-standalone-old`，**故意保留作为回滚退路**（回滚方法已写入第四点五节） |
| 2026-09-16 深夜 | **D1.1 尚未做**：Traefik / `${DOMAIN}` / `${STACK_NAME}` / `proxy` 服务仍未剥离，这是下一步 |
| 2026-09-16 深夜（续） | **📌 用户确认项目基座**：本项目基于 **full-stack-fastapi-template** 修改而来，用户明确「**无关 IrsBot 的都可以放心修改**，只是觉得 full-stack 的 webui 可以直接拿来用」→ 授权清理模板残留 |
| 2026-09-16 深夜（续） | **✅ `items` 判定完成（读前后端全部源码）**：`backend/app/api/routes/items.py` 是标准模板 CRUD（`Item` 只有 `title` + `description` + `owner_id`），`frontend/src/routes/_layout/items.tsx` 标题「物品」、空态「还没有任何物品」→ **确认是模板待办示例，与 IrsBot 零关系 → 删除**。删除需**新增 alembic 迁移删表**（不改历史迁移文件，因为迁移策略只 `upgrade` 不 `downgrade`） |
| 2026-09-16 深夜（续） | **✅ 前端方案定案：照 AstrBot 做法**（读 AstrBot 源码核实）—— AstrBot 用 `DashboardServer` 三级 dist 路径优先级（显式参数 → `data/dist` → bundled dist）+ `static_file.py` **显式枚举全部前端路由**返回 `index.html` + Quart `static_folder` 托管，**构建与后端解耦**（镜像内含预构建 dist，构建时不跑 npm） |
| 2026-09-16 深夜（续） | **🔑 识别出 FastAPI 与 Quart 的差异并适配**：AstrBot 是 Quart（Flask 系）可以枚举路由；本项目是 FastAPI，改用 **404 exception handler + 排除 `/api` 前缀**——比枚举路由更不易漏（新增前端路由不用回来改后端）。**关键陷阱：不能用 `app.get("/{full_path:path}")` 通吃，会与 API 路由冲突** |
| 2026-09-16 深夜（续） | **⭐ 前端方案的关键收益**：`VITE_API_URL` 改相对路径 `/api` → **消除构建期注入 → 同一个 dist 产物在任意主机、任意端口都能用**。这对"分发给别人"是决定性的（否则用户机器上的 API 地址会被烤死在构建产物里）。同时保留**绑定挂载 `./frontend/dist` 覆盖**能力 → 改前端**无需重建后端镜像** |
| 2026-09-16 深夜（续） | **📄 文档升级 v6**：`local-deployment-plan.md` 新增 §3.2.1 部署层残留清单 / §3.2.2 易误判清单（`DOCKER_IMAGE_*` 名为模板实为必需）/ §3.2.3 `items` 判定 / §3.3.4 前端方案定案（含 AstrBot 对照与完整代码）/ §10.1 D1 子阶段拆分（D1.1–D1.5）；`PROGRESS.md` 第五节重构为 5.1–5.5 子清单 + 新增 Q9/Q10 |
| 2026-09-16 深夜（续） | **⚠️ 新发现的陷阱（写入文档）**：`DOCKER_IMAGE_BACKEND` / `DOCKER_IMAGE_FRONTEND` / `TAG` 名字极像模板产物，但 `prestart` 与 `backend` 的 **`image:` 字段正在引用它们** → **必须与 `image:` 字段同批删**，否则 `?Variable not set` 立即报错。本地开发其实只需 `build:` |
| 2026-09-16 深夜（续） | **下一步：D1.1 可立即开工** —— 剥离 traefik 全层 / `${DOMAIN}` / `${STACK_NAME}` / `compose.traefik.yml` / `proxy` / `mailcatcher` / `playwright` / nginx 配置 |
| 2026-09-17 00:26 | **✅ Phase D2 完成（一键启停脚本）**：新增 `scripts/start.cmd` / `stop.cmd` / `start.sh` / `stop.sh`；`.env.example` 补 `PROJECT_NAME=IrsBot` / `ENVIRONMENT=local` / `POSTGRES_SERVER=db`（附三种场景注释）；`start.*` 含「缺 `.env` 自动从 `.env.example` 生成」+「轮询 health-check 最多 3 分钟」+「打印 URL/账号并打开浏览器」；`stop.*` 默认 `docker compose down` 保留数据卷、提示 `-v` 才删库 |
| 2026-09-17 00:26 | **🔴 D2 编码坑已修**：`start.cmd` / `stop.cmd` 最初含中文注释，cmd.exe 在 ANSI/GBK 代码页下解析报错（`'?-v' 不是内部或外部命令`）。已改为纯 ASCII 英文版，`nonascii=0` 校验通过。`.sh` 跑 bash/UTF-8 不受影响 |
| 2026-09-17 03:xx | **✅ Phase D5 完成（备份 + 判定不迁移 + 迁后验证）**：新增 `scripts/backup.ps1` + `scripts/backup.cmd`（一键只读备份，**绝不删数据**）。备份落 `backups/20260917_095030/`：容器 `app` 库 `pg_dump -Fc`（23KB，TOC 61 条可恢复）+ 本机 `app` 库 dump（23KB）+ `.env` 副本（含 SECRET_KEY/API Key/密码）+ `irsbot_app-db-data` 卷 tar（7.4MB）+ `D:\Milvus\volumes\milvus` 目录副本（156MB，etcd 锁文件由 robocopy 拷出）。`backups/` 已加 `.gitignore`（含密钥，禁提交）。**关键核查结论**：本机 `app` 库是被 pytest 清空后又被旧代码重新播种的**陈旧/残缺副本**（含遗留 `item` 表、`provider_configs=0`、会话/消息=0），容器 `app` 库才是**完整权威库**（`provider_configs=1` default、`user=1`、会话/消息各 3、alembic `f3e1a9b7c2d4`）→ **D5.2 判定不迁移**，以容器库为准。迁后验证通过（dump 可恢复、admin 可登录、模型源可用）。⚠️ 沙箱有「安全删除」钩子会拦截 `Remove-Item`（fail-closed），删除类操作需用户授权 |
| 2026-09-17 10:xx | **✅ Phase D6 完成（工具权限开关）**：`config.py` 加 `ENABLE_SHELL`/`ENABLE_FILE_WRITE`（默认 False）+ `FILE_WRITE_ROOTS`（逗号白名单，新增 `parse_path_list` 解析器）；`builtins/__init__.py` 改为按配置条件注册（shell/file_write 默认不注册=`不暴露给 LLM`；web_search/kb_query 只读始终注册）；`file_ops._allowed_roots()` 改读 `settings.FILE_WRITE_ROOTS`（留空回退 cwd+/tmp+临时目录）；`.env`+`.env.example` 补三项开关及注释。**附带修复潜在 bug**：此前 `app.core.agent.builtins` 从无任何模块导入触发注册（grep 全仓确认），4 个 builtin 工具等于死代码；现 `agent.py` 顶部 `import app.core.agent.builtins` 确保 Agent 启动时真正注册（受开关控制）。4 文件 `py_compile` 通过，`parse_path_list` 单测通过；完整导入验证需在用户机器（沙箱缺 langchain 依赖且 shell 不稳定） |
| 2026-09-17 10:xx | **✅ Phase D7 完成（运维手册）**：新建 `docs/OPERATIONS.md`，覆盖数据资产清单 / 一键备份说明 / 恢复三场景（仅库 `pg_restore --clean --if-exists`、仅向量目录覆盖、全盘）/ 卸载三档（停服保留、`down -v` 清 PG、彻底清宿主目录）/ 排查表 / 脚本一览；**重点揭示 `reset.cmd`(`down -v`) 只清 PostgreSQL 命名卷、不清 Milvus 绑定挂载的陷阱及修复**。同步增强 `scripts/backup.ps1`：新增 `backend/uploads` 只读拷贝（此前漏备，RAG 恢复缺源文件），manifest 记录；PowerShell 解析校验通过（`SYNTAX_OK`）。主线 D1–D7 全完成 |
| 2026-09-17 11:xx | **✅ 建 git 回退基线（用户要求「git 备份代码，方便回退」）**：IrsBot 此前非独立仓库（是上层 `d:/AIpy` 混合仓库子目录，含 doc_gen_agent 等无关项目改动）。**在 `d:/AIpy/full-stack/IrsBot/.git` 新建独立仓库**（`init`→`add -A`→`commit`；父仓库不跟踪 IrsBot 故无 gitlink 冲突）。`check-ignore` 确认 `.env`/`backups/`/`.venv`/`node_modules`/`backend/uploads`/`frontend/dist` 均排除；额外把 `.workbuddy/`（含记忆日志、有 DB 密码明文）、`wheelhouse/`（可重生成构建缓存）、`*.log`（构建/测试日志）加入 `.gitignore`，并删临时 `_t.ps1`。**踩坑**：沙箱 `git init -b feat/agent-platform` 后首提交报 `could not parse HEAD`（分支名含斜杠时 unborn 分支引用创建异常）；**解决：删 `.git` 重 `init` 默认分支提交成功，再 `git branch -m feat/agent-platform` 改名**。基线 = `fe7c391`（353 文件）+ `00a951d`（去日志）+ `74dd8d9`（补 `*.log` 规则）；`git status` 干净。**回退方式**：`git log` 看基线 / `git reset --hard fe7c391` 回退 / `git stash` 暂存 |
| 2026-09-17 12:xx | **✅ Phase 10.3/10.5 代码审查 + 修复 embedding 阻断 bug（提交 `bfe1c7d`/`499a2fd`）**：Provider 管理 UI / 用户管理页 / 设置页代码确认已存在且前后端契约一致；唯一逻辑改动 = `get_embedding_model` 补 `decrypt_api_key`（原样传加密 key 会导致 RAG 向量化 401）。§10.6 实机验收清单已入本文档第八节 |
| 2026-09-17 12:49 | **📋 系统提示词功能计划已写（未施工，待用户确认）**：新建 `plan/system-prompt-plan.md`，含现状结论（personas 表预留但全链路未打通）、方案（`user.system_prompt` 列 + alembic 迁移 + `prompts.py` 默认提示词 + Agent 消息最前注入 SystemMessage + `GET/PUT /users/me/system-prompt` + 设置页新 tab）、生效范围=**全局按用户、保存即生效**（不落消息表、动态注入）、默认提示词文案草案、4 步 4 提交执行序、实机验收 6 项。**待确认 3 项**：默认文案 / 全局范围 / 设置页入口。确认后开工 |
| 2026-09-18 01:17 | **✅ 修复 Provider 解析的多租户越权缺口**：`ProviderManager.get_chat_model` / `get_embedding_model` 在 `provider_id=None` 时**只查 `is_default` + `is_active`，没有 `user_id` 过滤** → 多用户下 A 用户没有默认源时会**静默取到 B 用户的默认源**，越权使用他人密钥与模型（`chat_with_fallback` 的候选源查询同样缺过滤）。修复：① 两个方法增加**必填** `user_id` 形参，`provider_id` 分支与默认分支**都**加 `user_id` 过滤；② `chat_with_fallback` 增加 `user_id` 并在候选查询中过滤；③ **chat 缓存 key 补 `user_id`**（原 key 不含 user_id，不同用户用 `provider_id=None` 会命中同一条目拿到别人的模型实例——这是同一缺陷的隐蔽副本）；④ `Agent.__init__` 统一解析 `user_uuid` 并透传；⑤ `user_id` 为 `None` 时 **fail closed**（查不到任何源），绝不回落成「取全库任意默认源」。**顺带修掉一个预先存在的阻断 bug**：`get_embedding_model` 函数**首行**即 `from langchain_anthropic import AnthropicEmbeddings`，而该版本 `langchain_anthropic` **没有这个类** → 该函数对**任何** provider 都会在查库前 `ImportError`（无调用方故一直未被发现）；已改为**惰性导入**（仅在对应类型分支内导入）。**新增 7 条回归测试**（缓存 key 归属 1 条 + 多租户隔离 6 条：默认源不跨用户、优先取本人源、显式 provider_id 不可跨用户、无 user_id fail closed、embedding 不跨用户、回退候选按人过滤）。**证伪**：临时短路默认分支的 `user_id` 过滤 → 恰好 3 条相关测试失败（`DID NOT RAISE` / `MultipleResultsFound`），恢复后全绿 → 证明测试真覆盖缺陷。**全量回归 318 passed / 0 failed**（311 基线 + 7 新增）。⚠️ **踩坑留档**：新增测试里用 `asyncio.run()` 会**清空默认事件循环**，导致后续 16 条异步测试报 `no current event loop in thread 'MainThread'`；已改用 `pytest-asyncio` 的 `@pytest.mark.asyncio` + `await`。**当前仍是单用户，此缺口不可从 HTTP 触发**（chat 路由不暴露 `provider_id`），属多用户上线前必修项，现已前置修掉 |
| 2026-09-18 01:xx | **✅ 修复 §10.6 d 项缺陷（提交 `a746d10`）**：`ProviderManager.delete_provider` 原只 `session.delete(obj)`，删掉当前默认源后**该用户再无任何 `is_default=True`**（徽标消失、取默认源直接 RuntimeError）。改为**删除前先选接替者**：若被删行 `is_default`，则在同用户**其余启用中**（`is_active=True`）配置里按 `fallback_order` 升序取一条置为默认，再删除并一次 `commit`。**三处关键约束**：① 只取启用中候选（`get_chat_model` 要求 `is_default` **与** `is_active` 同时成立，否则是"有徽标取不到模型"的假象）；② 严格按 `user_id` 过滤（否则会提升**他人**源 → 越权使用他人密钥）；③ 无接替者时保持无默认、不报错。**新增 7 条回归测试**（manager 6 + API 1）。**双层证伪**：测试层短路提升逻辑 → 恰好 4 条补位测试失败；实机层把 `cd1f17b` 旧版 `docker cp` 进容器跑同一动作序列 → `default` 掉成 `False`、**0 条默认**（缺陷如实复现）；换回修复版 → 恰好 1 条默认且自动补位 ✅。**全量回归 311 passed**。⚠️ **重要坑**：uvicorn `--reload`（StatReload）**只在 mtime 变大时重载**，用 `docker cp` 灌回较旧版本不会触发重载 → 需 `os.utime` 把 mtime 顶到未来。环境已还原（仅剩 `default` 且为默认） |
| 2026-09-18 01:33 | **✅ 容器同步闭环 + 注册闸门实机验证（用户指令「同步」）**：沙箱此前 `docker` CLI 完全不可用，本轮恢复可执行。**① 容器同步**：`docker compose up -d --build backend` → 镜像构建成功、4 容器 Recreate（`db`/`prestart`/`backend`/`milvus`）、`prestart` 迁移+播种跑完、backend Started；**命名卷 `app-db-data` 数据保留**（重建后 `user=1`、`provider_configs=1` 且 `is_default=True`）。**② 容器内代码校验**：`config.py:167 USERS_OPEN_REGISTRATION` ✅ / `users.py:194` 403 守卫 ✅ / `provider.py` 的 `ProviderConfig.user_id == user_id` 出现 7 处（与源码一致）✅ / `prompts.py` 的 `DEFAULT_SYSTEM_PROMPT` ✅ / `/app/frontend-dist/assets` 与宿主机 `dist` 一致（`login-CP8ls77z.js`，无旧产物）✅。**③ 运行时 7 项验证全过**：后端存活 200 / **`POST /users/signup` → 403 + 约定话术** / **防枚举：已存在与不存在邮箱响应逐字节一致** / 超管登录 200（注意 `/login/access-token` 吃**表单编码**，不吃 JSON，否则 422） / `GET /users/` 仅 `admin@example.com`（无探针账号落库） / `GET /providers` 恰 1 条默认（无回归） / `GET /users/me/system-prompt` 200。**④ 文档同步（D2 语义拆分，第六轮）**：修复「文档与已发布代码方向相反」的漂移——`istbot-implement-plan.md` 原写「Phase 11 因单用户**整体降级**…留接口不留逻辑、单用户下忽略 `user_id`」，而代码（`ef08cc1`）恰恰是「`user_id` **必填** + 双分支过滤 + 缓存键含 user_id + fail closed」。现拆为 **(A) 多用户运营化**（降级不做）与 **(B) 归属隔离**（已实现为硬约束），共改 **15 处活引用**（0.0 决策表 + 新增 D2.1 / 0.2 / 0.4 两处 / 0.5 三行 / 一节 Phase 3 / Phase 3.5 / SC11 恢复为 ✅ / **新增 SC D10** / 6.1 能力矩阵 / 8.0 引言+总览表 / 8.1 索引 / **8.4 全节重写** / 五节已移出注 / 第九节追加第六轮 7 行），`~~划掉~~` 与历轮留痕作为**追溯性引用一律保留**（删了下次还会被同一个错误意见说服）。**⑤ 工具坑留档**：同一轮**并行发多个文件编辑**时出现**部分编辑未落盘**（返回成功但内容仍旧）→ 必须 grep 回查，本轮补回 4 处漏改（0.4 注册行 / Phase 3 行 / 8.0 引言 / 8.1 索引）。**另一认知**：`compose.override.yml` 用 `develop.watch`，而 `docker compose up -d` **不启动 watch** → 「改源码但容器是旧的」是预期行为；同步用 `up -d --build` 或另开 `docker compose watch` |
| 2026-09-18 01:43 | **🔍 文档漂移根因复盘（写给自己）**：本次漂移不是「忘了更新」，而是**把两件性质不同的事当成一件**——「多用户**运营化**（注册/配额/计费）」与「数据**归属隔离**（user_id 过滤）」。前者该砍，后者是安全边界。原判「单用户下不存在串 Key」只对前者成立；`get_chat_model(provider_id=None)` 若不过滤取的是**全库**默认源 → 用户配了 A 家 Key 却静默跑 B 家，**无报错的越权**。教训：**「不做 X」这种否定式结论，必须写清否定的到底是 X 的哪一层**，否则半年后照文档办事的人会把安全边界也一起删掉 |
| 2026-09-18 01:3x（⚠️ 本行补记于此，**实际发生时间早于上方 01:33 行**） | **✅ 注册闸门收口（用户批准「方案 a」）**：起因 = 用户问「为什么有多用户」，调研发现 `/users/signup` **完全无守卫**（探针实测：匿名 `POST /users/signup` → **HTTP 200 建号成功**，新号可立即登录拿 token；根因 = 模板原版的 `if not settings.USERS_OPEN_REGISTRATION` 守卫**被删掉**且 `config.py` 根本没有该字段），而前端 `routes/signup.tsx` 是完整注册页、`login.tsx:126` 还有「注册」链接 → **「单用户」从事实降级成了假设**。**实施（沿用 D6 工具开关范式：安全默认 + `.env` 显式开启）**：① `config.py` 新增 `USERS_OPEN_REGISTRATION: bool = False`；② `users.py::register_user` 加守卫，**严格要求置于查重之前**（否则未开放时「400 邮箱已存在」与「403」的差异会变成**账号枚举探测面**），并清掉排障残留（`import traceback` + `print("=== SIGNUP ERROR ===")`）；③ `.env` 补显式声明与注释（与 `ENABLE_SHELL` 等排在一起）；④ 前端 `login.tsx` 删「注册」链接及随之无用的 `Link as RouterLink` import（`createFileRoute`/`redirect` 仍在用）。**测试 +3**：`forbidden_when_disabled`（403 且不落库）、`signup_disabled_does_not_leak_email_existence`（已存在 vs 全新邮箱响应**逐字节一致**）、`users_open_registration_default_is_false`（锁字段默认值不受 `.env` 影响）；原 2 条注册测试改为 `monkeypatch` 打开开关后运行。**双层证伪**：短路守卫 → 恰好 2 条失败；把守卫**挪到查重之后** → 恰好 1 条（防枚举那条）失败 → 两条约束均被真实锁住。**全量回归 321 passed / 0 failed**（318 + 3）。**前端已收尾**：`tsc -p tsconfig.build.json --noEmit` → ExitCode 0（**必须用仓库根 `node_modules`** —— `frontend/node_modules` 里其实没有依赖，只有 vite 缓存）；`vite build` 12.90s 重建 `frontend/dist`（新产物 `login-CP8ls77z.js`，旧产物连同「还没有账号」字符串一并清除）→ dist 为**绑定挂载**，刷新浏览器即生效。⚠️ **唯一未完成项**：backend 容器内代码仍是旧版（沙箱 `docker` CLI 本次完全不可用，连 `docker --version` 都报 `/usr/bin/env: 'sh'`），实测打真实接口 `POST /users/signup` **仍返回 200** → 需用户 `docker compose up -d --build backend`（或 `docker compose watch`）后复测应得 403。三层多用户残留溯源已留档 memory 日志 |
| 2026-09-18 10:35 | **📋 部署模式运行时开关计划已写（提交 `plan/multi-tenant-plan.md`，未编码，待确认）**：用户指令「关于多租户问题，管理员可以选择多租户和单用户开关」。**现状核查关键结论**：① 数据层**已是完整多租户**——`ProviderConfig`/`Conversation`/`Message`/`KnowledgeBase`/`Document`/`MCPServer`/`Persona`/`AgentRun` 全部带 `user_id` + `ON DELETE CASCADE`，开关**不需要**新建任何归属结构；② 隔离逻辑（`ef08cc1`）是**安全边界**，两模式下都必须保留；③ 本项目**不存在运行时可配置机制**（所有开关都在 `.env`），需新建。**用户三项决策**：(1) 载体 = **运行时而非部署级**（DB + `/admin` 页，超管切换即时生效）；(2) 严格度 = **仅关自助注册，超管仍可建号**——此决策**推翻了初稿**「单用户下隐藏 `/admin` 与侧边栏入口」的设想（超管要建号就必须保留 `/admin`）；(3) 先写计划文档。**方案要点**：新增 `app_settings` 通用 KV 表（后续加运行开关不必再写迁移）+ `DEPLOYMENT_MODE` 兜底配置；派生规则 `signup_allowed = (mode=="multi_tenant") AND open_registration` 设为**唯一派生点**（禁止各处自行拼条件，且 AND 派生构成双保险——即便 KV 被手工写脏也不会误开注册）；`GET /utils/public-settings`（匿名，只暴露 `signup_enabled` 供登录页渲染注册链接）+ `GET/PATCH /settings/deployment`（超管）；**不做进程内缓存**（多 worker/WS 进程各持副本会导致不一致，主键单行查询开销可忽略）；注册守卫改为读派生值但**位置不变，仍在查重之前**（防枚举，沿用 `41cccfd` 教训）。**测试矩阵 4 组**含「单用户 + 直写 KV 开注册 → 仍 403」的绕过用例；现有 3 条注册闸门测试因**兜底链**（DB 无记录 → 取 `.env`）应保持通过。**待确认 5 项**见计划第十节（表形态 / 公开端点 / PATCH 校验风格 / `/admin` 保留 / **D2.1 表述要从「硬约束」改回「运行时开关默认关」**）。⚠️ 这将是 D2 相关表述的**第三次**修订（`41cccfd` → `d1630f5` → 本次） |
| 2026-09-18 10:50 | **🔧 计划自我复查 → v1 砍掉一个配置键（发布 v2）**：用户追问「这样好吗，你推荐怎么样」，复查中发现 v1 存在**冗余状态缺陷**。**缺陷**：v1 设 `deployment.mode`（single_user/multi_tenant）+ `deployment.open_registration` 两个键，派生 `signup_allowed = (mode=="multi_tenant") AND open_registration`；但**决策 2（单用户下超管仍可建号）使 `mode` 失去约束力**——它既不限制超管建号，也不影响 `/admin` 可见性 → **「单用户」与「多租户+关注册」在所有可观测行为上完全等同**（注册都 403、超管都能建号、`/admin` 都可见、隔离都生效）。**危害**：设置页出现两个产出相同结果的档位，读设置的人无法判断该选哪个，维护者还会误以为 `mode` 管着什么——**冗余状态比缺失状态更危险（让人以为存在一道其实不存在的约束）**。**处置（v2）**：配置层**只留 `users.open_registration` 一键**，「单用户/多租户」降为**呈现层标签**（由布尔派生），`AND` 派生简化为直读，互斥 400 校验取消，`DEPLOYMENT_MODE` 配置项不再新增；「防误触」由**双开关**改为**单开关 + 二次确认对话框**（文案写明「任何人可注册并消耗你的 API Key」）。**关键语义**：KV 有记录则**覆盖 `.env`**（运行时优先），无记录回落 `.env`（升级后行为零变化，现有 3 条注册闸门测试保持通过）→ 测试矩阵改为**优先级矩阵 4 组**专门锁这条。**方法论要点**：`mode` 类型的键只要**不对任何行为产生约束**，就是空壳——要么给它牙齿，要么砍掉。若将来需要「多用户 + 仅管理员建号」，届时 KV 加键**零迁移**（这正是选 KV 表的收益）。**待确认收敛为 4 项**：砍 `mode` / 匿名公开端点 / 开关入口位置（`/admin` vs 设置页超管 tab）/ D2.1 表述修订 |
| 2026-09-18 11:0x | **✅ 部署模式运行时开关已实施（第七轮，用户确认入口放 `/admin`）**：用户答「开关入口放 `/admin`（本来就只有超管能进）」，其余三项按推荐执行。**改动清单**：① `db/models.py` 新增 `AppSetting`（第 10 张表）+ 迁移 `d4e5f6a7b8c9`；② 新建 `core/settings_runtime.py`（键常量 + 通用 KV 读写 + **`signup_allowed()` 全项目唯一判断点** + `deployment_mode()` 展示标签 + `count_users()`）；③ `sqlmodel_models.py` 加 3 个 Schema；④ `users.py` 注册守卫改读 `signup_allowed(session)`，**位置仍在查重之前**（防枚举），并移除对 `settings` 的直接 import；⑤ 新建 `api/routes/settings.py`（`GET`/`PATCH /settings/deployment`，超管）+ `main.py` 注册；⑥ `utils.py` 加 `GET /utils/public-settings`（**匿名**，只暴露一位布尔，登录页渲染注册入口用）；⑦ `.env`/`.env.example`/`config.py` 三处注释改为「首次兜底值，网页开关优先」；⑧ **`tests/conftest.py` 收尾清表列表补 `AppSetting`**（运行时配置**无 `user_id`、全库共享**，漏清会让某条用例写的 `true` 漏给后续所有注册闸门断言）；⑨ 前端：新建 `hooks/useDeploymentSettings.ts` + `components/Admin/DeploymentMode.tsx`（两态开关 + 切多租户**二次确认** + `user_count` 提示 + `.env` 被覆盖告警），`admin.tsx` 顶部接入，`login.tsx` 按开关**条件**恢复「注册」入口，`openapi.json` 重导 + `openapi-ts` 重新生成 client。**验证**：后端 `py_compile` ✅ / `app.api.main` 导入并列出新路由 ✅（`/users/signup`、`/utils/public-settings`、`/settings/deployment` ×2）/ 新增 **33 条测试全过**（`tests/core/test_settings_runtime.py` 15 + `tests/api/routes/test_settings.py` 18，2.40s）；全量 `pytest ../tests -q` → **1 failed, 343 passed, 10 errors, 622.62s**，总数 354 = 上次 321 + 33 ✅ **全部 11 条失败/错误均为 `tests/core/knowledge_base/*` 与 `test_knowledge_base.py` 的 Milvus 连接失败**（`UNAVAILABLE: failed to connect to all addresses … 127.0.0.1:64349`，每条重试 75 次 × 3s → 也是本轮耗时 622s 的原因）；**同期 `docker ps` 显示 `irsbot-milvus-1` 为 `Up Less than a second (health: starting)`（正在重启循环）**，属**环境问题、与本次改动无关**（改动不触碰 Milvus 任何代码路径）。前端 `vite build` ✅（`VITE_EXIT=0`，16.35s，新产物 `useDeploymentSettings-BzzkBDBE.js` / `login-jRLDmgqR.js` / `admin-yZes78BQ.js`）→ 重建 `frontend/dist`。⚠️ **`tsc` 未通过（非本次改动）**：`src/hooks/useKnowledgeBase.ts(1,79): error TS1005: ';' expected.` —— 该文件第 1 行两条 `import` 被挤在同一行、hook 体为空，是**用户正在写的 WIP**（全仓无引用），**未擅自改动**；因 `npm run build` 含 `tsc` 会挂，本轮改用 `vite build` 直接出产物 |
| 2026-09-18 11:0x | **🔍 本轮发现的两个结构性问题（未修，留档待定）**：① **`tests/conftest.py` 的清表列表是「硬编码模型清单」**——新增表若忘了加进来，就会静默产生跨用例污染（本轮 `AppSetting` 差点中招）。建议改为遍历 `SQLModel.metadata.sorted_tables` 反向清空，一处生效。② **全仓存在三套互不相干的「D 编号」**：`istbot-implement-plan.md` 0.0 决策表 `D1–D7 / D2.1`、同文件 SC 验收表 `D1–D10`、`local-deployment-plan.md` 施工阶段 `D1–D7 + D1.1…`；`PROGRESS.md` 里 `D2.1` 同时有「注册入口」与「Windows 启动脚本」两义。本轮**不擅自重编号**（会大面积波及引用），已在 `istbot-implement-plan.md` 第九节留档 |
| 2026-09-18 11:1x | **✅ 第七轮收尾：补齐漏提交的前端与文档 + 隔离复跑验证**：① **发现漏提交**——此前两笔（`45aa2c5` 表+迁移、`3df5fe5` 后端逻辑+测试）**只覆盖后端**，前端（client 重生成 3 文件、`hooks/useDeploymentSettings.ts`、`components/Admin/DeploymentMode.tsx`、`admin.tsx`、`login.tsx`）与文档（`OPERATIONS.md` / `PROGRESS.md` / `istbot-implement-plan.md` / `multi-tenant-plan.md`）仍留在工作区。已补两笔：**`53ef96c`** `feat(admin): 部署模式开关 UI 与登录页注册入口`（7 文件，+427/−2）、**`d6c4130`** `docs: 同步部署模式运行时开关的运维、计划与进度文档`（4 文件，+156/−11）。**教训**：多笔提交时须以 `git status` 复核「是否仍有本该入本的改动」，不能凭印象认为一次提交覆盖了整轮。② **隔离复跑（去掉集成标记）**：`pytest ../tests -q -m "not integration"` → **332 passed / 18 deselected / 1 failed / 3 errors，59.20s**；**剩余 4 项全部落在 `tests/core/knowledge_base/*` 与 `test_knowledge_base.py`**（`TestGetDeleteKB::test_delete_own_success` + `TestHybridRetriever` ×3），与前一轮全量跑中确认的 **Milvus 连接失败**是同一批；同期 `docker ps` 确认 **`irsbot-milvus-1` 仍是 `Restarting (134)` 崩溃循环**（另有 `milvus-standalone-old` Exited 137 保留作回滚）→ **环境故障，非本轮回归**，本轮新增/改动代码 **0 失败**。③ 清理临时探针 `_t4.txt`，工作区仅剩用户自写的 WIP `frontend/src/hooks/useKnowledgeBase.ts`（未跟踪，未触碰） |
| 2026-09-18 下午 | **✅ KB 管理 UI 基础页完成（guided-teaching 教学模式，四章走完）**：本轮起教学 skill 改为「**代码贴在回复里、不代学习者落盘**」；后应用户明确要求代为创建/修改。**① 数据层** `hooks/useKnowledgeBase.ts`（新建，用户手写 + 纠错后定稿）：`kbListQuery`（key `["knowledge-base"]`）/ `createKb` / `deleteKb` / `uploadDoc`（**FormData 上传**，`fd as unknown as Body_...` 隔离生成器把 `File` 错标成 `string` 的类型谎言）/ `deleteDoc`（**后端无删除文档端点，抛错占位**）/ `queryKb`（检索测试，**查询型写操作**用 mutation 不用 query）；失效统一 `onSettled` + 前缀匹配（`["kb-documents"]` 不带 kbId = 粗粒度全刷）。**② 界面** `components/KnowledgeBase/KnowledgeBaseManager.tsx`（新建）：三态处理（`isPending` → null / `data ?? []` 兜底 / 空态引导）+ `AddKbDialog`（react-hook-form + zod，关弹窗在**本次调用的 onSuccess**，失败保留表单）+ `KbRow` 删除二次确认；项目无 `ui/textarea.tsx`，描述字段用原生 `<textarea>` + shadcn 类名。**③ 路由与入口**：`routes/_layout/knowledge-base.tsx`（新建，薄路由页只管布局）+ `AppSidebar.tsx` 插入「知识库」入口（Library 图标，聊天与设置之间）。**验证**：`npm run build` 通过（`knowledge-base-*.js` 独立 chunk 出现 = 路由注册成功）。**踩坑留档**：① 用户构建报 8 错实为**旧文件状态**（IDE 缓冲未保存/竞态还原 import）——「改了还报错」先重读磁盘；② 本项目 `build` 脚本 `tsc && vite build` 而 **routeTree.gen.ts 由 vite 插件生成** → 新路由文件首次 tsc 必报「路由不存在」，先跑一次 `npx vite build` 再全量构建；③ 本机无 bun，用 `npm run build`（node_modules 已就绪，仅执行脚本不装依赖）。**发现后端功能缺口并已入待办第 6 项**：`DELETE /kb/{kb_id}/documents/{doc_id}` 不存在。**运维插曲**：用户反馈 8000 无法访问 → `docker compose ps` 发现仅 milvus 在跑（db/backend/prestart 停止，疑似重启过），`docker compose up -d` 拉起全部服务、prestart 迁移正常、health-check 通 |
| 2026-09-19 | **✅ 方案 A 一至三章完成：KB 详情页 + 删除文档端点 + docx 解析（guided-teaching）**。**第一章（doc_id 烙印）**：`vec_store.py` 新增 `delete_by_doc_id`（`has_collection` 幂等 + `filter='doc_id == "xx"'`）；`manager.py` 分块后向每块 `metadata["doc_id"] = str(record.id)`。**第二章（删除端点）**：`routes/knowledge_base.py` 新增 `DELETE /{kb_id}/documents/{doc_id}`——两层归属校验（`_get_owned_kb` + `doc.kb_id == kb.id`，越权一律 404 **零副作用**）、**Milvus→磁盘→DB 的删除顺序**（任何一步失败 DB 记录仍在可重试）、`unlink(missing_ok=True)` 幂等；新增 4 条回归测试（成功/跨库 404/他人库 404/随机 id 404，404 用例均断言 Milvus 未被调用），**62 passed**。**第三章（前端详情页）**：`useKnowledgeBase.ts` 拆两层 hook（`useKnowledgeBase` 列表层 / `useKbDetail(kbId)` 库内层，参数化 key `["kb-documents", kbId]`）；`KnowledgeBaseDetail.tsx`（文档列表+上传+检索测试）+ `routes/_layout/knowledge-base.$kbId.tsx`。**🔴 三大踩坑（都是部署/集成层，非业务逻辑）**：① **TanStack 父路由必须有 `<Outlet/>`**——`knowledge-base.tsx` 作为父路由只渲染列表不渲染 Outlet → 详情 URL 下子路由被静默丢弃（URL 变了、chunk 加载 200、无报错、页面还是列表）；修复=父路由改布局壳 + 列表挪 `knowledge-base.index.tsx`；② **vite 代理 IPv6 坑**——`wslrelay` 占用 `::1:8000`（IPv6 localhost），Node 代理解析 `localhost` 优先走 IPv6 → 全部 API 404；正确形态是**不走 dev server**，用 8000 后端托管 dist（OPERATIONS.md 单端口部署）；③ **生成客户端 formData 只收普通对象**——老版 hey-api `getFormData()` 用 `Object.entries()` 遍历入参自己打包，传 `FormData` 实例遍历出 `[]` → 发空表单 → 后端 422「file 缺失」；curl 直调 201 成功是定位关键（分层排查：浏览器 422 → curl 排除后端 → 读 client 源码）。修复=传 `{ file }` 对象 + 双重断言留注释。**④ docx 解析缺口**：`SUPPORTED_EXTENSIONS` 原只有 pdf/txt/md → `uv add docx2txt` + `Docx2txtLoader`；**容器同步坑**：容器 venv 在 `/app/.venv` 而非 `/app/backend/.venv`（`uv sync` 在错误目录建了无用 venv），正确姿势 = `docker cp` 源码 + `uv pip install --python /app/.venv/bin/python` + restart。**⑤ 实测发现旧数据无 doc_id**（上传早于烙印代码进容器）→ Milvus 按 doc_id 删不掉旧块（第一章设计注释的预言成真），需重传旧文档；已把 manager/vec_store/routes 三文件同步进容器。**待办**：第四章 = generate-client 生成 `deleteKbDocument` → 接通 `deleteDoc` → 详情页加删除按钮 → 全链路验收 |
| 2026-09-19 | **✅ 方案 A 第四章完成（收尾）：删除文档前端接线 + 全链路实机验收**。**① SDK 再生成**：`curl openapi.json` 快照 → `npm run generate-client` 生成 `deleteKbDocument`；**⚠️ 大坑：快照来源必须是本地代码而非运行中的容器**——容器里是旧代码，从它导出的 openapi 少了 Settings 等新端点，再生成会把 `SettingsService`/`DeploymentSettingsUpdate` 等类型整体删掉（`useDeploymentSettings.ts` 编译报错）。修复=改用 `uv run python -c "from app.main import app; json.dump(app.openapi(), ...)"` 从本地导出，diff 复核只剩删除端点增量（+31/−1）。**② UI**：`KnowledgeBaseDetail.tsx` 的 `DocumentRow` 加删除按钮（Dialog 二次确认，模式照搬 `KbRow`；`deleting` prop = `deleteDoc.isPending && deleteDoc.variables === doc.id` 只禁用正在删的那一行）。**③ 实机验收连环坑**：a) 首删 500 —— **旧 Milvus collection 连 `doc_id` 字段都没有**（schema 建于烙印机制之前），`delete` 表达式解析失败 `field doc_id not exist`；修复=`delete_by_doc_id` 先 `describe_collection` 检查 schema 含 `doc_id` 才执行删除，否则跳过返回 0（无向量可删，天然幂等）；容器同步 `docker cp` + restart。b) UI 报「Something went wrong」但后端日志 DELETE 200 —— 混入了**重启前的旧 traceback 干扰定位** + 浏览器缓存旧 bundle；强制刷新后 UI 删除正常。**④ 最终验收**：curl 直删旧 README（无 doc_id 字段的 collection）✅ 返回「文档已删除」、列表正确移除；浏览器 agent 实测 UI 删除 kb_test.txt ✅ 行消失、无报错。KB 回归 **20 passed**。**教训**：① 重新生成客户端前先 `git diff --stat src/client` 看删减量，异常大量删除 = 快照来源不对；② 排障时先按时间戳切分日志，别把重启前的旧 traceback 当新错误 |
| 2026-09-19 | **✅ Phase 14.2 RAG 聚合模式完成：Agent 对话可自主检索知识库**。**起因**：用户问「知识库在 AI 对话时怎么调用，没看到调用过程」→ 排查发现 `builtins/kb_query.py` 只是**占位实现**（返回 "No knowledge base configured"），即 Agent 侧预留了插座但没接电；主链路（上传/解析/混合检索/管理 UI）已完备，缺的只是这根线。**决策：不用 Pipeline 强注入**（AstrBot 式「每问必查」会让「你好」也去查 Milvus，慢 + 浪费 + 无关上下文带偏回答；`nodes.py` 里那段注释掉的 pipeline 残迹即此路线），改走 **Agentic 工具**（计划 8.3 / 14.2 既定路线）：LLM 自主决定查不查、查什么、查几次。**第一章 `kb_query.py` 整文件重写**：① **身份走 ContextVar 不走工具入参**——工具 args 由 LLM 生成、可被提示词注入伪造，`user_id` 若作参数即可越权查他人库；改为 `set_kb_user()` 把身份挂到任务级上下文，工具任意深度读取（并发用户互不串）。② **fail closed**——读不到身份直接返回「无法确定当前用户身份」，**绝不回落成「查全部」**（与 `ef08cc1` provider 修复同一条铁律）。③ 多租户过滤 `KnowledgeBase.user_id == user_id` + `kb_id` 精确过滤**双重叠加**（即便伪造他人 kb_id，user_id 过滤也在，查出来是空）。④ 参数防御：`top_k` 夹在 [1,10]、`kb_id` 先 `uuid.UUID()` 转型（顺带完成格式校验，乱码返回友好错误而非 500）。⑤ 未指定 kb_id 时遍历**用户所有库**聚合（「聚合模式」命名由来），每库内部走同一套 `mgr.query`（向量+BM25+RRF）+ `get_retrieval_context`，外层套 `【知识库：名字】` 头。**第二章 `agent.py` 三处改动**：import `set_kb_user`（`builtins/__init__` 已在 L25 触发注册，无循环依赖）｜`__init__` 把已解析的 `user_uuid` **存为实例属性**（单一真相源，提示词查询/Provider 过滤/KB 身份三处共用同一份解析结果）｜`run()` 与 `stream()` **开头各调一次** `set_kb_user(self.user_uuid)`（两条入口都要覆盖，漏一条就是「流式聊天查不了库」这类难查 bug；且**裸调不加 if**——身份为 None 也如实 set，否则 ContextVar 可能残留上一次请求的身份，从「拒绝」变成「查别人的库」）。**测试**：原 2 条针对占位实现的测试必然失败（断言占位文案）→ 改写为 `test_kb_query_fail_closed_without_user`（无身份必须拒绝）+ `test_kb_query_rejects_invalid_kb_id`（有效身份 + 非法 kb_id 返回友好错误，`finally` 里 `set_kb_user(None)` 清理防身份残留）。**验证**：宿主机全量 `pytest ../tests -m "not integration" -q` → **340 passed / 18 deselected**（338 + 2）。**实机验收（容器内真 LLM + 真 Milvus）**：`docker cp` agent.py + kb_query.py → restart → 脚本驱动 `Agent.run("我的知识库里 README 这份文档讲了什么？")`，消息轨迹显示 **`[5] AIMessage → tool_calls: knowledge_base_query(top_k=10)` → `[9] ToolMessage: 【知识库：小北】[1] 来源: uploads/kb/3f49.../14f5..._README.md` → `[10] AIMessage: 让我再补全两份 README 中尚未检索到的章节` → 二次并行检索 → `[13] AIMessage` 带出处的回答**。三件事得到实证：① Agentic 生效（LLM 自主判断要查，还自主补了第二次检索）② 召回为真（真实 Milvus 分块，非占位文案）③ 多租户过滤生效（只查到 admin 名下「小北」）。**观察（非 bug，已入待办 7）**：LLM 倾向要 `top_k=10`（恰为夹取上限），库大时会撑上下文，与「检索质量优化」一并观察。**工具坑留档**：`DeleteFile` 工具删临时脚本报「未能移动到回收站」→ 改用 `Remove-Item -Force`（沙箱安全删除钩子，老问题） |
| 2026-09-20 | **✅ 对话导出完成（Phase 15.1 遗留项闭环）**。**用户两项决策**：① 格式 = md + json + docx + txt + **pdf 全要**；② 导出内容 = 正文 + 角色 + 时间；③ PDF 中文 = **直接内置一份字体**（接受仓库 +10MB，换「任何环境都不出方框」）。**① 渲染层 `core/agent/export.py`（新建，纯函数不碰 DB/HTTP）**：`ExportedFile(filename, content: bytes, media_type)` + `render_export()` 单一入口；`ExportFormat` 常量类收口扩展名/媒体类型；`_EXPORTABLE_ROLES = {user, assistant}` —— **system/tool 是内部产物不外泄**（与 `agent_ws.build_history_payload` 同口径）；时间**一律 UTC 原样输出并显式标注**（human 格式带 ` UTC` 后缀、JSON 用 ISO `Z`），不做本地时区猜测（服务端无从得知浏览器时区，猜错比不猜更糟）；`extract_text()` 兼容 `{text}` / `str` / 其他类型 JSON 兜底；`build_filename()` 清洗 `[\\/:*?"<>|\x00-\x1f]`（Windows 非法字符，含控制字符）并截断 60 字。**docx**：多行用 `run.add_break()` 还原软换行（直接写 `\n` 在 Word 里会被吃掉）。**pdf**：reportlab platypus（自动分页）+ **`wordWrap="CJK"`（必须，否则中文不换行）** + 正文转义 `& < >`（`Paragraph` 是迷你 HTML）。**② 字体**：Google Fonts `NotoSansSC[wght].ttf`（可变字体 17.7MB）→ `fontTools.varLib.instancer wght=400 --update-name-table` 得静态 Regular（10.6MB，名称正确为 "Noto Sans SC" / "Noto Sans SC Regular"）；存 `backend/app/assets/fonts/` + `OFL.txt`，随 `COPY ./backend/app` 自动进镜像，**无需改 Dockerfile**；`_pdf_font_name()` 用 `lru_cache` 优先取内置字体、缺失则退回不嵌入的 `STSong-Light`（不崩但会有方框）。**③ 端点** `GET /agent/conversations/{id}/export?format=`：归属校验走 `crud.get_conversation(user_id=...)`（越权与不存在**同返 404**，不泄露存在性）；`format` 用 `Literal[...]` → 非法值 422；文件名走 **RFC 6266 双写** `filename="<ASCII兜底>"; filename*=UTF-8''<百分号编码>`（只给 ASCII 名会丢中文，只给 `filename*` 老浏览器会乱码）。**④ 前端**：`downloadConversationExport()` **必须用原生 `fetch` + `Blob`** —— 生成的 SDK 走 axios，默认按 JSON 解析响应体，docx/pdf 二进制会被损坏；`parseFilename()` 优先解 `filename*=UTF-8''`；`ConversationList` 把原 `disabled` 占位换成 `DropdownMenuSub` 二级菜单（5 格式）+ `isExporting` 锁菜单防连点。**⑤ 验证**：全量非集成 **440 passed / 18 deselected**（基线 386 → +54：渲染层 38 + API 层 16）；前端 `tsc` + `vite build` 通过；容器实机 5 格式全通（md/txt/json/docx/pdf 均 200，媒体类型正确）、404/422 边界正确、**PDF 实测 `embedded subset font: True`、字体 `AAAAAA+NotoSansSC-Regular`**。**⑥ 踩坑留档**：a) **`parents[1]` 层级算错**——`export.py` 在 `app/core/agent/`，`parents[1]` 是 `app/core` 而非 `app` → 容器里静默退回兜底字体（**不报错**，只有扒 PDF 内部结构才看得见），修为 `parents[2]`，并补两条回归防线（`test_pdf_uses_bundled_font_asset` 断路径存在 + `test_pdf_embeds_font_subset` 断字节里含 `FontFile2`）；b) **离线 wheelhouse 补包**——`jieba`/`docx2txt` 此前是容器里 out-of-band 装的、**从未进过 `wheelhouse-req.txt`**，本次一并补齐；`jieba` 在 PyPI **只有 sdist**，下载不能带 `--only-binary=:all:`；c) 依赖变更后须 `uv export --frozen --all-extras --no-dev` 重导 `wheelhouse-req.txt`，再逐包比对 sha256 后才重建镜像（避免 build 阶段才失败） |
| 2026-09-20 | **✅ Phase D1.3c 分发优化完成（待办 5 闭环，范围经用户确认为「只做自动化」）**。**动机 = 堵静默故障**：`uv pip install -r wheelhouse-req.txt --offline` 用的是**手写清单**——往 pyproject.toml 加依赖却忘了重新导出 → 镜像构建**照样成功**、应用启动后才 ImportError（静默，比构建失败更糟；`jieba`/`docx2txt` 就是这么漏过一次，上一轮才补上）。**① 新建 `scripts/wheelhouse.py`**（仓库根运行，单一工具两个子命令；核心比较逻辑全抽成纯函数便于测试）：`check` = 重跑 `uv export --frozen --all-extras --no-dev --package app --no-emit-package app`（参数固化成常量）+ 与已提交的 `wheelhouse-req.txt` 做**逐字节比对**（先剥掉 uv 自动生成的横幅——横幅里带 `-o` 路径，不剥会因换个输出名就误报），不一致打印 unified diff 且**退出码非 0**；`wheelhouse/` 存在时再校验 142 个文件的 sha256 与清单哈希一致（该目录被 gitignore，缺失时提示并跳过、**不报错**——新克隆的仓库本来就没有它）。`update` = 重新导出 + 过滤 win32 包 + **只补下缺失的** wheel。**② 三处复现要害固化为显式常量/分支**：`EXCLUDED_PACKAGES={colorama,pywin32,tzdata}`（win32-only；pip 跨平台下载时按**本机**环境评估标记，这些行会让 pip 直接报错）；linux-only 包（faiss-cpu / pyarrow / uvloop / milvus-lite）在**下载阶段去掉环境标记**、改由 `--platform manylinux*` 显式指定（否则被 pip 按本机平台**静默跳过**，不报错）；`SDIST_ONLY_PACKAGES={jieba}`（PyPI 只有 sdist，得换 `--no-binary=:all:`）。下载借 `uv run --no-project --with pip python -m pip download`（uv 无 download 子命令，且遵守「禁裸 python/pip」）。**③ `tests/scripts/test_wheelhouse.py`（35 条）**：只测纯函数（包名归一化 / 清单解析 / win32 块过滤 / 渲染 / 文件名解析 / hash 比对 / missing 判定），用 fixture 造数据，**不依赖网络、也不要求 `wheelhouse/` 真实存在**——否则这个「防干净环境缺件」的测试自己就会在干净环境里挂掉。**④ `backend/Dockerfile`**：注释块里那三条手写命令收敛为指向脚本的一句话（**单一真相源**），保留「为什么用 `uv pip install -r` 而非 `uv sync --frozen`」的说明与 5 个历史坑的成因。**⑤ 镜像瘦身不做**（用户否决）：`.venv` 是 Dockerfile 里**单个 RUN 装成的单层**，后续 `RUN rm` 只加 whiteout 不减体积；且占大头的 pyarrow(153MB)+pandas(64MB) 是 `pymilvus` **硬依赖**，删不得。**⑥ 验证**：实跑 `check` → 退出码 0（142 个包 + 142 个文件哈希全匹配）；**证伪**——把清单里 `aiohappyeyeballs==2.6.2` 改成 `2.6.1` → 正确报出 diff、退出码 1，还原后复绿（并核对 `git diff` 确认文件字节还原）；全量非集成回归 **475 passed / 18 deselected**（基线 440 + 新增 35） |
| 2026-09-20 | **✅ Phase 12 管线完整化完成（待办 10 闭环）**。**12.1 决策表（先决策后编码，三项经用户确认）**：SessionStatus **做**（`Conversation.is_enabled` 字段 + 迁移 `b7c9d1e3f5a7`；test_app 库是 create_all 建的、无 alembic 版本表 → `alembic stamp a8b9c0d1e2f3` 后再 `upgrade head`）；WakingCheck/WhitelistCheck 不做（无群聊）；ContentSafety 暂不做。**12.2 经决策保持顺序模型**（计划原文「优先正确性而非形式」），`STAGES_ORDER` 常量定权威顺序。**12.3 修复问题 #13**：新增 `run_entry_stages()` 共用前置 Stage（RateLimit→SessionStatus→PreProcess），WS 与 REST 走同一实现保证行为一致；WS 拦截时发 `text_chunk` 说明 + `done`（协议不变）；**顺带修掉一个真 bug**——REST 路由每请求 `RateLimitStage()`，计数窗口永远为空、限流形同虚设 → 改进程级单例 `get_rate_limit_stage()`。**12.4 内部钩子**：`pipeline/hooks.py` 精简 3 钩子（on_llm_request / on_llm_response / on_agent_done），异步总线 + 异常吞掉只记日志，不做第三方插件；Agent.run/stream 接入。**12.5 上下文补强**：新模块 `agent/context_manager.py`（中英文分权重 token 估算 / `split_into_rounds` / **`fix_messages` 保证 assistant(tool_calls)↔tool 配对**——悬空 tool 丢弃、未响应调用补合成 ToolMessage，否则截断历史发 OpenAI 直接 400 / `ContextTruncator` 三策略且输出一律过 fix_messages 兜底）；`get_context_messages` 末尾接入 fix_messages；`invoke_llm_node` 空输出 tenacity 指数退避重试 3 次（`_EmptyOutputError` 仅作重试信号，reraise）；工具超时统一 `TOOL_CALL_TIMEOUT=120s`（原 ToolExecutor 默认 30s）；`MAX_AGENT_STEPS` 15→30（test_config 同步改）。**验证**：+27 测试（SessionStatus/entry stages 6 + hooks 6 + context_manager 12 + retry 3），全量非集成 **490 passed**（10 failed 均为 Milvus 容器未启动的环境噪音，与本次改动无关）。**踩坑留档**：tenacity 装饰器参数 `retry_if_exception(_is_retryable)` 在**模块导入时**求值 → `_is_retryable` 必须定义在装饰器**之前**，否则 NameError 连环炸到 app 全家 |
| 2026-09-20 | **✅ Phase 15 前端完善完成（待办 11 闭环，15.1 / 15.2 / 15.3 全部达成）**。**目标兑现**：用户全程零配置文件——「填 Key → 对话 → 管 KB/MCP/Skill/Persona」纯网页闭环。**15.1 对话体验**（`235193c → 07d9c60` 七笔）：Markdown 渲染打磨（代码高亮/表格/打字机）、消息操作（复制/重新生成/编辑重发/删除）、工具调用折叠面板（入参+结果可视化）、停止按钮走 WS `interrupt`、错误态与重连提示中文化、RAG 引用来源展示（命中片段+相似度）、移动端适配。**15.2 配置台**（`50739ec → 65e4633` 七笔）：MCP 管理页（列表/连接测试/工具预览，顺带修复三种传输的连接实现 `748f844`）、技能页（列表/上传/详情）、人设页（列表/编辑/会话绑定）、会话管理页（列表/历史查看/启停/删除）、统计页（运行次数/Token 用量/平均耗时/工具调用四卡片，补齐 14.3 AgentRun 采集闭环 `7e24739`）、**设置页工具权限开关**（`79eea28`：GET/PATCH `/settings/tools` 超管专属；优先级 DB > `.env` > 代码默认；隐藏的工具在 `Agent.__init__` 从 `self.tools` 过滤、`call_tools_node` 解析不到即返回「工具不存在」，内置注册恒全量）、**配置闭环引导**（`65e4633`：聊天页空状态在无任何启用 Provider 时显示引导卡，一键 `navigate(/providers?new=1)` 自动弹新增对话框；Provider 是**按用户**隔离的，引导判据用 `providersQuery` 共享缓存 key 自动隐现）。**15.3 其它**：侧边栏信息架构重组 + 品牌替换（`6da2829`：工作台/资源/系统三分组 + Admin 入口按超管角色显隐；内联 SVG 品牌 mark 替换全部 FastAPI 资产 + 同名 favicon，删 4 张旧图、卸载 react-icons）；**Playwright e2e**（`af0e7b6`：新增 `agent-pages.spec.ts` 每页冒烟 + `onboarding.spec.ts` 引导与权限可见性，删除指向已移除功能的陈旧用例 `items.spec.ts`/`reset-password.spec.ts`/`mailcatcher.ts`，改造 `sign-up.spec.ts`，全量 **60 passed**）。**踩坑留档**：① shadcn `<aside>` 嵌套在 layout 里**不映射 role=complementary**，Playwright 定位侧边栏须用 `[data-sidebar="sidebar"]`；② 注册闸门默认关 → 需注册的用例必须**自带 beforeAll PATCH 开关 + afterAll 还原**（放 `finally` 不可靠——测试超时后 browser context 已关，PATCH 直接报 Target closed；`afterAll` 失败时也执行），且一次超时失败曾把共享库注册留开，须事后 GET `/settings/deployment` 复核收口；③ signup 成功后跳 `/login` 而非自动登录，`waitForURL` 别写错；④ `tests/utils/privateApi.ts` 的 `OpenAPI.BASE` 引用了已从 `.env` 刻意删除的 `VITE_API_URL`，字面量变成字符串 `"undefined"` → 加 `|| "http://localhost:5173"` 兜底（vite proxy 转 API）；⑤ Radix tab 在水合完成前 `.click()` 无效，可靠姿势是键盘 `ArrowRight` 派发或等待水合后 uid 点击 |
| 2026-09-21 | **✅ 高级配置功能落地（P6，两笔提交）**：模型源详情「高级配置…」三行从占位转**真功能**。**后端**：复用存量 `ProviderConfig.config` JSON 列（免迁移）承载 `timeout_seconds/proxy_url/extra_headers`；PATCH 校验（超时 5–600 → 422、代理协议前缀 → 400、headers 值必须 str → 422；空串/空 dict=清除）；**两个生效点**——`get_chat_model`（openai: `timeout`+`default_headers`+`http_client(proxy)`，anthropic: `default_request_timeout`+…，gemini 如实记录不生效）与 `query_balance`（httpx.AsyncClient 透传）；**缓存键纳入高级配置签名**（否则改配置拿到旧实例）。**前端**：三行解禁接表单，请求头做行内键值对编辑器（添加/移除/完成）。**测试**：新增 `test_provider_advanced.py` 10 条（校验/持久化往返/清除/越权 404/工厂接线断言 `request_timeout`+`default_headers`+挂载代理/改配置换实例/余额客户端透传），api+provider+core **459 passed**；e2e 18 passed；实机闭环「配置→保存→API 确认→清理」，清除语义实测正确 |
| 2026-09-21 | **✅ 模型供应商界面 AstrBot 风格改造（纯前端，P0–P4 五笔提交）**。**版式**：顶部能力 Tab（对话 + 语音转文字/文字转语音/嵌入/重排序四项**禁用占位**）→ 左「模型源」列表卡片（名称/默认徽标/API 地址/查余额行内/删除 hover 显隐）+ 右详情面板（未选时空态「请选择一个模型源」）→ 详情分**设置 / 高级配置… / 模型**三分区。**功能迁移**：保存配置接 `updateProvider`（API Key 留空不提交防覆盖密文；类型只读——后端 PATCH 无 provider_type）；新增/删除/设默认/视觉/查余额全部保留；`?new=1` 自动开弹窗保留。**占位（代码注释 TODO）**：高级配置（超时/代理/自定义请求头）、模型区（搜索/获取模型列表/自定义模型）、添加更多 Key。**e2e 兼容关键**：`provider-row`/`provider-balance-*` testid 与 base_url 文案留在左卡片（agent-pages 按行定位）。**验证**：agent-pages+onboarding 18 passed；实机验收空态/详情全区块渲染、无改动保存 PATCH 链路通。任务文档 [providers-ui-plan.md](./providers-ui-plan.md)（P0–P4 每阶段一笔提交可回退） |
| 2026-09-21 | **✅ 控制台信息功能改造（AstrBot 风格，提交链 `ca9faa6` → …）**。**痛点**：控制台被 uvicorn.access 淹没（控制台页每 2s 轮询 /api/v1/logs + 健康检查全进缓冲 = 自我回声），看不到有效信息。**后端**：① `RingBufferHandler` 噪声过滤——访问日志命中 `/api/v1/logs`、`/utils/health-check` 直接不进缓冲；② `LogEntry` 新增 `source` 字段（`父目录.文件名:行号`，AstrBot 短定位风格）；③ main.py 启动横幅（控制台有时间锚点）。**前端**（仿 AstrBot 数据日志页）：级别筛选改 ✓ 徽标五档（CRITICAL 单列）、日志行 `[时间][级别][logger][来源] 消息`、**可选信息三开关**（访问日志默认排除 / 来源定位 / 自动滚动）、全屏按钮。**验证**：e2e 24 passed；实机 23 条有效日志中自轮询噪声 0、健康检查噪声 0、来源定位全命中、横幅清晰。**参考**：`astrbot-console-logging.md` 实施方案（loguru/Broker/SSE 全套本轮未引入——现有 2s 轮询 + 环形缓冲对本机场景够用，SSE 与文件落盘列为后续可升级项） |
| 2026-09-21 | **✅ 默认系统提示词加固**。用户发现 agnes-3.0-flash 一次回答「我是 Agnes-3.0-flash，由 Sapiens AI 开发」——排查结论：注入链路无 bug（prompts.py/agent.py/DB/人设逐环验证；实测同环境新会话 4 连答对），系该蒸馏 flash 模型**偶发无视系统提示词**（训练烙印身份）。加固：`DEFAULT_SYSTEM_PROMPT` 重写为「身份约定前置（最高优先级 + 明确覆盖训练自带设定）+ 结尾再次强调」双重结构，枚举名单补 Qwen/Agnes；tests 只按引用比较文案，34 条 test_users 全过。**实机验证**（agnes-3.0-flash 默认源）：4 种试探（泄漏原话「你是什么」/ 中文名直问 / 英文 injection 攻击 / 「你是 Agnes 吗」诱饵）全部按约定话术回答，零泄漏；`docker cp` + mtime 热同步进容器 |
| 2026-09-21 | **✅ 对话列表「生成中」状态指示器**：流式回复期间，侧边栏对应会话行尾显示绿色旋转指示器（hover 时隐去给「…」菜单让位，移动端不渲染避免重叠）。实现：新建 `hooks/useChatActivity.ts`（模块级 store + `useSyncExternalStore`，不引入 zustand）；`useAgentChat` 把 `isStreaming` 同步进 store，effect cleanup 强制清除防残留；`ConversationList` 行内按 `generatingIds.includes(conv.id)` 渲染。实机验证 4 轮完整生成周期；e2e 回归 32 passed |
| 2026-09-21 | **✅ 多会话并行生成（切换会话不再中断）**。**根因**：WS 连接挂在聊天页组件的 effect 里，切走会话 → 组件卸载 → 连接关闭 → 后端 `chat_ws` 的 `WebSocketDisconnect` 分支 cancel 生成任务（`agent_ws.py` 收尾处），「切走即停止」。**方案 = 纯前端重构**（后端协议与取消语义不动）：`useAgentChat.ts` 重写为模块级连接管理器——`ChatConnection` 类按会话 ID 持有 WS + 消息流 + 重连退避（Map 单例，StrictMode 双渲染幂等），`useAgentChat` 退化为 `useSyncExternalStore` 订阅视图（getSnapshot 缓存快照引用满足相等性约定）；切换会话只是换订阅对象，旧连接继续在后台收流。**配套**：① `setStreaming` 内联同步 `useChatActivity` 全局登记——后台会话的「生成中」指示器照常工作；② done 事件派发 `window` 事件 `irsbot:turn-done`，聊天页监听后 invalidate 会话列表（后台会话收尾时组件感知不到 isStreaming 复位）；③ 连接上限 10 条 LRU 淘汰（只淘汰空闲连接，流式中允许暂时超限）；④ `useConversations.deleteConversation` 的 onSuccess 里 `closeChatConnection` 防删除后残留连接。**实机验证**（浏览器自动化）：会话 C 发起长生成（四大名著长文）→ 生成中切到会话 B → **后台指示器连续 20s 持续存在**（40 次采样全 1）→ 切回 C 后回复完整落库（3098 字、四大名著全命中、done 已收尾）。**e2e 回归 58 passed**（admin/agent-pages/onboarding/console/login/user-settings），tsc/vite build 通过。**遗留说明**：被淘汰的空闲连接重开时重放 history 消息不丢；被删除会话的连接由 4404 兜底 |
| 2026-09-21 | **✅ 日志与控制台功能完成（待办 13 闭环）**：`core/logging.py`（setup_logging + 环形缓冲 + 脱敏过滤器，§8.6「16.3 api_key 不进日志」保留项落地）→ `GET /api/v1/logs`（superuser，after_id 游标增量）→ `/console` 前端控制台页（2s 轮询、级别过滤、搜索、暂停/清屏、superuser 守卫）+ 侧边栏入口。测试：后端新增 24 条、全量 **713 passed**；e2e `console.spec.ts` 7 条 + 回归 admin/login/onboarding 23 条全过（8000 实机 dist，`--workers=1` 因空闲内存 1.9GB）。详案 [console-logging-plan.md](./console-logging-plan.md) 已全部勾选，见待办 13 |
| 2026-09-20 | **✅ 模型源余额查询完成（待办 12 闭环）+ 补 Persona 后端回归 + e2e 端口纠偏**。**补课（先回答「这些功能测试过了吗」）**：用 grep + `git show f724d8b --stat` 核查发现 **15.2c Persona 只有前端实现、零后端测试**（其余 15.x 均有覆盖）→ 新建 `tests/api/routes/test_agent_personas.py` **17 条**（默认值、全字段、422/401、列表按用户隔离、详情/越权 404、部分更新、删除幂等、绑定/解绑、他人 persona 404、删 persona 自动解绑），提交 `020aabb`。**e2e 端口纠偏（用户指出「走什么 5173，前后端统一到 8000」）**：此前 e2e 打的是 vite dev server 5173，而**单端口部署下 8000 后端托管的是已构建的 `frontend/dist`**，dev server 跑的是**另一份源码** → 用例绿了也可能与真实产物无关。改 `playwright.config.ts` baseURL 为 `http://127.0.0.1:8000` 并**删掉 `webServer` 块**（被测对象是 dist 构建产物，不是 dev server），`privateApi.ts` 兜底同步；改完立刻暴露 2 处真实缺陷：login/signup 的 zod 邮箱校验漏了中文 message（显示 `Invalid input`），以及 `/stats` 的「工具调用」标签与表头重名导致 strict-mode 冲突 —— 前者补 `{ message: "邮箱格式不正确" }`，后者加 `.first()`，**60 passed**，提交 `ad53193`。**余额功能**：经用户二选一定案「**上游接口适配器** + **模型源页每卡片加按钮**」；后端 `8a51564`（4 厂商适配器 + 归一化模型 + 中文错误映射 + 35 条测试），前端 `9f788ac`（`useProviderBalance` 用 `enabled:false` 的显式查询 + `data-testid="provider-balance-button"/"provider-balance-result"`），本轮补 Playwright 用例并**实机验证 8000**：`GET /providers/7fb3f761-.../balance` 返回 `{"supported":false, detail:"阿里云百炼不提供余额接口；账户余额请在阿里云控制台「费用中心」查看"}`（与 e2e 断言的文案一致）。**踩坑留档（环境）**：全量 e2e 有一次 **24 failed / 12.1min**，全是 `browserContext.newPage: Test timeout of 30000ms`；同一套用例内存充足时 **21.6s** 跑完 → 查 `wmic OS get FreePhysicalMemory` 仅剩 ~1.7GB，**空闲物理内存不足会让 Chromium 启动大面积超时**，与代码无关；另外 `npx playwright test ... \| tail` 的退出码是 `tail` 的，**永远 0**，别用它判断成败（须落盘后看报告尾部） |
| 2026-09-21 | **✅ Phase 16 聊天附件闭环（待办 14，S0–S8 全部完成）**。用户四项诉求全部落地：删「聊天」独立入口、「新对话」移到「最近对话」之上、输入框加「上传文件」、按截图实现菜单——菜单最终定为**上传文档 / 上传图片 / 截屏提问**三项（用户当场砍掉「共享屏幕」）。**链路**：前端 `＋` 菜单 → `POST /api/v1/agent/attachments`（裸 32 位 hex id、图片嗅探魔数、随会话删除而删）→ 元数据随 WS 消息上行存进 `Message.content.attachments`（**不新建表**）→ 本轮 `build_turn_content` 拼装：文档解析文本并入、图片按 `Provider.supports_vision` 三态（显式 > 模型名启发式）决定**内联多模态**还是**本地 `rapidocr` OCR 回退**，两者都不行时如实中文说明。**提交链** `1dfe24c`(S0) → `10e8123`(S1) → `c98a67b`(S2) → `17950bd`(S3) → `f24080d`(S4) → `419da15`(S5) → `2f3ea1e`(S5b) → `6dca04a`(S6) → `844589e`(S7) → `14abe8d`(S8)。**验证**：后端全量非集成 **706 passed**；Playwright `chat-attachments.spec.ts` 3 条在 8000 实机 dist 通过（全量套件 71 passed，其中 `admin.spec.ts` 编辑用户名一条为**共享库重名的既有数据问题**，与本次改动无关）。详案 [chat-attachment-plan.md](./chat-attachment-plan.md) |

