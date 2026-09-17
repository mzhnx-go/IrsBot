# IrsBot Docker 本地部署实施计划

> 版本：v7.2 ｜ 日期：2026-09-17
> 上游文档：[istbot-implement-plan.md](./istbot-implement-plan.md)（全局规划）｜ [PROGRESS.md](./PROGRESS.md)（运行态）
> **本文档只覆盖一件事：让 IrsBot 能被「一条命令启动、并且分发给别人」。**
>
> ✅ **状态：施工中。D1.2 已完成并实机验证；D1.3a（后端静态托管）+ D1.3b（前端相对路径 + Vite proxy）已完成编码，待实机验证。**
> 下一步：验证 8000 端口出界面 → D1.1 剥离 Traefik 依赖 → D1.4 清理 items。
>
> 📌 **v6 补充定位**：本项目基于 **full-stack-fastapi-template** 修改而来。
> **除 IrsBot 自身功能（Agent / RAG / 对话 / Provider / 知识库）外，模板残留均可清理。**
> 前端 webui（登录、shadcn/ui 组件库、apiClient 生成机制）按用户决定**直接复用**。
>
> 📌 **v7 新增**：① 修复 `backend/Dockerfile` 既有 bug（`FROM python:3.10` → `3.13-slim`，与 `requires-python` 冲突）；
> ② §3.3.4 补全「前端 API 地址三处陷阱 + Vite proxy 必需性」；③ D1.3 拆为 a/b/c 并标注完成度。
>
> 📌 **v7.2 新增**：① §3.3.5 补**容器网络限吞吐**的完整实测（小请求 150 KB/s vs 大文件 2–11 KB/s，宿主 1370 KB/s）→ **根因锁定，换源不解决**；
> ② §3.3.5 补「`--no-cache` 断层缓存但不断 cache mount」的关键区分；③ §3.3.6 新增**坑 C（日志文件当判据，骗了三次）**；
> ④ 明确 **D1.3 验证不依赖镜像构建**（本机 `.venv` + `dist` 即可）。

---

## 零、方向变更记录（v4 根本性转向）

### 0.1 本文档的历史与推翻

本文档 v1–v3 的主题是「**消灭外部依赖**」——把 PostgreSQL 换成 SQLite、把 Milvus 换成 FAISS，目标是「不装任何东西就能跑」。

**该方向已于 2026-09-16 被用户推翻。** 原因：

| 假设 | 现实 |
|---|---|
| 「本地部署 = 必须零外部依赖」 | ❌ 这是**未经论证的假设**，不是唯一答案 |
| 「PostgreSQL + Milvus 是负担」 | ❌ 它们是**已验证可用**的成熟方案 |
| 「必须做数据库方言改造」 | ❌ 改造成本高（约 70% 工作量），收益不明 |
| 「AstrBot 用 SQLite 所以我们也该用」 | ❌ AstrBot 的选择是它的场景（桌面分发），不适用于本项目 |

**用户决策**：**保持 PostgreSQL + Milvus，走 Docker 一键启动路线。**

### 0.2 新决策记录（2026-09-16，v4）

| # | 决策 | 影响 |
|---|---|---|
| **D4** | **保持 PostgreSQL + Milvus**（不换 SQLite/FAISS） | **L1/L2 阶段作废**；`local-deployment-plan.md` 整份重写 |
| **D5** | **部署形态 = Docker 一键启动** | 用户需装 Docker（唯一前置）；交付 `compose.local.yml` + 启动脚本 |
| **D6** | **默认容器内 PG，留环境变量后门** | `POSTGRES_SERVER` 默认 `db`（容器）；可覆盖为 `host.docker.internal` 连宿主机 |
| **D7** | **全量迁移现有开发数据** | 新增数据迁移阶段（§5），迁移前强制备份 |

### 0.3 为何 Docker 是正确选择（论证）

| 维度 | Docker 方案 | 桌面 exe 方案（AstrBot 路线） |
|---|---|---|
| 用户要做 | 装一次 Docker → 跑脚本 | 双击安装包 |
| **本项目工作量** | **小**（改造 compose + 脚本） | **大**（SQLite/FAISS 改造 + Tauri 打包 + 内置 CPython） |
| **技术栈** | **保持不变** ✅ | 必须换成 SQLite + FAISS ❌ |
| **功能验证状态** | **已实机验证通过**（18 项集成测试）✅ | 需重新验证 ❌ |

**结论**：Docker 路线用最小代价达成「一条命令启动」，同时保住已验证的技术栈。

### 0.4 唯一的已知代价

**用户必须安装 Docker Desktop。** 这是本方案唯一的门槛。

- 对技术用户：无障碍
- 对非技术用户：有门槛 → **未来若需进一步降低门槛，再走 AstrBot Desktop 路线（届时才需要 SQLite/FAISS 改造）**

> **不要为"未来可能的桌面版"提前做改造** —— 那是 YAGNI。等技术栈真的需要换时再换。

---

## 一、现状盘点（已实机确认，2026-09-16）

### 1.1 功能层面：✅ 已验证可用

**18 项集成测试全部通过**（真实调用 API，非 mock）：

```
18 passed, 294 deselected, 9 warnings in 90.93s
```

| 验证域 | 项数 | 结果 |
|---|---|---|
| RAG 向量检索（Milvus + Embedding API） | 9 | ✅ 全过 |
| Agent 真实 LLM 循环（LangGraph ReAct） | 2 | ✅ 全过 |
| WS 流式对话（端到端） | 6 | ✅ 全过 |
| 工具执行 / Skill 注入 / 长对话 | 1 | ✅ 全过 |

**关键含义**：Docker 化不是「包装一个坏功能」，而是「让一个已验证能跑的应用更容易启动」。

### 1.2 部署层面：❌ 无可交付的启动方式

**当前 `compose.yml` 是「线上 SaaS 版」**，依赖：

| 依赖 | 位置 | 本地跑会怎样 |
|---|---|---|
| `${DOMAIN}`（域名） | `compose.yml:36` 等多处 | ❌ 未设置则启动失败 |
| `${STACK_NAME}` | 多处 | ❌ 未设置则启动失败 |
| Traefik（外部网络 `traefik-public`） | `compose.yml:174` `external: true` | ❌ 网络不存在则报错 |
| Let's Encrypt 证书 | 多处 `certresolver=le` | ❌ 需要公网域名 |
| adminer | `compose.yml:22` | 非必需 |

**这就是本地部署的真实工作量所在：拆解线上依赖**，而非写新功能。

### 1.3 环境层面：⚠️ 有两套 PostgreSQL 并存

| 实例 | 状态 | 用途 |
|---|---|---|
| **本机安装版**（PID 9196，监听 5432） | ✅ 在跑 | **当前实际使用**，含开发数据 |
| **Docker 容器** `full-stack-fastapi-template-db-1` | ❌ Exited (255)，7 天前 | 模板残留，未使用 |

> **处置**：Docker 化前需清理残留容器，并明确新旧 PG 的关系（见 §5 数据迁移）。

### 1.4 开发数据实况（本机 PG）

| 表 | 行数 | 价值判断 |
|---|---|---|
| `conversations` | **126** | ★★★ 核心数据 |
| `messages` | **108** | ★★★ 核心数据 |
| `knowledge_bases` | 22 | ★★ 多数为测试空壳（仅 2 个 document） |
| `personas` | 21 | ★★ 多数为测试残留 |
| `mcp_servers` | 17 | ★★ 多数为测试残留 |
| `agent_runs` | 20 | ★ 统计记录 |
| `documents` | 2 | ★★ |
| `provider_configs` | 1 | ★★★ 含你的 API Key 配置 |
| `user` | 1 | ★★★ 账号 |
| `item` / `skills` | 0 | 空 |

**决策：全量迁移**（D7）。理由：筛选易漏、迁移成本相同、搬过去后可自行清理。

### 1.5 已发现的既有隐患（与部署无关，但需修）

| # | 问题 | 位置 | 严重度 |
|---|---|---|---|
| 1 | **`SECRET_KEY` 每次重启变化** → JWT 全部失效、登录态丢失 | `config.py:34` | **P0** |
| 2 | `FIRST_SUPERUSER_PASSWORD` 仍是 `changethis` | `.env` / `config.py:160` | **P0** |
| 3 | psycopg 连接泄漏（`ResourceWarning`） | 测试/运行期 | P1 |
| 4 | `auto_id` 配置与实际行为不一致 | `vec_store.py:49-53` 传入参数 | P2 |

---

## 二、阶段总览

```
D1 (compose 本地化)  ──► D2 (一键启动脚本) ──► D3 (首次引导)
                                                    │
                                                    ▼
                                          D4 (验证) ──► D5 (数据迁移)
                                                          │
                                                          ▼
                                                    D6 (工具权限) ──► D7 (交付)
```

