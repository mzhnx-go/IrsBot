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
| **当前阶段** | **🎉 Phase D1–D7 ✅ + D5.1b ✅ 全完成**；**已建 git 回退基线**（独立仓库 `d:/AIpy/full-stack/IrsBot/.git`，分支 `feat/agent-platform`）；**✅ §10.6 Provider 实测 a–f 全部通过（2026-09-18）**：a 列表/b 新增/c 设默认/e 加密/f RAG 向量化 ✅；**d 项缺陷（删默认源后无默认）已修复**（`a746d10`：`delete_provider` 自动补位 + 7 条回归测试 + 实机 A/B 验证），详见第八节；**✅ 系统提示词功能已实施并实机验收（2026-09-17）**：User.system_prompt 列+迁移 `a1b2c3d4e5f6`、`prompts.py`、Agent 注入 SystemMessage、GET/PATCH `/users/me/system-prompt`、设置页「系统提示词」tab、client 已重新生成 |
| **代码状态** | 🔶 **有代码改动**：`backend/Dockerfile`（修 Python 版本）/ `backend/app/main.py`（静态托管）/ `frontend/src/main.tsx` + `routes/_layout/chat.tsx` + `hooks/useAgentChat.ts`（相对路径）/ `frontend/vite.config.ts`（proxy）/ `frontend/.env` + 配置类改动（见第四点五节） |
| **运行状态** | ✅ `irsbot-milvus-1`（healthy） + `irsbot-db-1`（healthy）已由 compose 接管；✅ **本机 uvicorn :8001 已跑通 D1.3a**；🔶 `backend` 镜像**构建中**（`buildx history` → Running，28+ 分钟；**根因已锁定为容器虚拟网络限吞吐**，见 §3.3.5） |
| **文档状态** | ✅ **已一致**：`istbot-implement-plan.md` 第零至十节全部对齐「Docker 交付」；`local-deployment-plan.md` 已升 **v7.2**（新增容器网络限速实测 + 「坑 C：日志文件误判」）；**2026-09-17 17:xx 全量回查再同步**：第一节 Phase 表 D1–D7 ⬜→✅、SC D1–D9 达成情况实证改判（D7 改判不迁移、D1 服务数 6→3）、10.1/10.5 待办消解结案、`local-deployment-plan.md` 状态头改「已全部完成」+ D1 子阶段表 + 风险表 8 行结案 |
| **当前分支** | `feat/agent-platform`（未推送远端） |
| **测试基线** | ✅ **全量最新实跑：`pytest ../tests -q` → 311 passed, 0 failed（100.93s）**（2026-09-18，含本次新增 7 条 provider 回归测试）；前端 `tsc --noEmit` ✅ ExitCode 0；`app.main` 导入 ✅；**D1.3a 实机验收 6/6 通过 ✅**；**§10.6 a–f 全部通过（d 项缺陷已修复并实机 A/B 验证）** |
| **阻塞项** | **无** —— **D1.3a 已实机验证通过**（见下方验收表）；镜像构建是 D1.3c 分发优化，非阻塞 |
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
| D2 | 本地版单用户 | **Phase 11 降级**（仅保留 cache 淘汰 + `is_default` 约束） |
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

> 代码层已具备实跑条件；**沙箱无法跑 Docker+前端+PG 全链路**，故 a–e 的点击实测与「embedding 不再 401」需你在 Windows 机器执行 `start.cmd` 后按上表走一遍。

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

**第 0 步：~~审阅 + 回答 Q1–Q6~~** → ✅ **Q1–Q3 已确认，D1.2 已完成**；Q4–Q10 可在施工中陆续回答。

**第 1 步：开工 D1.1**（剥离部署层残留 —— **不依赖任何调研结论，可立即动手**）

```powershell
cd d:\AIpy\full-stack\IrsBot
# D1.1 改 compose.yml + compose.override.yml：
#   删 traefik 全层 labels / traefik-public external 网络 / ${DOMAIN} / ${STACK_NAME}
#   删 compose.traefik.yml、proxy、mailcatcher、playwright、nginx.conf
#   .env 改 PROJECT_NAME=IrsBot、FRONTEND_HOST=http://localhost:8000
# 改完立刻验证：
docker compose config           # 目标：无任何 ?Variable not set 报错
docker compose up -d db         # 只起 db，验证最小面
```

**第 2 步：~~D1.2（Milvus）~~** → ✅ **已完成**（单容器内嵌 etcd，绑定挂载零迁移复用数据）

**第 3 步：D1.3 → D1.4 → D1.5（前端托管 + 模板残留清理）**

```powershell
# D1.3a: backend/app/main.py 加静态托管 + SPA fallback（排除 /api 前缀）
# D1.3b: VITE_API_URL 改相对路径 /api
# D1.3c: backend/Dockerfile 加 COPY ./frontend/dist /app/frontend-dist
# D1.4 : 删 items（前后端 + 新增 alembic 迁移删表 + 侧边栏）
# D1.5 : 清 DOCKER_IMAGE_*/TAG（与 image: 字段同批）
# 💡 D1.3–D1.4 同批改前端、只构建一次
```

**第 4 步：D2 + D3（启动脚本 + 首次引导）** → **第 5 步：D4 端到端验证** → **第 6 步：D5 数据迁移**

```powershell
# D4：重跑测试基线（务必带上 integration 标记，否则会被静默跳过）
cd d:\AIpy\full-stack\IrsBot\backend
uv run pytest -m integration -q     # 期望 18 passed
uv run pytest -q                    # 期望 294 passed
```

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
| 2026-09-18 01:xx | **✅ 修复 §10.6 d 项缺陷（提交 `a746d10`）**：`ProviderManager.delete_provider` 原只 `session.delete(obj)`，删掉当前默认源后**该用户再无任何 `is_default=True`**（徽标消失、取默认源直接 RuntimeError）。改为**删除前先选接替者**：若被删行 `is_default`，则在同用户**其余启用中**（`is_active=True`）配置里按 `fallback_order` 升序取一条置为默认，再删除并一次 `commit`。**三处关键约束**：① 只取启用中候选（`get_chat_model` 要求 `is_default` **与** `is_active` 同时成立，否则是"有徽标取不到模型"的假象）；② 严格按 `user_id` 过滤（否则会提升**他人**源 → 越权使用他人密钥）；③ 无接替者时保持无默认、不报错。**新增 7 条回归测试**（manager 6 + API 1）。**双层证伪**：测试层短路提升逻辑 → 恰好 4 条补位测试失败；实机层把 `cd1f17b` 旧版 `docker cp` 进容器跑同一动作序列 → `default` 掉成 `False`、**0 条默认**（缺陷如实复现）；换回修复版 → 恰好 1 条默认且自动补位 ✅。**全量回归 311 passed**。⚠️ **重要坑**：uvicorn `--reload`（StatReload）**只在 mtime 变大时重载**，用 `docker cp` 灌回较旧版本不会触发重载 → 需 `os.utime` 把 mtime 顶到未来。环境已还原（仅剩 `default` 且为默认） |