| 阶段 | 主题 | 优先级 | 依赖 | 关键产出 |
|---|---|---|---|---|
| **D1** | Compose 本地化改造 | **P0** | 无 | `compose.local.yml`（剥离 traefik/域名） |
| **D2** | 一键启动脚本 | **P0** | D1 | `scripts/start-local.ps1` / `.sh` |
| **D3** | 首次启动引导 | **P0** | D1 | `SECRET_KEY` 落盘 + 随机管理员密码 |
| **D4** | 端到端验证 | **P0** | D1–D3 | 干净环境启动成功证据 |
| **D5** | 数据迁移 | **P0** | D4 | 本机 PG → 容器 PG，**迁移前强制备份** |
| **D6** | 工具权限开关 | **P1** | D1 | `shell` / `file_write` 默认关 |
| **D7** | 交付与文档 | **P1** | D4 | README（启动/备份/卸载） |

**关键路径**：`D1 → D2/D3 → D4 → D5`

> ⚠️ **D5 必须在 D4 之后**。理由：迁移是「从旧环境切到新环境」，必须先确认新环境可用。**搬到还没盖好的房子里是危险的。**

---

## 三、D1 Compose 本地化改造（核心工作量）

### 3.1 目标

**新建 `compose.local.yml`**，保留原 `compose.yml` 不动（线上版可能仍被另一个项目复用）。

### 3.2 需要剥离的内容

> **背景（2026-09-16 用户确认）**：本项目基于 **full-stack-fastapi-template** 修改而来，因而保留了大量模板残留。
> 用户明确：「**无关 IrsBot 的都可以放心修改**，只是觉得 full-stack 的 webui 可以直接拿来用」。
> 故 D1 的目标不仅是"让 compose 能在本地跑"，还要**顺手清掉模板痕迹**，让仓库自解释。

#### 3.2.1 部署层残留（确定删除）

| 剥离项 | 原位置 | 处置 |
|---|---|---|
| Traefik 全部 labels | 各 service | **删除** |
| `traefik-public` 外部网络 | `compose.yml:171-174` | **删除**，改用默认 bridge |
| `${DOMAIN}` / `${STACK_NAME}` / `${FRONTEND_HOST?}` 依赖 | 多处（约 30 处） | **删除** |
| Let's Encrypt 证书配置（`tls.certresolver=le`） | 多处 | **删除** |
| HTTPS 重定向中间件（`https-redirect`） | 多处 | **删除** |
| `proxy` 服务（traefik:3.6） | `compose.override.yml:59-97` | **删除** |
| `compose.traefik.yml` | 根目录 | **删除整个文件**（纯 traefik 生产部署用） |
| `mailcatcher` 服务 | `compose.override.yml:167-171` | **删除**（SMTP 测试工具） |
| `playwright` 服务 + `Dockerfile.playwright` | `compose.override.yml:184-207` | **删除**（模板自带 e2e 测试，与 IrsBot 无关） |
| `adminer` 服务 | `compose.yml:22-43` | **移入"仅开发"**（用户已定：不删，但只在开发时启用） |
| `nginx.conf` / `nginx-backend-not-found.conf` | `frontend/` | **删除**（前端改后端托管后无用） |
| `PROJECT_NAME="Full Stack FastAPI Project"` | `.env:16` | 改为 `IrsBot` |
| `FRONTEND_HOST=http://localhost:5173` | `.env:9` | 改为 `http://localhost:8000`（单端口） |

#### 3.2.2 ⚠️ 看似模板、实则不能直接删（易误判）

| 对象 | 为什么不能直接删 |
|---|---|
| **`DOCKER_IMAGE_BACKEND` / `DOCKER_IMAGE_FRONTEND` / `TAG`** | 名字极像模板产物，但 `prestart` 与 `backend` 的 `image:` 字段**正在引用它们**。删 `.env` 里的变量而不删 `image:` 字段 → `?Variable not set` 立即报错。**可删，但必须与 `image:` 字段同批删** |
| **`frontend/src/components/ui/`**（shadcn/ui） | 成熟的组件库，是"webui 可直接拿来用"的核心价值，**保留** |
| **`apiClient` 自动生成机制** | `openapi-ts.config.ts` + `openapi.json` 驱动前端类型安全，**保留** |
| **`routeTree.gen.ts` 生成器** | TanStack Router 自动生成，**保留**（不要手工编辑） |

#### 3.2.3 ✅ `items` 已确认是模板残留（可删）

**核实结论（2026-09-16，读了前后端全部代码）**：

| 证据 | 内容 |
|---|---|
| `backend/app/api/routes/items.py` | 标准模板 CRUD：`Item` 模型只有 `title: str` + `description: str \| None`——**即待办事项示例** |
| `sqlmodel_models.py:74-110` | `ItemBase` / `ItemCreate` / `ItemUpdate` / `Item` / `ItemPublic` / `ItemsPublic`，字段与模板一字不差 |
| `frontend/src/routes/_layout/items.tsx` | 标题「**物品**」，空态文案「还没有任何物品 / 添加一个新物品开始使用」 |
| `Item.owner_id` | 带 owner 归属校验 → 模板的"per-user items"示例 |

**判定：纯模板示例，与 IrsBot 的 Agent / RAG / 对话能力零关系 → 删除。**

删除清单（全部同批清理，避免悬空引用）：

| 类型 | 路径 |
|---|---|
| 后端路由 | `backend/app/api/routes/items.py` + `api/main.py` 里的 `include_router(items.router)` |
| 后端模型 | `sqlmodel_models.py` 中 `Item*` 六个类 + `Item` 表 |
| 数据库迁移 | **新增一个 alembic 迁移删 `item` 表**（不要改历史迁移文件） |
| 前端路由 | `frontend/src/routes/_layout/items.tsx` |
| 前端组件 | `frontend/src/components/Items/`（AddItem / columns 等） |
| 前端 Pending | `frontend/src/components/Pending/PendingItems.tsx` |
| 侧边栏入口 | `frontend/src/components/Sidebar/` 中指向 `/items` 的导航项 |

> ⚠️ **迁移注意事项**：本项目迁移策略是 `alembic upgrade head`（`.env`/`prestart` 均为 upgrade，**不 downgrade**）。
> 所以删除 `Item` 表要**新增一个 forward 迁移**，而不是删除历史文件——否则已有数据库升级时会缺表报错。
>
> ⚠️ **D5 数据迁移影响**：删除 `item` 表意味着**本机 PG 的 `item` 表数据不迁移**（模板示例数据，无价值）。
> 这与 D5.1 盘点结论一致：真实资产只有 5 类，不含 `item`。

### 3.3 需要新增/调整的内容

#### 3.3.1 PostgreSQL（保留，但改为本地友好）

```yaml
db:
  image: postgres:18
  restart: unless-stopped
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
    interval: 10s
    retries: 5
    start_period: 30s
    timeout: 10s
  volumes:
    - irsbot-db-data:/var/lib/postgresql/data/pgdata
  environment:
    - PGDATA=/var/lib/postgresql/data/pgdata
    - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?}
    - POSTGRES_USER=${POSTGRES_USER:?}
    - POSTGRES_DB=${POSTGRES_DB:?}
  ports:
    - "5432:5432"        # 暴露给宿主机（便于迁移时 pg_dump）
```

> ⚠️ **端口冲突风险**：你本机 PG 已占用 5432。若两者同时运行会冲突。
> **处置**：迁移期间临时停掉本机 PG，或把容器端口映射为 `5433:5432`。

#### 3.3.2 Milvus（✅ M2 已查明，方案已确定）

> **M2 调研结论（2026-09-16 晚实测）**：现网 Milvus 是**单容器内嵌 etcd + local 存储**，由 `D:\Milvus\standalone.bat` 以**独立 `docker run`** 启动（**非 compose 管理**）。
> 因此**不需要** etcd 独立容器，**也不需要 MinIO**。v1–v3 里设想的「Milvus 全家桶 3 容器」是**过度设计**，已作废。

**现网真实启动参数（唯一权威来源：`D:\Milvus\standalone.bat`）**：

```bat
docker run -d --name milvus-standalone --security-opt seccomp:unconfined ^
    -e ETCD_USE_EMBED=true ^
    -e ETCD_DATA_DIR=/var/lib/milvus/etcd ^
    -e ETCD_CONFIG_PATH=/milvus/configs/embedEtcd.yaml ^
    -e COMMON_STORAGETYPE=local ^
    -e DEPLOY_MODE=STANDALONE ^
    -v "%cd%\volumes\milvus:/var/lib/milvus" ^
    -p 19530:19530 -p 9091:9091 -p 2379:2379 ^
    milvusdb/milvus:v2.6.14 milvus run standalone
```

**对应 compose 写法（D1.2 应改为这个，替换旧的全家桶方案）**：

```yaml
milvus:
  image: milvusdb/milvus:v2.6.14          # ✅ 与现网一致，不用 override 里的 v2.5.14
  container_name: irsbot-milvus
  restart: unless-stopped
  security_opt:
    - seccomp:unconfined                   # 现网参数，必须保留
  command: milvus run standalone
  environment:
    - ETCD_USE_EMBED=true                  # 内嵌 etcd，省掉独立 etcd 容器
    - ETCD_DATA_DIR=/var/lib/milvus/etcd
    - ETCD_CONFIG_PATH=/milvus/configs/embedEtcd.yaml
    - COMMON_STORAGETYPE=local             # 本地存储，省掉 MinIO
    - DEPLOY_MODE=STANDALONE
  volumes:
    - ./milvus-config/embedEtcd.yaml:/milvus/configs/embedEtcd.yaml:ro
    - irsbot-milvus-data:/var/lib/milvus
  # ⚠️ 端口映射见下方「端口冲突」处置，不要照抄现网的 19530/9091/2379
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
    interval: 30s
    start_period: 90s
    timeout: 20s
    retries: 3
```

**`embedEtcd.yaml` 内容**（现网文件，需一并纳入仓库）：

```yaml
listen-client-urls: http://0.0.0.0:2379
advertise-client-urls: http://0.0.0.0:2379
quota-backend-bytes: 4294967296
auto-compaction-mode: revision
auto-compaction-retention: '1000'
```

**⚠️ 端口冲突（必须在 D1.1 一并处置）**：

| 端口 | 现网占用方 | 处置 |
|---|---|---|
| `19530` | `milvus-standalone`（Up 46h） | 🔴 **二选一**：停掉现网容器由 compose 接管 / 不映射端口，backend 走 `host.docker.internal:19530` |
| `9091` | 同上（metrics/health） | 同上 |
| `2379` | 同上（内嵌 etcd） | 同上 |
| `5432` | **本机 PG 18.3** | 🔴 容器 `db` **不要映射** `5432:5432`（历史教训：容器版 PG 当年就是这样被挤停的） |

> ⚠️ **数据卷位置**：现网数据在 `D:\Milvus\volumes\milvus`（`data` 2.4 MB + `rdb_data` 5.5 MB + `etcd`）。
> 若要让 compose 复用现有数据，需把命名卷改为**绑定挂载**该目录，或先迁移数据。

> ✅ **一处需要修正的旧描述**：本文档 v1–v3 说「Milvus 全家桶内存占用 2G+」——**内嵌 etcd + local 存储方案下，单容器内存占用显著低于 3 容器方案**，此风险可下调。

#### 3.3.3 后端（调整）

```yaml
backend:
  build:
    context: .
    dockerfile: backend/Dockerfile
  restart: unless-stopped
  depends_on:
    db:
      condition: service_healthy
    milvus:
      condition: service_healthy
  env_file:
    - .env
  environment:
    - POSTGRES_SERVER=${POSTGRES_SERVER:-db}     # ← D6 的后门：默认容器内，可覆盖
    - MILVUS_URI=http://milvus:19530
  ports:
    - "8000:8000"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/utils/health-check/"]
    interval: 10s
    timeout: 5s
    retries: 5
```

#### 3.3.4 前端（✅ 方案已定：照 AstrBot 的做法）

**关键变更**：本地版让**后端托管前端静态产物**，实现单端口。**方案定为「后端托管 + 可覆盖 dist 挂载」**，参考 AstrBot 的成熟实现。

##### AstrBot 的做法（已读源码核实，2026-09-16）

| 环节 | AstrBot 实现 | 文件位置 |
|---|---|---|
| 构建与后端**解耦** | 镜像内是**预构建好的 dist**，构建阶段 `COPY . /AstrBot/` 时把 `data/dist` 一起带进去，**构建镜像时不跑 npm** | `Dockerfile`（单阶段，无 node 构建 stage） |
| dist 路径**三级优先级** | ① 显式 `webui_dir` 参数 → ② `data/dist/`（用户自己放进来的） → ③ `astrbot/dashboard/dist/`（随包绑定） | `dashboard/server.py:235-254` |
| 静态托管 | `Quart("dashboard", static_folder=self.data_path, static_url_path="/")` | `dashboard/server.py:257` |
| **SPA fallback** | **显式枚举全部前端路由**，逐个 `add_url_rule(i, view_func=self.index)`，全部返回 `index.html` | `dashboard/routes/static_file.py:8-30` |
| 部署 | **单容器**，一个端口 `6185`，`./data` 绑定挂载 | `compose.yml` |

**AstrBot 为什么要枚举路由，而不用 catch-all？**
因为它基于 **Quart（Flask 系）**，而本项目是 **FastAPI（Starlette）**。两者 fallback 的写法不同：

- **FastAPI 更省事**：`@app.exception_handler(404)` + 判断路径是否以 `/api` 开头 → 是则返 JSON 404，否则返 `index.html`。
  这比枚举路由**更不易漏**——新增前端路由不用回来改后端。

**为什么不学 AstrBot 用通吃路由？** 有个陷阱：如果写 `app.get("/{full_path:path}")` 通吃，**它会抢在 API 路由前面或与之冲突**（取决于注册顺序），导致 `/api/v1/...` 也返回 HTML。所以本项目采用 **404 handler 方案**，并显式排除 `/api` 前缀。

##### 本项目采用的方案（AstrBot 思路 + FastAPI 适配）

```yaml
backend:
  build:
    context: .
    dockerfile: backend/Dockerfile
  environment:
    - MILVUS_URI=http://milvus:19530
    - IrsBot_WEBUI_DIR=/app/frontend-dist    # ← 对应 AstrBot 的 webui_dir 参数
  volumes:
    - ./frontend/dist:/app/frontend-dist     # ← 覆盖机制：前端单独构建，立即生效
```

**后端托管代码（`app/main.py` 末尾，✅ 已实施）**：

```python
import os
from pathlib import Path

from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# dist 目录：环境变量优先，其次镜像内置路径（对应 AstrBot 的三级路径优先级）
WEBUI_DIR = Path(os.getenv("IrsBot_WEBUI_DIR", "/app/frontend-dist"))
WEBUI_INDEX = WEBUI_DIR / "index.html"

# ⚠️ 整个静态托管段用 index.html 是否存在来守卫：
#    dist 不存在（如纯 API 开发、未构建前端）时**静默跳过**，后端退化为纯 API 服务。
#    这一点很重要 —— 它保证"前端没构建"不会让后端启动失败。
if WEBUI_INDEX.exists():
    WEBUI_ASSETS = WEBUI_DIR / "assets"
    if WEBUI_ASSETS.exists():
        app.mount("/assets", StaticFiles(directory=WEBUI_ASSETS), name="webui-assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request, exc):
        """SPA 路由回退：前端路由（/chat、/settings…）在服务端没有对应文件，
        需回退 index.html 交给前端路由，否则**刷新页面 404**。
        """
        # ① API 404 保持 JSON，别返回 HTML
        if exc.status_code == 404 and not request.url.path.startswith(
            settings.API_V1_STR
        ):
            # ② 只对"想要 HTML"的请求回退：静态资源（图片等）缺失时保持 404，
            #    否则前端加载失败会拿到一坨 HTML，报错莫名其妙
            if "text/html" in request.headers.get("accept", ""):
                return FileResponse(WEBUI_INDEX)
        return await http_exception_handler(request, exc)
```

> 🔴 **三个必须注意的点**：
> 1. **`/api` 前缀必须排除** —— 否则 API 打错地址时会收到 HTML，前端报 `JSON parse error`，排查方向被带偏。
> 2. **`accept` 头必须判断** —— 否则缺失的 `.js`/`.png` 也会返回 `index.html`，浏览器解析失败时报错极难懂。
> 3. **WebSocket 路由不受影响** —— `agent_ws` 走 WS 协议，不经过 HTTP 404 handler，无需额外处理。

##### ⭐ 前端 API 地址改造（D1.3b —— 方案的关键，⚠️ 有三处陷阱）

**目标**：让前端用**同源相对路径**，从而消除构建期注入。

原来有**三处**引用 `VITE_API_URL`，改法**各不相同**，且**不能统一改成 `/api`**：

| # | 文件 | 原写法 | 改法 | 若统一改成 `/api` 会怎样 |
|---|---|---|---|---|
| 1 | `src/main.tsx:16` | `OpenAPI.BASE = import.meta.env.VITE_API_URL` | `OpenAPI.BASE = ""` | 可以，但 `""` 更准确地表达"同源" |
| 2 | `src/routes/_layout/chat.tsx:23` | `` `${VITE_API_URL}/api/v1/agent/conversations` `` | `"/api/v1/agent/conversations"` | 🔴 变成 `/api/api/v1/...`（**路径重复**） |
| 3 | `src/hooks/useAgentChat.ts:50` | `VITE_API_URL.replace(/^http/, "ws") + ...` | 用 `location` 动态拼（见下） | 🔴 **正则静默失效** → WS 直接坏 |

**第 3 处的正确写法**（最隐蔽的一处）：

```ts
// ws: 页面是 https 时用 wss（否则浏览器拦截混合内容）
// host: 直接用 location.host → 谁托管页面就连谁（天然同源）
const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:"
const wsUrl =
  `${wsProtocol}//${location.host}` +
  `/api/v1/agent/chat/ws/${conversationId}` +
  `?token=${localStorage.getItem("access_token")}`
```

> ⚠️ **为什么不能沿用 `replace(/^http/, "ws")`**：
> 该写法依赖字符串里存在 `http`。一旦值变成相对路径 `/api`，
> **正则匹配不到任何东西、也不报错**（`replace` 无匹配时原样返回）→
> 得到 `/api/api/v1/...` 这种非法 ws 地址，浏览器只报"连接失败"，
> **看不出真实原因**。这是本次改造中最容易踩且最难排查的坑。

##### 🔑 配套必需：Vite dev server proxy（否则开发入口会坏）

改成相对路径后，**开发时（5173）会出问题**：浏览器请求的是
`http://localhost:5173/api/v1/...`，而 5173 是 Vite 的静态服务器，
**不认识 `/api`，请求到不了后端**。

因此 `vite.config.ts` **必须**补上 proxy：

```ts
server: {
  proxy: {
    "/api": {
      target: process.env.BACKEND_URL || "http://localhost:8000",
      changeOrigin: true,
      ws: true,   // ⚠️ 必须开：WebSocket 与 API 同前缀，否则聊天流式连不上
    },
  },
},
```

> 💡 **收益**：有了 proxy 后，**开发和生产的代码路径完全一致**（都是 `/api/v1/...`、都是同源），
> 唯一差别只是"谁在转发" —— 开发时是 Vite，生产时是后端自己托管。
> 后端换端口也不用改代码：`BACKEND_URL=http://localhost:8001 bun run dev`。

> 🧹 **连带**：`frontend/.env` 里的 `VITE_API_URL` 应**删除**（留着会误导后来者以为 API 地址由它控制）。
> `frontend/src/vite-env.d.ts` 的 `readonly VITE_API_URL: string` 声明也应一并移除。

##### ⚠️ 前端是 **bun workspace 单仓**（构建命令必须在仓库根跑）

**实机探明（2026-09-16）**：

| 事实 | 证据 |
|---|---|
| 锁文件在**仓库根** | 根目录有 `bun.lock`（+ `package-lock.json`）；`frontend/` 下**没有任何锁文件** |
| 依赖装在**仓库根** | 根 `node_modules/` 有 **251 个包**（`typescript` / `vite` / `react` 俱全）；`frontend/node_modules/` **只有 3 个隐藏目录**（`.cache` / `.vite` / `.vite-temp`），无任何真实包 |
| Dockerfile 也按 workspace 写 | `frontend/Dockerfile:6-8`：`COPY package.json bun.lock /app/` + `COPY frontend/package.json /app/frontend/` |

**🔴 因此**：

| 操作 | ❌ 错误写法 | ✅ 正确写法 |
|---|---|---|
| 装依赖 | `cd frontend && bun install` | `cd <仓库根> && bun install` |
| 构建前端 | `cd frontend && bun run build` | `cd <仓库根> && bun run --filter frontend build` 或 `bunx --bun vite build`（在 frontend 内，依赖靠根 node_modules 提升解析） |
| 类型检查 | `cd frontend && tsc` | `cd <仓库根> && node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json` |

> 💡 **踩坑提示**：在 `frontend/` 里跑 `bun install` 会**因为找不到锁文件而全量重装**，
> 生成一个 `frontend/bun.lock` 并污染目录结构。**不要这样做。**
>
> ✅ **已验证**：从仓库根执行 `node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json` → **ExitCode 0**（三处 API 地址改动类型正确）。

##### 为什么选这个方案（而不是 A：前端独立容器）

| 维度 | A：前端独立容器 | **本方案：后端托管 + 挂载 dist** |
|---|---|---|
| 端口 | 双端口（5173 + 8000） | **单端口 8000** ✅ |
| 改前端是否要重建后端镜像 | 否 | **否**（绑定挂载覆盖 dist）✅ |
| 生产/分发形态 | 多一个容器 | 单容器 ✅ |
| 构建期 `VITE_API_URL` 注入 | 必须（跨域） | **不需要**（同源，用相对路径）✅ |

**关键收益**：把 `VITE_API_URL` 改成相对路径 `/api` 后，**同一个 dist 产物在任意主机、任意端口都能用**——这对"分发给别人"是决定性的，否则用户机器上的 API 地址会被烤死在构建产物里。

##### 前端构建方式（开发 vs 分发）

> ⚠️ 所有命令都在**仓库根**执行（本前端是 bun workspace，见上一小节）。

| 场景 | 做法 |
|---|---|
| **本地开发**（常用） | 仓库根：`bun run --filter frontend dev`（Vite dev server + 热更新，**已配 proxy**），后端只跑 API |
| **验证托管形态** | 仓库根：`bun run --filter frontend build` → 产物落 `frontend/dist/` → 绑定挂载立即生效，**无需重建后端镜像** |
| **分发给用户** | 在镜像构建阶段把 `frontend/dist` COPY 进后端镜像（需改 `backend/Dockerfile` 加 `COPY ./frontend/dist /app/frontend-dist`），此后用户无需构建前端 |

> ⚠️ **前置条件（已缓解）**：上述 COPY 要求 `frontend/dist` 在 `docker build` **之前**已存在。
> **当前策略（已实施）**：先不做 COPY（D1.3c 推迟），靠 `compose.override.yml` 的**绑定挂载**提供 dist。
> 好处：① 构建镜像不受 dist 是否存在影响；② 改前端无需重建后端镜像。
> 代价：分发时用户必须先自己 `bun run build`。
> **D1.3c（分发形态）再做 COPY**，届时需在 README 写清「构建镜像前先 `bun run build`」，或加一个只装依赖的兜底 stage。
>
> 💡 **重要澄清**：由于 `main.py` 用了 `WEBUI_INDEX.exists()` 守卫，**dist 缺失不会导致后端启动失败**，
> 只是退化为纯 API 服务。所以 D1.3c 是「分发优化」，**不是「能否跑起来」的阻塞项**。

#### 3.3.5 ⚠️ 构建速度：**容器虚拟网络吞带宽**（实测数据，根因已锁定）

首次构建 backend 镜像**耗时超过 20 分钟仍未完成**，累计失败 **5 次**（见 `docker buildx history ls` 的 Error 记录）。

##### 实测数据（全）

| 项 | 实测 | 速度 | 结论 |
|---|---|---|---|
| Docker 基础层 `python:3.10` | 236 MB / 166 秒 | ~1.4 MB/s | 尚可 |
| `uv` 镜像（ghcr.io） | 23 MB / 560 秒 | **41 KB/s** | ⚠️ 慢 |
| PyPI `pygments`（1.2 MB，官方源） | 264 秒 | **4.5 KB/s** | ⚠️ 极慢 |
| `dkimpy==1.1.8` 源码编译（官方源） | **425 秒** | — | 官方源只给 sdist |
| **容器内 `urlopen` 清华源索引页** | 45,839 B / **0.3 秒** | **~150 KB/s** | ✅ 网络通 |
| **容器内 uv 下 `pygments`（清华源）** | 1.2 MB / **598 秒** | **2 KB/s** | 🔴 慢于官方源 |
| **容器内 uv 下 `pydantic-core`（清华源）** | 2.0 MB / **179 秒** | **11 KB/s** | 🔴 龟速 |
| `dkimpy` 编译（清华源） | **2.1 秒** | — | ✅ wheel 秒装 |
| **宿主机**下 `pygments`（清华源） | — | **1370 KB/s** | ✅ 正常 |

##### 🔴 根因锁定：不是"源慢"，是**容器虚拟网络层限吞吐**

同一容器、同一域名、同一时刻：

| 请求类型 | 速度 |
|---|---|
| 小请求（索引页 45 KB，单次往返） | **150 KB/s** |
| 大文件流（包下载） | **2–11 KB/s** |

**相差 15–75 倍**。而宿主机同源实测 **1370 KB/s**。

> 诊断模式：**小请求飞快 + 大文件龟速 = 连接可建立、吞吐被掐**。
> 排除了 DNS / 路由 / 源站问题 —— 问题在 **Docker Desktop 虚拟网络层（vpnkit / WSL2 NAT）**。

**这解释了两个反直觉现象：**
1. 加了清华源后 `dkimpy` 从 425 秒 → **2.1 秒**（单个小 wheel，抢到带宽）—— 但 `pygments` 反而**比官方源更慢**（2 KB/s vs 4.5 KB/s，在并发洪流里被淹没）。
2. 换任何 PyPI 镜像源都**不会**根本解决 —— 瓶颈不在这里。

##### ✅ 有效：清华源（已实施，仍有价值）

```dockerfile
# ⚠️ 必须在所有 uv sync / uv pip install 之前声明，否则不生效
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
```

**收益**：提供**预编译 wheel**，消除源码编译（`dkimpy` 425 秒 → 2.1 秒）。
换源只需改这一行（阿里云 / 腾讯云同理）。

##### 🔑 关键洞察：`--no-cache` 断的是**层缓存**，断不了**包缓存**

```powershell
docker compose --progress=plain build --no-cache backend   # ← 这个 --no-cache
```

- `--no-cache` → 让 `RUN` 层**每次重新执行**
- `--mount=type=cache,target=/root/.cache/uv` → **不受 `--no-cache` 影响**，uv 的包缓存**一直在累积**

**所以**：`docker buildx du` 的 371.8 MB 是**真实累积的包缓存**，并未白费。
但**层缓存从未建立过**（5 次全 Error，没有一次成功）→ **每次都从零开始**。

> ✅ **正确做法：不要加 `--no-cache`。** 让已成功的层可复用。

##### 🎯 结论与建议

**这个构建不是 D1.3 的阻塞项。** 依据：

1. **`WEBUI_INDEX.exists()` 守卫**保证 dist 缺失时后端仍能启动（退化为纯 API）→ 镜像不是"能否跑起来"的前置。
2. **本机 `.venv`（Python 3.13.0）+ `frontend/dist`（已构建，见 §3.3.4）** 足以完整验证 D1.3a 的全部逻辑（静态托管 + SPA fallback）。
3. **容器网络问题属环境问题，非代码问题** —— 换机器 / 换网络即消失，不应写进代码。

**建议顺序**：
1. **先做本机验证**（2 分钟，拿到 D1.3 的真结论）
2. 镜像构建**并行继续**，不作为阻塞
3. 若仍需镜像：考虑「**预置 wheelhouse**」方案（把宿主 `uv cache` 的 2.4 GB 产物导出为本地 wheel 目录，构建时 `--find-links` 指向），彻底绕开下载

##### 🧠 本节的元教训

**「观察指标连续骗你两次时，不要再调参数，去换指标。」**

本项目在"构建慢"这件事上被**日志文件修改时间**骗了三次 ——
`Tee-Object` 只在缓冲区满或进程结束时刷盘，**进程在跑、日志是死的**。

| ❌ 不可靠判据 | ✅ 可靠判据 |
|---|---|
| `build.log` 的最后修改时间 | `docker buildx history ls` 的 `DURATION`（末尾 `+` 表示在跑） |
| `docker buildx du` 的 last-used 时间 | `--progress=plain` 输出的**行号**是否推进 |
| 日志文件的 size 是否变化 | `docker buildx history ls` 的 `STATUS` 字段 |

#### 3.3.6 ❌ 已踩的坑（记录以免重犯）

**坑 A：把「慢」误判成「卡死」**

- **现象**：`docker buildx du` 里那条 `exec.cachemount` 的「最后一次使用」时间 **18 分钟没刷新** → 判定卡死、建议停掉。
- **实际**：`#11 705.5 Built dkimpy==1.1.8` —— **它一直在编译，编译完就继续了**。
- **教训**：**缓存的 last-used 时间在单条 `RUN` 执行期间不会刷新**，
  所以「多久没动」**无法区分「慢」与「死」**。可靠判据是看**构建输出行号是否推进**。

**坑 B：从 AstrBot 抄了「预装编译工具链」，但前提不成立**

- **抄的内容**：AstrBot `Dockerfile:6-23` 预装 `gcc` / `build-essential` / `python3-dev` / `libffi-dev` / `libssl-dev`。
- **漏掉的前提**：AstrBot 装编译器，是因为它有**大量需要编译的包**（`faiss-cpu`、`pycryptodome`）；
  而 IrsBot 唯一触发源码编译的是 `dkimpy`（**邮件库，模板残留**）。
- **代价**：`apt-get install` 要下 **106 MB 包 / 占用 415 MB 磁盘**，在 98.9 KB/s 下需 **18 分钟** ——
  为了优化 425 秒的编译，**反而净亏**。
- **处置**：**已回退**该改动，只保留清华源。

> 🧠 **可迁移原则**：**当「优化的代价」大于「被优化对象」本身时，该做的是消除对象，而不是优化它。**
> IrsBot 的正确解法是**删掉邮件依赖**（消除编译需求），而不是**装编译器去加速编译**。

**坑 D 🔴：「构建成功但功能缺失」—— `uv sync` 默认不装 optional-dependencies**

**这是本轮最危险的一个坑 —— 镜像构建成功、容器正常启动、API 可用，但核心能力全缺。**

- **现象**：`backend:latest` 构建成功（647 MB），`#11` 装了 **87 个包**。但清单里**没有** `langchain` / `langgraph` / `pymilvus` / `mcp` / `tiktoken` / `pypdf` / `faiss-cpu`。
- **根因**：IrsBot 的核心能力定义在 `backend/pyproject.toml` 的 **`[project.optional-dependencies]`**（`langchain` / `rag` / `mcp` / `all` 四个 extra）。
  **`uv sync` 默认只装主依赖 + dev group，不装 optional-dependencies。**
- **后果**：容器**能启动、健康检查能过**，但一调用 Agent / 知识库就报
  `ModuleNotFoundError: No module named 'langchain'`。
  **这类"配置缺项"故障最难排查** —— 因为所有显性指标（构建成功、容器 healthy）都是绿的。
- **为何难发现**：本机 `.venv` 装了 extras（因为 `.venv` 是开发时装的），
  所以**"本地能跑、容器报错"** —— 只有真正调用到那个功能才暴露。

**解法（已实施）**：两处 `uv sync` 都加 `--all-extras --no-dev`：

```dockerfile
uv sync --frozen --no-install-workspace --all-extras --no-dev --package app   # 第 1 处（装依赖）
uv sync --frozen --all-extras --no-dev --package app                          # 第 2 处（装项目本身）
```

| 参数 | 作用 | 不加的后果 |
|---|---|---|
| `--all-extras` | 装上全部 optional-dependencies | 🔴 **核心功能缺失**（LangChain / RAG / MCP） |
| `--no-dev` | 排除 `[dependency-groups] dev` | ⚠️ 镜像多装 pytest / mypy / ruff / pre-commit（多约 34 MiB 下载） |
| `--package app` | workspace 成员名 | 装错目标 |

**✅ dry-run 验证（2026-09-17）**：

```
$ uv sync --frozen --no-install-workspace --all-extras --no-dev --package app --dry-run
Would download 140 packages
Would install 140 packages
```

**87 → 140 个包**（多出的 53 个含 `anthropic` / `openai` / `faiss-cpu` / `pymilvus` / `tiktoken` / `beautifulsoup4` / `grpcio` …），
且 `mypy` / `ruff` / `zizmor` **已从清单消失**。

> 🔑 **顺带发现**：`dev` group 里的 `mypy`(14.3MiB) + `ruff`(10.8MiB) + `zizmor`(8.9MiB) ≈ **34 MiB**
> 恰是上一轮构建**最后下载完的三个包**（`#11 1536 zizmor` / `1630 ruff` / `1716 mypy`）——
> 在受限网络下它们多花了约 **20 分钟**。`--no-dev` 直接把这部分省掉。

> 🧠 **可迁移原则**：**「构建成功」不等于「功能齐备」。**
> 验证一个新镜像时，不要只看 `docker build` 的 ExitCode / `docker ps` 的 healthy ——
> **要显式检查关键依赖在不在**：
> ```bash
> docker run --rm --entrypoint python backend:latest -c "import langchain, pymilvus, mcp; print('OK')"
> ```

**坑 C：用「日志文件的修改时间」判断构建是否在跑（骗了三次）**

- **现象**：`build.log` 长时间不更新 → 判定"卡住 / 中断"。
- **实际**：`docker buildx history ls` 显示该构建 **Running**，`DURATION` 的末尾 `+` 一直在涨。
- **根因**：**`Tee-Object` 只在缓冲区满或进程结束时刷盘。** 进程在跑，日志却是死的。
- **连带误判**：`docker buildx du` 里 cache mount 的 last-used 时间**在单条 `RUN` 执行期间不会刷新**（与坑 A 同源）。
- **正确判据表**：

| ❌ 不可靠 | ✅ 可靠 |
|---|---|
| `build.log` 的 LastWriteTime | `docker buildx history ls` 的 `DURATION`（`+` 在涨 = 在跑） |
| `buildx du` 的 last-used 时间 | `--progress=plain` 的**行号**是否推进 |
| 日志文件 size 是否变化 | `docker buildx history ls` 的 `STATUS = Running` |

- **处置**：**不再用日志文件当判据**；`--progress=plain` 直接输出到终端（不过 `Tee`）以实时观察。

> 🧠 **可迁移原则**：**当一个观察指标连续骗你两次，不要再调参数，去换指标。**
> 「多久没动」这个指标本身就无法区分「慢」与「死」——问题出在指标，不在你观察得不够仔细。

#### 3.3.7 📌 待决策：邮件依赖是否删除（影响构建 7 分钟 + 镜像 415 MB）

**现状**：`pyproject.toml:9,23,24` 引入 `email-validator` + `aiosmtplib` + `emails`；
其中 `emails` 拖入 **`dkimpy`**（邮件签名库，**从源码编译 425 秒**）。

**全部引用面（已查清）**——**都是模板的「用户注册 / 找回密码」功能**：

| 位置 | 用途 | 性质 |
|---|---|---|
| `api/routes/login.py:60` `recover_password` | 发密码重置邮件 | 模板 |
| `api/routes/login.py:111` `recover_password_html_content` | 前端展示 | 模板 |
| `api/routes/users.py:69` | 新建用户欢迎邮件（有 `settings.emails_enabled` 守卫） | 模板 |
| `api/routes/utils.py:21` `test-email` | 测试端点 | 模板 |
| `core/utils/email.py` | 发信实现（用 `emails` 库） | 模板 |
| `core/utils/__init__.py:3-11` | 导出以上 6 个函数 | 模板 |

**AstrBot 的做法（已核实源码）**：AstrBot 的邮件能力**全部在插件市场**（`data/plugins.json` 里的"SMTP 邮件小工具"等），
**核心依赖零邮件库** —— 同一件事，成熟项目选择「给需要的人」而非「让所有人承担」。

**判定建议：删除**。理由：
1. **场景不存在**：本地单用户应用，「联系不上管理员」不成立 —— 用户自己就是管理员，忘密码直接改库。
2. **前置条件本身不成立**：`.env` 里 `SMTP_HOST=mailcatcher`，而 mailcatcher 是模板的**本地假邮件服务器** —— 邮件根本发不出去。
3. **AstrBot 印证**：同类项目的核心依赖不含邮件库。

**⚠️ 但这属于 D1.4 模板残留清理的范围**（要连带动前端「忘记密码」页），
**建议在 D1.3 验证通过后单独做**，以免混淆「整合是否成功」与「依赖是否精简」两个结论。

### 3.4 D1 验收
- [ ] `docker compose -f compose.local.yml config` 校验通过（无未定义变量）
- [ ] `docker compose -f compose.local.yml up -d` 能起来（无 traefik 报错）
- [ ] 所有服务 healthy
- [ ] 后端能连上容器内 PG 与 Milvus

---

## 四、D2 / D3 一键启动与首次引导

### 4.1 D2 启动脚本

- [ ] `scripts/start-local.ps1`（Windows，主目标平台）
  - 检测 Docker 是否安装/运行（未装则给出明确指引）
  - 检测端口占用（5432 / 8000 / 19530）
  - `docker compose -f compose.local.yml up -d`
  - 等待健康检查通过
  - 打印访问地址与管理账号
- [ ] `scripts/stop-local.ps1` / `.sh`
- [ ] `scripts/start-local.sh`（macOS / Linux 等价物）

### 4.2 D3 首次启动引导

- [ ] **`SECRET_KEY` 落盘**（修复 §1.5 问题 #1）
  - 位置：`.env` 或 `.irsbot/.env.local`（与数据同目录）
  - 首次启动生成 → 写入 → 后续复用
  - **不做这个，每次容器重启都会导致所有登录失效**
- [ ] **`FIRST_SUPERUSER_PASSWORD` 自动生成**（修复 §1.5 问题 #2）
  - 未配置时生成随机密码 → 控制台打印 + 写入 `.irsbot/initial_admin.txt`
  - 移除 `changethis` 默认值
- [ ] 自动建表（Alembic `upgrade head`，容器已有 `prestart` 机制）
- [ ] 启动完成打印：

```
✅ IrsBot 已就绪
   访问地址：http://localhost:8000
   管理员账号：admin@irsbot.local
   管理员密码：<随机串>（也在 .irsbot/initial_admin.txt）
   数据目录：Docker 卷 irsbot-db-data / irsbot-milvus-data
```

---

## 五、D5 数据迁移（⚠️ 高风险，需谨慎）

### 5.1 前置条件（强制）

- [ ] **D4 已通过**（新环境能起、能登录、能对话）
- [ ] **备份本机 PG 全量数据**
  ```powershell
  # 备份（本机 PG，5432）
  pg_dump -h localhost -p 5432 -U <user> -d <db> -F c -f irsbot_backup_20260916.dump
  ```
- [ ] **确认备份文件可读**（`pg_restore -l` 能列出内容）
- [ ] **备份 Milvus 数据**（向量数据在 MinIO 卷里，需一并处理）

### 5.2 迁移步骤

1. 停掉本机 PG（或改用 5433 端口映射，避免冲突）
2. 启动容器内 PG
3. `pg_restore` 恢复到容器内 PG
4. **验证数据完整性**：
   - 表清单一致（12 张表）
   - ⚠️ **关键表行数修正**（D5.1 盘点结果）：`app` 库真实资产为
     **`knowledge_bases` 1 个（非 22）/ `documents` 2 个 / `conversations` 51 条真实（非 126）/ `messages` 108 条 / `personas` 0 个真实（21 个全是测试残留）/ `mcp_servers` 0 个真实（17 个全是测试残留）/ `provider_configs` 1 个 / `user` 1 个**
5. 处理 Milvus 向量数据（⚠️ **M1 待调研**，但因真实文档仅 2 个 × 211 B，**重新索引成本极低，不再是阻塞项**）
6. 应用侧验证：登录 → 查看历史对话 → 检索知识库

### 5.3 数据盘点结论（✅ D5.1 已完成，逐行核对）

**真实资产（应迁移）**：

| 资产 | 数量 | 明细 |
|---|---|---|
| Provider 配置 | 1 | `default` / openai / `qwen3.8-flash` / is_default=t |
| 用户 | 1 | admin |
| 知识库 | 1 | "测试库"（`4302411d-2e1e-45d3-bab7-8e7999f1e131`，2026-09-11 建） |
| 文档 | 2 | 都是"退货政策.md"（211 B，3 chunks，status=done） |
| 实体文件 | 2 | `uploads\kb\4302411d-...\*_退货政策.md` |
| 真实会话 | 51 | 09-14 起（25/12/14 条） |
| 消息 | 108 | — |

**测试残留（应清理，需用户逐条确认）**：

| 残留 | 数量 | 特征 |
|---|---|---|
| 假知识库 | 21 | `kb0`/`kb1`/`kb2`/`KB1`/`kb-get`/`kb-del`，全部 2026-06-21 |
| 假 Persona | 21 | `P1`/`p-get`/`per0`/`per1`/`per2`/`p-del`，重复 4 组 |
| 假 MCP | 17 | `mcp1`/`m-get`/`srv0`/`srv1`/`m-del`，重复 4 组 |
| 测试会话 | 75 | 2026-06-21 批量产生 |
| `uploads\kb_test\` 文件 | 21 | pytest 产物 |

**待判断**：

| 项 | 说明 |
|---|---|
| 孤儿目录 `uploads\kb\a2e7d572-...` | 含 `*_测试文档.md`（563 B），**DB 中无对应 KB 记录**（KB 已删、文件残留） |
| `document_agent` 库 | 8670 kB 但**无任何表**（空壳） |
| `test_app` 库 | 测试库，可弃 |

> 🎉 **D5 风险等级由「高」下调为「低-中」**：真实资产仅 5 类、总体积 < 1 MB。
> 即使迁移失败，**重建成本约等于重新上传 2 个 211 B 文件 + 改 1 条 Provider 配置**。

**一句话**：**「全量迁移」实际上是一次小规模精选迁移 + 一次有据可依的清理。**

### 5.4 回滚方案

**保留备份文件 + 不删除本机 PG 数据**，直到新环境验证完全通过。
若迁移失败 → 恢复 `.env` 指向本机 PG，即可回到原状态。

### 5.5 待调研 / 待确认问题

| # | 问题 | 影响 | 状态 |
|---|---|---|---|
| **M1** | Milvus 向量数据能否跨实例迁移？ | 若不能，重新上传 2 个 211 B 文件 + 重建索引 | ⬜ 待做（**非阻塞**） |
| **M2** | 当前 Milvus 怎么启动？ | 已查明：单容器内嵌 etcd + local 存储 | ✅ 已完成 |
| **M3** | 本机 PG 与 `postgres:18` 兼容性？ | 已查明：本机 18.3，**完全兼容** | ✅ 已完成 |
| ~~旧 M2~~ | ~~22 个知识库哪些真有数据？~~ | **已由 D5.1 盘点取代** —— 真实仅 1 个 | ✅ 已完成 |
| **Q1–Q6** | Milvus 方案 / 端口 / override 处置 / 残留清理 / 凭据 / 孤儿目录 | 见 `PROGRESS.md` 第九点五节 | 🔴 **待用户确认** |

---

## 六、D6 工具权限开关

### 6.1 现状

| 工具 | 文件 | 风险 |
|---|---|---|
| `shell_execute` | `agent/builtins/shell.py` | 可执行任意命令 |
| `file_write` | `agent/builtins/file_ops.py` | 可写任意路径 |
| `file_read` | `agent/builtins/file_ops.py` | 可读任意路径（含密钥文件） |
| `web_search` / `knowledge_base_query` | — | 低风险 |

### 6.2 计划改动

- [ ] `Settings` 新增：
  ```python
  ENABLE_SHELL_TOOL: bool = False
  ENABLE_FILE_WRITE_TOOL: bool = False
  ENABLE_FILE_READ_TOOL: bool = True
  ```
- [ ] `ToolRegistry.get_all_tools()` 按开关过滤
- [ ] **在 Agent 注入阶段过滤**（`agent/nodes.py`），而非执行时拦截
- [ ] `file_read` / `file_write` 加路径白名单（限制在 `WORKSPACE_DIR` 内）
- [ ] 路径校验用 `Path.resolve()` 防 `../` 穿越与符号链接逃逸
- [ ] 前端设置页加开关 + 风险提示文案

> **为什么在注入阶段过滤？** 若执行时才拒，模型看不到工具却会反复尝试调用，在 `ToolMessage` 里收到错误——白白消耗轮次。让模型**根本不知道它存在**更干净。

---

## 七、D7 交付

- [ ] **README 增补**：
  - 「5 分钟跑通」（Docker 前置 + 启动命令）
  - 「数据在哪 / 怎么备份 / 怎么卸载」
  - 「哪些工具默认关闭、怎么开」
  - 「如何指向自己的 PG」（D6 后门用法）
- [ ] `.env.local.example` 精简模板
- [ ] 文档同步（见第八节）

---

## 八、连带需要同步的文档

| 文档 | 需要的修改 | 状态 |
|---|---|---|
| `istbot-implement-plan.md` | 定位改为 Docker 化；L1/L2 作废；写入 18 项验证基线 | ✅ 本轮 |
| `PROGRESS.md` | 当前阶段改为 D1–D7；M2/M3 完成；D5.1 盘点完成 | ✅ 本轮 |
| `astrbot-architecture.md` | 数据库/向量库行回滚为 PostgreSQL/Milvus | ✅ 本轮 |
| `spec.md` | 定位与部署方式同步 | ⬜ 待做 |
| `tasks.md` / `checklist.md` | 标题与阶段同步 | ⬜ 待做 |

---

## 九、风险登记

| 风险 | 概率 | 影响 | 应对 | 状态 |
|---|---|---|---|---|
| Traefik/域名依赖导致本地起不来 | **高** | 高 | D1 彻底剥离 | ⬜ |
| 端口冲突（本机 PG **5432** / Milvus **19530-9091-2379**） | **🔴 已确认会发生** | 中 | 见 3.3.2 端口处置表；容器 `db` 不映射 5432 | ⬜ |
| **两套 Milvus 方案并存导致选错** | **高** | 中 | Q1 决策；**采用现网 v2.6.14 内嵌方案** | 🔴 待确认 |
| `compose.override.yml` 混装开发工具进交付包 | **高** | 中 | Q3 决策：拆分配置 | 🔴 待确认 |
| **数据迁移丢数据** | ~~中~~ → **低** | ~~极高~~ → **中** | 强制备份 + 逐条验证 + 保留回滚；**且真实资产仅 5 类** | ✅ 风险已下调 |
| Milvus 向量数据不可迁移 | **中** | **低**（原为中） | M1；重新索引成本 = 上传 2 个 211 B 文件 | ⬜ 非阻塞 |
| `SECRET_KEY` 不落盘 → 容器重启登录失效 | **已存在** | 中 | D3 强制落盘 | ⬜ |
| `FIRST_SUPERUSER_PASSWORD=changethis` | **已确认存在** | 中 | D3.2 随机生成 + 打印 | ⬜ |
| 前端 SPA 路由刷新 404 | 中 | 中 | 后端加 catch-all 回退 `index.html` | ⬜ |
| Docker 镜像过大（含 langchain 全家桶） | 中 | 低 | 分层构建 + `.dockerignore`；不必强求小体积 | ⬜ |
| Milvus 内存占用 | ~~2G+（3 容器）~~ → **单容器，更低** | 低 | 用户已接受 | ✅ 已接受 |
| `psycopg` 连接泄漏（ResourceWarning） | 中 | 低 | 长期运行前修；D4 后可选 | ⬜ |

---

## 十、建议执行顺序（✅ 已按 M2/M3/D5.1 结论校准）

```
第 1 步（D1 前置）—— ✅ 已完成
  ├─ M2 现网 Milvus 启动方式  → 单容器内嵌 etcd + local 存储
  ├─ M3 本机 PG 版本          → 18.3，与 postgres:18 完全兼容
  ├─ D5.1 数据盘点            → 真实资产仅 5 类，D5 风险大幅下调
  └─ ~~🔴 待用户回答 Q1–Q6~~ → ✅ Q1–Q3 已确认；Q4–Q8 见 §9.5

第 2 步（D1.1，可立即开工）—— 剥离部署层残留
  删 traefik 全层 / ${DOMAIN} / ${STACK_NAME} / compose.traefik.yml
  / proxy / mailcatcher / playwright / nginx 配置
  → docker compose config 校验（目标：无任何 ?Variable not set 报错）
  → docker compose up -d db 验证最小面
  🔴 注意：容器 db 不要映射 5432（✅ D1.2 已处理）

第 3 步（D1.2）—— ✅ 已完成并验证
  单容器内嵌 etcd Milvus 已由 compose 接管，数据零迁移复用

第 3.5 步（D1.3 → D1.4 → D1.5）—— 前端托管与模板残留清理
  D1.3a main.py 静态托管 + SPA fallback（排除 /api）
  D1.3b VITE_API_URL 改相对路径 /api
  D1.3c backend/Dockerfile COPY frontend/dist
  D1.4  删 items 前后端 + 新增 alembic 迁移删表
  D1.5  DOCKER_IMAGE_* / TAG 清理（与 image: 字段同批）
  💡 D1.3–D1.4 同批改前端、只构建一次

第 4 步（D2 + D3）
  启动脚本 + 首次引导（SECRET_KEY 落盘、随机管理员密码）

第 5 步（D4）
  端到端验证 + 重跑测试基线（294 + 18）

第 6 步（D5，风险已下调为低-中）
  ⚠️ 先备份 → 演练恢复 → 清理测试残留（Q4）→ 迁移 5 类真实资产 → 逐条验证 → 保留回滚

第 7 步（D6 + D7）
  工具权限开关 + README
```

**建议的第一个动作**：**D1.1**（剥离 Traefik/变量/端口）—— 它不依赖任何待确认项，且最能快速暴露隐藏的线上耦合。
**唯一前置**：~~先花 1 分钟回答 Q1–Q3~~ → ✅ Q1–Q3 已确认，D1.2 已完成。Q4–Q8 可在 D5 前回答。

### 10.1 D1 子阶段拆分（细化，2026-09-16 更新）

| 子阶段 | 内容 | 状态 |
|---|---|---|
| **D1.1** | 剥离部署层残留：Traefik / `${DOMAIN}` / `${STACK_NAME}` / `external: true` / `compose.traefik.yml` / `proxy` / `mailcatcher` / `playwright` / nginx 配置；统一 `restart` 策略；`.env` 改 `PROJECT_NAME=IrsBot`、`FRONTEND_HOST=http://localhost:8000` | ⬜ **可立即开工** |
| **D1.2** | Milvus 改由 compose 管理（单容器内嵌 etcd + local 存储 + 绑定挂载复用数据） | ✅ 已完成并验证 |
| **D1.3a** | `app/main.py` 加静态托管 + SPA fallback（排除 `/api` 前缀 + 判断 `accept` 头） | ✅ **已编码**，待实机验证 |
| **D1.3b** | 前端 API 地址改**同源相对路径**（三处分别改）+ `vite.config.ts` 补 **proxy**（含 `ws: true`）+ 删 `.env` 的 `VITE_API_URL` | ✅ **已编码**，待实机验证 |
| **D1.3c** | `backend/Dockerfile` 增加 `COPY ./frontend/dist /app/frontend-dist`（**分发优化，非阻塞**） | ⬜ |
| **D1.3d** | `compose.override.yml` backend 绑定挂载 `./frontend/dist:/app/frontend-dist` | ✅ 已完成 |
| **D1.3e** | 移除 `frontend` 独立容器（nginx） | ⬜（并入 D1.1） |
| **D1.4** | 删除 `items` 模板残留（前后端 + 新增 alembic 迁移删表 + 侧边栏入口） | ⬜ |
| **D1.5** | `DOCKER_IMAGE_*` / `TAG` 清理（**须与 `image:` 字段同批删**） | ⬜ |

> 🔴 **D1.3b 的三处陷阱（务必按 §3.3.4 表格逐处改，不要统一替换）**：
> 1. `main.tsx` → `OpenAPI.BASE = ""`（不是 `"/api"`）
> 2. `chat.tsx` → 直接写 `"/api/v1/agent/conversations"`（若填 `/api` 会变成 `/api/api/v1/...`）
> 3. `useAgentChat.ts` → 用 `location.protocol` + `location.host` 动态拼（沿用 `replace(/^http/, "ws")` 会**静默失效**）
>
> ⚠️ **D1.3b 若漏了 Vite proxy，开发入口（5173）会直接坏掉** —— 因为相对路径请求打不到后端。
> 这是本次改造中"改完前端看起来对、一跑就 404"的根因，详见 §3.3.4。

> **为什么 D1.4（删 items）排在 D1.3 之后**：删前端路由会改动 `routeTree.gen.ts` 与侧边栏，
> 而 D1.3 会改前端构建配置——**同批改前端、只构建一次**，比分散到两轮省一半时间。

---

## 十一、变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-16 | v1：确立「零外部依赖」方向（SQLite + FAISS），阶段 L1–L4 |
| 2026-09-16 | v2：代码改动撤销；标记「待审阅，未施工」；Q1 增加权衡 |
| 2026-09-16 | v3：上游主计划第六至十节原地改写；本文档第七节同步 |
| 2026-09-16 | **v4：根本性转向** —— 用户决策保持 PostgreSQL + Milvus（D4），改为 Docker 一键启动（D5）；L1/L2 作废；新增默认容器内 PG + 环境变量后门（D6）；新增数据迁移阶段（D7）；基于 18 项集成测试通过的事实确立「已验证基线」 |
| 2026-09-16 晚 | **v5：调研结论落地** —— ① §3.3.2 **Milvus 全家桶方案作废**，改为「单容器内嵌 etcd + local 存储」（M2 实测结论）；② 新增端口冲突处置表；③ §5.3 新增 D5.1 逐行盘点结论（真实资产 5 类 / 测试残留 21+21+17+75+21）；④ §5.5 更新 M1–M3 状态（M2/M3 ✅，M1 非阻塞）；⑤ §九 风险登记表全面校准（D5 由「极高」下调为「中」，Milvus 内存风险下调）；⑥ §十 执行顺序按新结论重排，明确「D1.1 可立即开工」 |
| 2026-09-16 晚（续） | **v5 施工进度更新：D1.2 已完成并实机验证通过** —— ① `compose.override.yml` Milvus 段重写为单容器 v2.6.14（内嵌 etcd + local 存储 + `seccomp:unconfined`）；② 数据改**绑定挂载** `D:/Milvus/volumes/milvus:/var/lib/milvus`，实现**零迁移复用**现有 collection；③ 新建 `milvus-config/embedEtcd.yaml` 纳入仓库；④ `db` 移除 `5432:5432` 映射（避让本机 PG 18.3）；⑤ 修复 **`env_file` 覆盖 `environment`** 陷阱（`.env` 的 `POSTGRES_SERVER` 由 `localhost` 改 `db`，并在 override 的 `backend`/`prestart` 显式声明）；⑥ 旧容器 `milvus-standalone` 改名 `milvus-standalone-old` 保留作回滚；⑦ 8 项验证全部通过（含数据逐字节一致：data 2.4M + rdb_data 5.5M + 15 个 insert_log 段）；⑧ 文档状态行由「待审阅，未施工」改为「施工中，D1.2 已完成」。**下一步 D1.1** |
| 2026-09-16 晚（续 2） | **v5 定稿：模板残留清理范围 + 前端方案定案** —— ① **用户确认**项目基于 full-stack-fastapi-template，无关 IrsBot 的均可改，webui 可直接复用；② 新增 **§3.2.1 部署层残留清单**（traefik 全层 / `${DOMAIN}` / `compose.traefik.yml` / `proxy` / `mailcatcher` / `playwright` / nginx 配置）；③ 新增 **§3.2.2 易误判清单**（`DOCKER_IMAGE_*` / `TAG` 名为模板实为必需，须与 `image:` 字段同批删）；④ 新增 **§3.2.3 `items` 判定**——读前后端源码确认是模板待办示例（`title` + `description` + `owner_id`，前端标题「物品」）→ **确认删除**，含新增 alembic 迁移删表；⑤ **§3.3.4 前端方案定案**：照 **AstrBot 做法**（已读 AstrBot 源码：`dashboard/server.py` 三级 dist 优先级 + `static_file.py` 显式路由枚举 + Quart `static_folder`），本项目适配为 **FastAPI 404 handler + 排除 `/api` 前缀**，并保留**绑定挂载覆盖 dist** 能力；⑥ 新增 **§10.1 D1 子阶段拆分**（D1.1 / D1.2✅ / D1.3a-c / D1.4 / D1.5） |
| 2026-09-16 深夜 | **v7：D1.3a/3b 编码完成 + 修复既有 Dockerfile bug + 补全前端改造陷阱** —— ① 🔴 **修复 `backend/Dockerfile` 既有 bug**：`FROM python:3.10` 与 `backend/pyproject.toml` 的 `requires-python = ">=3.12,<4.0"` 冲突，导致 `uv sync` 直接失败（**与本次改造无关，是模板遗留**）。改为 `python:3.13-slim`（对齐本机 `.venv` 的 3.13.0，该版本已由 294 单测 + 18 集成测试验证）；② ✅ **D1.3a 编码完成**：`app/main.py` 末尾新增静态托管段（`IrsBot_WEBUI_DIR` 环境变量优先 → `WEBUI_INDEX.exists()` 守卫 → `/assets` 挂载 → `spa_fallback` 同时排除 `/api` 前缀**并判断 `accept` 头**）；③ ✅ **D1.3b 编码完成**：查清 `VITE_API_URL` 共有**三处**引用且改法各不相同（详见 §3.3.4 表格），⚠️ **不能统一替换成 `/api`** —— `chat.tsx` 会路径重复、`useAgentChat.ts` 的 `replace(/^http/, "ws")` 会**静默失效导致 WebSocket 坏掉**；④ 🔑 **发现并补上关键缺口**：改相对路径后 **Vite dev server 必须配 proxy**（`vite.config.ts` 新增 `server.proxy`，含 **`ws: true`**），否则 5173 开发入口的 `/api` 请求到不了后端 → **"改完前端看起来对、一跑就 404"**；⑤ 连带清理 `frontend/.env` 的 `VITE_API_URL`（改为说明性注释）；⑥ **重要澄清**：因 `main.py` 有 `exists()` 守卫，**dist 缺失不会让后端启动失败**（仅退化为纯 API），故 **D1.3c（COPY dist）是分发优化、不是阻塞项**；⑦ D1.3 由 3 项细化为 **a/b/c/d/e 五项**并标注完成度 |
| 2026-09-16 深夜 | **v7.1：探明前端为 bun workspace 单仓（影响所有构建命令）** —— 实机核实：① 锁文件（`bun.lock`）在**仓库根**，`frontend/` 下无锁文件；② 依赖装在**仓库根**（根 `node_modules` **251 个包**，`typescript`/`vite`/`react` 俱全），`frontend/node_modules` **仅 3 个隐藏目录、无真实包**；③ `frontend/Dockerfile:6-8` 也按 workspace 写（从根 COPY `package.json bun.lock`）。**结论**：所有前端命令（install / build / dev / tsc）**必须在仓库根执行**，在 `frontend/` 里跑 `bun install` 会生成污染性锁文件并全量重装。✅ 已验证：从根执行 `node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json` → **ExitCode 0**（D1.3b 三处改动类型正确）。已同步修正 §3.3.4 的构建方式表 |
