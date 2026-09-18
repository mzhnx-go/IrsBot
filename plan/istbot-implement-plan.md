# IrsBot 实施计划

> 更新时间：2026-09-16 ｜ 分支：`feat/agent-platform`（未推送远端）
> **本文档为 IrsBot 唯一权威实施计划**（原 `progress.md` 已并入本文件）
> 对照文档：[astrbot-architecture.md](./astrbot-architecture.md)（架构参考，仍有效）
> ⚠️ 已弃用（2026-09-17 改名+加声明头，仅历史参考）：[DEPRECATED-spec.md](./DEPRECATED-spec.md) ｜ [DEPRECATED-tasks.md](./DEPRECATED-tasks.md) ｜ [DEPRECATED-checklist.md](./DEPRECATED-checklist.md) ｜ [DEPRECATED-implementation-plan.md](./DEPRECATED-implementation-plan.md) —— 均为「IM 机器人框架」旧定位产物，本文档（第十节）中涉及它们同步的待办视为**以弃用方式结案**

---

## 零、项目定位（一切决策的前提）

> **IrsBot（本项目）是一个本地部署的 AI Agent 应用，单用户使用，Docker 一条命令启动。**
>
> - 部署者在**自己的机器上跑一套 IrsBot**，一条命令启动
> - 用户**在浏览器里对话**，接入**自己的 API Key**（在网页端填写，不写配置文件）
> - 具备 **Skill / Tool / MCP / RAG** 等完整 Agent 能力
> - **不接入 QQ / 微信 / Telegram 等 IM 平台**，不做 IM 机器人框架
> - **网页版（多用户 / 线上部署）已拆分到另一个独立项目**，本项目不做
>
> 参考形态：类似 WorkBuddy —— 自带模型源配置、本地运行、以对话为核心。

### 0.0 最新边界决策（2026-09-16，覆盖此前所有定位描述）

| # | 决策 | 影响 |
|---|---|---|
| **D1** | **网页部署独立成另一个项目** | 本项目**单形态**（本地），Phase 16 移出，SC14 取消 |
| **D2** | **本地版是单用户** | **拆分**（2026-09-18 修订）：**多用户「运营化」降级**——不做自助注册 / 配额 / 计费；**「归属隔离」已实现且为硬约束**（`user_id` 必填 + fail closed，`ef08cc1`）。另保留 `_chat_cache` 淘汰与 `is_default` 约束两项。详见 8.4 |
| **D2.1** | **注册入口默认关闭（可由超管运行时开启）** | `POST /users/signup` 默认 403，账号由管理员在 `/admin` 创建（`41cccfd`）。**2026-09-18 修订**：不再是写死在 `.env` 的硬约束——超管在 `/admin` 页切换「单用户 / 多租户」**即时生效、无需重启**，`.env` 的 `USERS_OPEN_REGISTRATION` 降为**兜底初值**。判断依据统一走 `settings_runtime.signup_allowed()`，机制见 **8.4「配套：运行时开关」** |
| **D3** | ~~Docker 与裸机脚本都提供~~ | ➖ **已变更**：见 D4/D5 |
| **D4** | **保持 PostgreSQL + Milvus**（不换 SQLite/FAISS） | **L1/L2 阶段作废**；[local-deployment-plan.md](./local-deployment-plan.md) 整份重写为 Docker 方案 |
| **D5** | **部署形态 = Docker 一键启动**（唯一前置：装 Docker） | 交付 `compose.local.yml` + 启动脚本；放弃裸机脚本路线 |
| **D6** | **默认容器内 PG，留环境变量后门** | `POSTGRES_SERVER` 默认 `db`（容器）；可覆盖为 `host.docker.internal` 连宿主机 |
| **D7** | **全量迁移现有开发数据** | 新增数据迁移阶段；迁移前**强制备份** |

> 📄 **部署施工的完整计划见 [local-deployment-plan.md](./local-deployment-plan.md)**（阶段 D1–D7）。本文档保留全局规划视角。

### 0.1 一句话定位

| 维度 | 答案 |
|---|---|
| 产品形态 | **本地部署的 Web Agent 应用**（localhost 使用） |
| 使用方式 | 浏览器打开 localhost → 登录 → 对话 |
| 用户模型 | **单用户**（部署者本人）；保留登录以隔离同机他人访问 |
| 交互介质 | **纯 Web**，无 IM |
| 部署形态 | **Docker Compose 一键启动**（唯一前置：装 Docker） |
| 数据库 | **PostgreSQL**（容器内，可配环境变量指向外部） |
| 向量库 | **Milvus**（容器内，含 etcd + MinIO） |
| 对标 AstrBot 的 | **Agent 能力栈**（Tool / Skill / MCP / RAG / Persona / 上下文管理 / 管线），**不是**平台接入层 |

> ⚠️ **与上一版的区别**：上一版承诺「零外部依赖」（SQLite + FAISS）。**该承诺已撤回**（D4）——因为它是未经论证的假设，且改造成本占整体工作量的 70%，而收益不明确。现在的承诺是「**一条命令启动**」，前置条件是装一次 Docker。

### 0.2 定位决策表（本轮确立）

| 问题 | 答案 | 依据 |
|---|---|---|
| Web 聊天页是什么？ | **产品主体界面**，不是调试通道 | 用户通过网页对话 |
| 平台适配器要不要做？ | **不做** ➖ | 明确不接 IM |
| 插件（Star）体系要不要做？ | **不做** ➖。Skill + Tool + MCP 三层扩展已足够 | 无插件分发场景；工作量与收益不匹配 |
| 事件总线要不要做？ | **不做** ➖。FastAPI 路由即入口 | 无多平台归一化需求 |
| 多租户要不要做？ | **不做「多用户运营化」** ➖（自助注册 / 配额 / 计费）；**但「归属隔离」已实现** | 本地单用户；运营化已随网页版拆分出去，隔离则作为安全底线保留（见 8.4） |
| Provider 归属？ | 部署者自己的 Key，**网页端填写** | 单用户；**归属隔离为硬约束**（`user_id` 必填 + fail closed），不是「无需隔离」 |
| 数据库 | **PostgreSQL**（容器内；可配环境变量指向外部） | 保持已验证的技术栈（D4） |
| 向量库 | **Milvus**（容器内，含 etcd + MinIO） | 保持已验证的技术栈（D4） |
| 前端的重心？ | **对话 + 配置台并重** | 两端都直接用 |
| 高危工具默认值？ | `shell` / `file_write` **默认关闭**，设置页显式开启 | 本地 = 宿主机风险，必须显式 |
| IM 专项能力（唤醒词/群白名单/消息组件链/主动推送）？ | **不做** ➖ | 无 IM 场景 |
| 多模态？ | **降为 P2**。Web 上传图片是加分项 | 交互介质是浏览器 |
| Cron 定时任务？ | **降为 P3**。无主动推送场景 | 浏览器是拉取模型 |
| Pipeline 洋葱模型？ | **保留但要"瘦身"**：不追求 9 Stage，只做 Web 场景真正需要的 Stage | 见 Phase 12 |

### 0.3 与 AstrBot 的关系（大幅收缩）

AstrBot 的能力分三层，IrsBot 只复刻中间一层：

```
AstrBot 三层能力
├── 平台接入层 (Platform ABC + 消息事件 + UMO + 18 适配器 + 事件总线)
│     → IrsBot：完全不做 ➖
│
├── Agent 能力栈 (Pipeline + Agent 引擎 + Provider + Tool + Skill + MCP + RAG + Persona)  ★
│     → IrsBot：核心复刻目标
│
└── 生态与运维层 (Star 插件体系 + 事件钩子 + 热重载)
      → IrsBot：不做 ➖（用 Skill/Tool/MCP 替代）
```

**要复刻的骨架**：
```
├── Pipeline 管线（瘦身版，Web 场景 Stage）
├── Agent 引擎（工具循环 + 上下文管理）—— 用 LangGraph 实现，替代 AstrBot 手写循环
├── Provider 体系（多能力 + 动态加载 + 热重载）
├── 能力层：Tool / Skill / MCP / RAG / Persona
└── 上下文管理（token 计数 / 轮次截断 / 摘要压缩 / tool_call 配对修复）
```

**保留的差异化优势**（AstrBot 没有的）：
- **Docker 一条命令启动，零配置运维**——AstrBot Desktop 用 Tauri + 内置 CPython 打安装包（每个平台一个包）；IrsBot 走容器路线，**不打包运行时**，代价是用户装一次 Docker，收益是**跨平台零适配成本**（同一个 `compose.yml` 在 Windows / macOS / Linux 都能跑）
- LangGraph 状态机编排（可观测、检查点、可中断恢复）
- FastAPI 自动 OpenAPI + 前端 SDK 生成
- Alembic 规范化迁移体系
- 结构化测试基线（**294 单测 + 18 集成测试实跑通过**，见第一节）

### 0.4 本地 / 线上双形态 → **已改为单形态**

> ⚠️ **本节已被 D1 决策取代**：网页部署拆分到另一个项目，本项目只做本地。
> 保留原文以便追溯。

**原设计（已废弃）**：同一套代码，靠 `ENVIRONMENT` 分层。

**现状（D1 + D4/D5 之后）**：

| 差异项 | 本项目（本地） | 另一个项目（线上） |
|---|---|---|
| 数据库 | **PostgreSQL**（容器内 `db`，可配环境变量指向外部） | PostgreSQL（对方负责） |
| 向量库 | **Milvus**（容器内，含 etcd + MinIO） | Milvus（对方负责） |
| 注册 | **默认关闭，可由超管运行时开启**（`POST /users/signup` 默认 403；超管在 `/admin` 页切换「单用户 / 多租户」即时生效；`.env` 的 `USERS_OPEN_REGISTRATION` 只是兜底初值） | 开放 |
| 邮件 | 关闭 | 开启 |
| 工具权限 | shell / file **默认关闭**，显式开启 | 对方决定 |
| HTTPS | 无（localhost） | 对方负责 |
| 配额 | 无 | 对方负责 |

**本项目需承担的「为复用留余地」义务**（低成本但重要）：
- `Provider` 读取函数的**归属隔离已实现**（`user_id` 为必填位置参数 + 两条查找分支均过滤 + `user_id=None` 时 fail closed，`ef08cc1`）—— 由「留接口不留逻辑」**升级为默认实现**，理由见 8.4
- 保留 Alembic 迁移脚本（**本地也用它建表，不跳过**）
- 保留 `compose.yml`（线上版）不删——另一个项目可能复用
- 新增 **`app_settings` 运行时配置表 + `settings_runtime` 读取层**：超管在网页改开关、保存即生效，无需重启（见 8.4「配套：运行时开关」）。另一个项目（多用户）可直接复用这套机制，不必再把配置全部塞进 `.env`

> ⚠️ **与上一版的关键差异**：上一版要求「`GUID` 用 `TypeDecorator` 保持 PG 可用」「向量库抽象接口保留 Milvus 实现」。
> **这些义务已消失**（D4）——因为 PG 和 Milvus 现在就是**本项目的主力方案**，不需要"为将来保留"。

> **重要**：本地部署是**唯一形态**，前置条件是**装一次 Docker**。
> 详见 [local-deployment-plan.md](./local-deployment-plan.md)

### 0.5 已被历轮定位否定的判断（完整追溯）

> 保留以便追溯，避免反复摇摆。**最新一轮（D4–D7）为准。**

| 历轮判断 | 最终裁定 | 原因 |
|---|---|---|
| 「平台适配器是 P0 产品核心」（IM 轮） | **不做** ➖ | 明确不接 IM |
| 「插件体系是生态核心 P1」（IM 轮） | **不做** ➖ | 无插件分发场景 |
| 「Web 只是控制台，聊天页仅调试」（IM 轮） | **Web 是产品主体** | 用户就在网页对话 |
| 「不做多租户，降级为数据归属校验」（IM 轮） | **前半不做 ✅ / 后半反而做对了**（2026-09-18 修订） | 「不做**多用户运营化**」成立（本地单用户 + 网页版已拆分）；而「**降级为数据归属校验**」这一半**正是现在的实现**——`user_id` 必填 + fail closed。当时把两句当成一件事否掉了，是过度归并 |
| 「多租户恢复，且是 BYOK」（多用户轮） | **作为产品功能已推翻** | D2：本地单用户，无 BYOK 运营场景；**但数据层隔离已实现**（见下一行） |
| 「Provider 多用户隔离是 P0」（多用户轮） | 🔄 **不作为产品功能；代码层已实现并列为硬约束**（2026-09-18 修订） | 原判「单用户下不存在串 Key」只对**运营化多用户**成立。**归属隔离**有独立价值：① 防未来多账号 / 配置误用导致越权用他人 Key ② 本代码库将被另一个多用户项目复用 ③ 安全默认优于留白。故 `user_id` 已改为**必填位置参数** + 双分支过滤 + fail closed（`ef08cc1`） |
| 「RAG Rerank 是 P0」 | 降为 **P1** | 检索质量重要但非阻塞 |
| 「多模态是 P1（IM 用户发图）」 | 降为 **P2** | 非 IM 场景 |
| 「Cron 主动推送是 P1（IM 刚需）」 | 降为 **P3** | 无主动推送场景 |
| 「Phase 16 线上部署与工程化是 P2」 | **移出本项目** | D1：网页版独立 |
| 「本地/线上双形态靠 ENVIRONMENT 分层」 | **改为单形态** | D1 |
| 「删掉 PostgreSQL，换 SQLite + FAISS，实现零外部依赖」（本地化轮） | **🔴 已推翻（第四轮）** | D4：这是**未经论证的假设**。原判断把「exe 双击即用」等价于「必须 SQLite + FAISS」，但 AstrBot Desktop 的实证显示它用 **Tauri + 内置 CPython**，数据库是它自己的实现细节——**「跨平台免装运行时」与「用哪个数据库」是两件独立的事**。改造成本占整体工作量 70%，收益不明确 |
| 「`GUID` TypeDecorator 是本地化必需」（本地化轮） | **不再必需** | D4：PostgreSQL 保留为唯一数据库，模型层用 PG 原生 `UUID` 即可。做 `TypeDecorator` 只剩「为另一个项目留余地」的价值，**不是 P0** |
| 「数据全部落在 `.irsbot/`，删除即卸载」（本地化轮） | **改为命名卷** | D5：Docker 下用 `irsbot_pgdata` 等命名卷，卸载用 `docker compose down -v` |

---

## 一、总体进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 项目基础架构搭建 | ✅ 完成 |
| Phase 2 | 对话管理系统 | ✅ 完成 |
| Phase 3 | Provider 系统 (LangChain 适配层) | 🔶 Chat + Embedding 完成，**归属隔离已实现**；**缺缓存淘汰**（单用户下同样存在，见 8.4） |
| Phase 4 | Tool 系统 | ✅ 完成（5 个内置工具） |
| Phase 5 | MCP 协议集成 | ✅ 完成（含 REST API + 19 测试） |
| Phase 6 | Skill 系统 | ✅ 完成（含 REST API + 13 测试） |
| Phase 7 | RAG 知识库系统 | 🔶 主链路完成（**9 项集成测试已实跑通过**），缺 Rerank / 多格式解析 |
| Phase 8 | Agent 引擎 (LangGraph) | 🔶 主链路完成，缺重试/统计/会话锁 |
| Phase 9 | Pipeline 架构 | 🔶 4 Stage，**需按 Web 场景重新定义范围** |
| Phase 10 | Web 聊天对话功能 | 🔶 10.1/10.2/10.4 完成，10.3/10.5 UI 待做 |
| **Phase D1** | **Compose 本地化改造**（剥离 Traefik/域名/adminer/HTTPS；补全 Milvus 全家桶；前端改后端托管） | ✅ **已完成**（2026-09-17 实机验收，D1.1–D1.5，详见 PROGRESS.md；唯余 D1.3c 分发优化非阻塞）｜ **P0** |
| **Phase D2** | **一键启动脚本**（Windows `.cmd` / macOS·Linux `.sh` 双份） | ✅ **已完成**（2026-09-17 00:26；含缺 `.env` 自动生成 + health 轮询 3 分钟）｜ **P0** |
| **Phase D3** | **首次启动引导**（SECRET_KEY 落盘 + 随机管理员密码 + 打印地址） | ✅ **已完成**（2026-09-17 实机验收）｜ **P0** |
| **Phase D4** | **端到端验证**（干净机器跑通全功能；测试矩阵；README） | ✅ **已完成**（D1.3a/D1.3/D1.4 实机验收；「干净机器复验」部分移交 **D8 可分发** 待做）｜ **P0** |
| **Phase D5** | **数据迁移**（本机开发数据 → 容器；**最高风险，强制备份**） | ✅ **已完成 —— 判定不迁移**（盘点实证：本机库系 pytest 清空后的陈旧副本，**容器库为权威库**；真实资产已备份 `backups/20260917_095030/`；风险由「最高」下调为低）｜ **P0** |
| **Phase D6** | **工具权限开关**（`shell` / `file_write` 默认关闭 + 路径白名单） | ✅ **已完成**（`ENABLE_SHELL`/`ENABLE_FILE_WRITE` 默认 False + `FILE_WRITE_ROOTS` 白名单）｜ **P0** |
| **Phase D7** | **交付**（交付说明 / 备份恢复文档 / 卸载说明） | ✅ **已完成**（`docs/OPERATIONS.md` 运维手册 + `scripts/backup.ps1/.cmd` 一键备份）｜ P0 |
| **Phase 12** | 管线完整化 + 上下文管理补强 | ⬜ 未开始 ｜ P1 |
| **Phase 14** | Agent 能力补强（Rerank / Persona / 统计 / 多模态） | ⬜ 未开始 ｜ P1–P2 |
| **Phase 15** | 前端完善（对话体验 + 配置台管理页） | ⬜ 未开始 ｜ P1 |
| ~~Phase 11~~ | ~~Provider 多用户化（BYOK）~~ | ➖ **降级**：仅保留 cache 淘汰 + `is_default` 约束（D2） |
| ~~Phase 13~~ | ~~本地部署免依赖~~ | ➖ **作废**，由 **D1–D7** 取代（D4/D5：保持技术栈，走 Docker） |
| ~~Phase L1~~ | ~~数据库方言无关（SQLite 支持）~~ | ➖ **作废**（D4） |
| ~~Phase L2~~ | ~~向量库可插拔（FAISS 默认）~~ | ➖ **作废**（D4） |
| ~~Phase L3 / L3.5 / L4~~ | ~~一键启动 / 工具权限 / 验证交付~~ | 🔄 **重编号为 D2–D7** |
| ~~Phase 16~~ | ~~线上部署与工程化~~ | ➖ **移出本项目**（D1，网页版独立） |

### 1.1 测试基线（✅ 本轮已实跑，不再是估算）

| 类别 | 数量 | 状态 | 说明 |
|---|---|---|---|
| **单元测试** | 294 | ✅ 全过 | 含 13 个 Provider 测试 |
| **集成测试** | 18 | ✅ **实跑通过**（`90.93s`） | 此前一直被**默认跳过**——见下方警示 |

> ⚠️ **本轮最重要的发现**：集成测试文件带 `pytestmark = pytest.mark.integration`（如 `tests/core/knowledge_base/test_vec_store.py:15`），**默认被跳过**。这就是「跑了测试但不知道真实情况」的根因。
> 手动放行后实跑结果：
> - `test_vec_store.py`：**`9 passed, 9 warnings in 60.35s`**（真连 Milvus，真调 Embedding API）
> - 全量集成：**`18 passed, 294 deselected, 9 warnings in 90.93s`**
> - 覆盖：RAG 向量检索 9 项、Agent 真实 LLM 循环 2 项、WS 流式 6 项、工具/Skill/长对话 1 项
>
> **结论**：RAG 链路**不是"看起来能跑"，是"确实跑通了"**——向量写入、检索、RRF 混合排序全部真实经过 Milvus 与外部 Embedding 服务。这条基线要在 D4 重跑一次作为回归。

测试代码在仓库根 `tests/`（非 `backend/tests/`）。
> ~~新增 `tests/core/db/test_uuid_portability.py`~~ —— 该验证测试已按用户要求删除，且随 D4 **整体失去必要性**（不再做方言适配）。

---

## 二、已完成阶段详细清单

### Phase 1: 项目基础架构搭建 ✅

- [x] **1.0 环境准备**
  - uv 管理依赖，`backend/.venv` 唯一环境，全部命令 `uv run` 前缀（规则固化在 `.trae/rules/uv_python_env.md`）
  - Milvus 基础设施（etcd + MinIO + Milvus）Docker Compose 可启动
  - 注意：langgraph 实际版本超出 checklist 锁定范围（checklist 写 `<0.3.0`，实际已升级），以 `uv.lock` 为准
- [x] **1.1 uv 依赖与配置**
  - pyproject.toml 含 optional-dependencies（langchain/rag/mcp/all）
  - Settings 覆盖 LLM API Key / Agent 参数 / RAG 参数 / MCP 参数 / Skill 参数，`.env.example` 有模板
  - pytest-asyncio 版本约束已修复为 `>=0.23.0,<1.0.0`（曾因依赖漂移导致全局环境覆盖 venv，教训已写入项目记忆：禁止裸 python/pip）
- [x] **1.2 数据模型**
  - `backend/app/core/db/models.py`：9 个业务模型（ProviderConfig、Conversation、Message、KnowledgeBase、Document、MCPServer、Skill、Persona、AgentRun），中文注释已标准化
  - Alembic 迁移应用到 PostgreSQL；业务模型已统一迁入 SQLModel.metadata
- [x] **1.3 Agent CRUD**：每模型 CRUD 函数，支持分页 + 数据归属隔离

### Phase 2: 对话管理系统 ✅

- [x] **2.1 对话管理器**（`backend/app/core/agent/conversation.py`）
  - ConversationManager CRUD；`add_message()` 持久化用户/AI 消息
  - `get_langchain_messages()`：DB JSON → LangChain Message 转换
  - `get_context_messages()`：token 限制截断；查询带归属校验（`one_or_none()` fail-fast 风格）
- [x] **2.2 上下文管理**：ContextConfig + ConversationSummaryBuffer 摘要压缩，长对话集成测试通过

### Phase 3: Provider 系统 🔶

- [x] **3.1 Provider 管理器**（`backend/app/core/agent/provider.py`）
  - `get_chat_model()` / `get_embedding_model()` 动态创建；无默认 Provider 时 raise RuntimeError 明确报错（设计决策：显式失败优于回退 .env——回退会导致实际使用部署者自己的 key，用户以为在用自己配置的）
  - chat_with_fallback() Fallback 链、reload_config() 热重载、Provider CRUD
  - **新增（Task 10.5）**：`list_providers` / `create_provider` / `update_provider` / `delete_provider` / `clear_other_defaults`（默认互斥）
- [x] **3.2 模型来源配置**：MODEL_SOURCES 预定义 OpenAI/Anthropic/Gemini 等来源
- [ ] **3.3 Rerank 能力**（缺失，见 Phase 14.1）
- [ ] **3.4 STT / TTS 能力**（缺失，按需 ➖ 可跳过）
- [ ] **3.5 缓存淘汰缺失（本轮新识别，P0）**
  - `_chat_cache` / `_embed_cache` 是**纯 dict，永不淘汰**（`provider.py:142-143`）→ 长期运行内存只增不减
  - **与用户数无关**：单用户下同样存在（原 Phase 11 的**多用户运营化**部分已随 D2 取消；**归属隔离不在取消之列**，已实现，见 8.4）
  - 计划：加 LRU 或 TTL 上限
  - 相关：`get_chat_model()` / `get_embedding_model()` 的 `user_id` 已是**必填位置参数**（无默认值），两条查找分支均带 `user_id` 过滤，缓存键含 `user_id`，`user_id=None` 时 **fail closed** —— **逻辑已实现**（`ef08cc1`），不再是「留接口不留逻辑」
  - 追加审计点：`is_default` 的互斥目前只在应用层（`clear_other_defaults`），**DB 无唯一约束** → 并发/异常下可能出现两个默认，需部分唯一索引兜底

### Phase 4: Tool 系统 ✅

- [x] **4.1 工具注册中心**：ToolRegistry 单例 + `@register_tool` 装饰器（= @tool + 自动注册）
- [x] **4.2 内置工具集**：web_search / file_read / file_write / shell_execute / knowledge_base_query
- [x] **4.3 工具执行器**：执行包装 + 超时 + 错误处理；ToolMessage 与 tool_call_id 配对规则已固化到项目记忆
- [ ] **4.4 工具权限开关**（本轮新识别，P0）：`shell_execute` / `file_write` 无开关，**默认就是可用的**。走 Docker 后风险面缩小（容器隔离），但容器**仍可能挂载工作目录**，不应默认开放 → 见 **D6**

### Phase 5: MCP 协议集成 ✅

- [x] **5.1 MCP 客户端**：mcp SDK 原生客户端，SSE / stdio / Streamable HTTP，list_tools + call_tool + 自动重连
- [x] **5.2 MCP 安全**：白名单/黑名单/Shell 元字符/内联代码检测
- [x] **5.3 MCP → LangChain Tool 桥接**：MCP tool 包装为 BaseTool 批量注册
- [x] **5.4 MCP REST API**（`backend/app/api/routes/agent.py`，6 端点）：`POST/GET /agent/mcp-servers`、`GET/PATCH/DELETE /agent/mcp-servers/{id}`、`POST /agent/mcp-servers/{id}/connect`

### Phase 6: Skill 系统 ✅

- [x] **6.1 Skill 管理器**：scan_skills / build_skills_prompt / install_skill，渐进式披露
  - 硬性约束：Skill 名 3-64 字符；SKILL.md ≤1MB；上传临时文件唯一命名防并发冲突
- [x] **6.2 Skill 安全**：名称正则/路径穿越/ZIP 安全校验
- [x] **6.3 Skill REST API**（5 端点）：`GET /agent/skills`、`GET/DELETE /agent/skills/{name}`、`POST /agent/skills/scan`、`POST /agent/skills/install`
  - 安装采用**原子替换**（`copytree` 到 `.tmp_<name>` → `os.replace`）

### Phase 7: RAG 知识库系统 🔶

- [x] **7.1 文档处理**：LangChain DocumentLoaders（PyPDFLoader 等）+ TextSplitters
- [x] **7.2 向量存储和检索**：LangChain Milvus 封装（**已验证：9 项集成测试实跑通过**），BM25 + RRF 混合检索
- [x] **7.3 知识库管理**：upload → 解析 → 分块 → Embedding → Milvus 全链路；query() + get_retrieval_context()
- [x] **7.4 REST API**（`backend/app/api/routes/knowledge_base.py`）
- [ ] **7.5 Rerank 段**（缺失，见 14.1）
- [ ] **7.6 多格式解析器 / 聚合模式**（缺失，见 14.2）
- [x] **7.7 向量库 = Milvus（最终选定，不再可插拔）**：D4 确认保持 Milvus。~~原计划做「可插拔 + FAISS 默认」~~ **已作废** —— 那不是 P0，是"为一个被推翻的目标付出的成本"

### Phase 8: Agent 引擎 (LangGraph) 🔶

- [x] **8.1 状态图**：`Annotated[list[AnyMessage], add_messages]`（硬性约束）；inject_knowledge → inject_skills → invoke_llm → call_tools → END + should_continue 路由
- [x] **8.2 节点函数**：RAG 注入、`bind_tools() + ainvoke()`、工具执行追加 ToolMessage
- [x] **8.3 Agent Runner**：`astream_events()` 流式 AsyncGenerator；run / run_sync / interrupt
- [x] **8.4 检查点持久化**：SQLAlchemyStore → PostgreSQL
- [x] **8.5 端到端**：Mock LLM + Tool 完整 ReAct 循环验证
- [ ] **8.6 补强项**（见 Phase 12.3 / 14.3）

### Phase 9: Pipeline 架构 🔶（4/9 Stage）

- [x] **9.1 基础框架**：Stage ABC + PipelineContext + PipelineScheduler
- [x] **9.2 Pipeline 阶段**：RateLimit / PreProcess / Process / PostProcess
  - 现状：`Stage.process()` 返回 `PipelineContext | None`，Scheduler 是普通 `for` 循环 → **不支持洋葱模型**
  - `RateLimitStage` 仅挂 REST chat 路由，WS 通道未接
- [ ] **9.3 范围重定义**（本轮）：不再追求 9 Stage，改为按 Web 场景裁剪，见 Phase 12.1

---

## 三、当前阶段详情（Phase 10 收尾）

| 任务 | 状态 | 说明 |
|---|---|---|
| 10.1 WS API | ✅ | `/agent/chat/ws/{conversation_id}`，token 查询参数鉴权，astream_events 流式转发 |
| 10.2 前端聊天页 | ✅ | 千问风格 UI，react-markdown 渲染，useAgentChat 自动重连 |
| 10.3 前端管理页 | 🔶 | Settings 页含「模型源」Tab；KB/MCP/Skill/Persona 管理页未做 |
| 10.4 上下文记忆 | ✅ | 归属校验 + 双向持久化 + WS `history` 下行 + 前端恢复；协议文档已更新；三项集成测试通过 |
| 10.5 Provider 管理 | 🔶 | 代码全部完成，UI 实测未做 |

### Task 10.5 已交付内容
- **后端**（`backend/app/api/routes/providers.py`）：GET/POST `/api/v1/providers`、PATCH/DELETE `/api/v1/providers/{id}`，归属校验 404 防 IDOR，默认 Provider 互斥
- **加密**（`backend/app/utils/crypto.py`）：api_key AES-256-GCM 加密落库（`enc:v1:` 前缀），历史明文平滑兼容；接入 create/update/seed 写入点与 `get_chat_model` 读取点；`SECRET_KEY` 已换强随机
- **前端**：`useProviders.ts`（React Query 自动失效缓存）+ `ProviderSettings.tsx`（列表/新增弹窗/设默认/删除确认/空状态引导），OpenAPI SDK 重新生成
- **入口**：侧边栏新增「设置」菜单项
- **测试**：4 端点 + 互斥验收 + 加密落库 + IDOR 防护，共 13 个

### 本轮附带完成（超出计划）
- 前端全站文案中文化（32 个文件），Logo/标题改为 IrsBot
- Playwright e2e 断言同步中文化（8 个文件，169 处）
- 移除空顶栏、页脚、TanStack 调试工具；侧边栏收起态展开按钮全页面通用
- 数据库业务模型迁移 SQLModel.metadata
- git 提交按主题拆分（feat/refactor/test/chore），工作区干净

### Task 10.5 验收清单（关单前）
- [ ] UI 实测：设置页新增一条 Provider（假 key 即可）
- [ ] 落库验证：`providerconfig.api_key` 显示 `enc:v1:` 密文
  ```powershell
  cd backend
  uv run python -c "from app.core.db.engine import engine; from sqlmodel import Session, select; from app.core.db.models import ProviderConfig; [print(r.name, '->', r.api_key[:20]) for r in Session(engine).exec(select(ProviderConfig)).all()]"
  ```
- [ ] 「设为默认」互斥验证：两条 Provider 依次设默认，只有一条带默认徽章
- [ ] 「删除」验证：删除后列表刷新；删除默认后无默认（UI 引导重设）
- [ ] 闭环验证：聊天页发消息，确认走默认 Provider 而非 .env

---

## 四、Success Criteria

| 编号 | 标准 | 状态 |
|---|---|---|
| SC1 | 端到端对话（LangGraph ReAct 完整循环） | ✅ |
| SC2 | ≥2 种 LLM 切换 | ✅ |
| SC2.1 | Provider 便捷切换 REST API + 前端 | 🔶 代码完成，UI 实测待做 |
| SC3 | ≥3 种内置工具 | ✅（5 种） |
| SC4 | MCP Server 连接 + ToolBridge 调用 | ✅ |
| SC5 | TextSplitter + Milvus + 检索返回 | ✅ |
| SC6 | Skill 安装 + Agent 读取 SKILL.md | ✅ |
| SC7 | WebUI 对话 + 管理页面 | 🔶 对话 ✅，管理页仅 Provider |
| SC9 | Alembic 迁移覆盖双 metadata | ✅ |
| SC10 | WebSocket 断线自动重连 | ✅ |
| **SC8** | **Web 场景所需 Stage 全部生效**（范围已从「9 Stage 全实现」重定义） | ⬜ 见 Phase 12 |
| ~~L1~~ | ~~无需 PostgreSQL：不启任何数据库进程即可完成全流程~~ | ➖ **作废**（D4） |
| ~~L2~~ | ~~无需 Milvus：不启 etcd/MinIO/Milvus 即可建库并检索~~ | ➖ **作废**（D4） |
| ~~L7~~ | ~~全量单测在本地模式（SQLite + FAISS）下通过~~ | 🔄 **改为 D4**：全量测试在**容器环境**下通过 |
| ~~L8~~ | ~~数据全部落在 `.irsbot/`，删除即完全卸载~~ | 🔄 **改为 D7**：`docker compose down -v` 即完全卸载 |
| **D1** | ~~一条命令起全栈：6 个服务（db/etcd/minio/milvus/backend/frontend）~~ → **实证修正：3 个服务**（db/milvus/backend；Milvus 单容器内嵌 etcd，**无独立 etcd/minio**；前端由 backend 托管，**无独立 frontend 容器**）全部 healthy | ✅ **达成**（D1.2/D1.3 实机验收） |
| **D2** | **`http://localhost:8000` 可直接对话**：浏览器打开即用，**无需手动建库、无需改任何配置文件** | ✅ **达成**（backend 托管前端 + SPA fallback；uvicorn 8001 验收 6/6 + 容器链路闭环） |
| **D3** | **前端单端口**：前端由后端托管静态产物，**不再需要 5173 dev server** | ✅ **达成**（D1.3a） |
| **D4** | **首次启动零配置**：自动生成 SECRET_KEY **并落盘**、自动建表、自动建管理员、终端**打印随机密码与访问地址** | ✅ **达成**（D3） |
| **D5** | **重启不丢登录态**：`docker compose restart` 后已登录会话仍然有效（验证 SECRET_KEY 未变） | ✅ **达成**（D3 SECRET_KEY 落盘） |
| **D6** | **`shell` / `file_write` 工具默认关闭**，设置页可显式开启 | ✅ **达成**（D6；⚠️ 设置页显式开启的 UI 未建，当前改 `.env` 生效） |
| **D7** | ~~开发数据完整迁移：本机 126 会话 / 108 消息 / 22 知识库…~~ → **实证推翻后改判**：盘点发现「22 KB/126 会话」是 pytest 残留虚高，真实资产仅 5 类；本机库系被 pytest 清空的陈旧副本，**判定不迁移，容器库为权威库**；真实资产已全量备份 | ✅ **以「不迁移 + 备份」结案**（D5） |
| **D8** | **可分发**：把仓库拷给他人，对方装好 Docker 后同样一条命令跑通（验证无本机隐式依赖） | ⬜ **待做**（需干净机器/他人环境实测；属下一里程碑） |
| **D9** | **测试基线不退化**：294 单测 + 18 集成测试在容器环境下仍全过 | 🔶 **部分达成**（294+18 本机实跑全过；容器环境内复跑待验） |
| **D10** | **无自助注册入口**：匿名调用 `POST /users/signup` 必须被拒（403），且响应不泄露账号是否存在 | ✅ **达成并升级**（2026-09-18 实机验证）：默认（单用户模式）→ 403 + 固定话术；已存在 / 不存在邮箱的**响应逐字节一致**（防枚举）；闸门置于查重之前。**现已由运行时开关控制**（超管可在 `/admin` 开启「多租户」，见 8.4「配套：运行时开关」），但**默认仍为关闭**，且两种模式下防枚举断言均成立 |
| **SC11** | **数据归属隔离：A 用户绝不会用到 B 用户的 Key** | ✅ **达成（2026-09-18 恢复）**：`get_chat_model` / `get_embedding_model` 的 `user_id` 为必填位置参数，两条查找分支均带 `user_id` 过滤，缓存键含 `user_id`，`user_id=None` 时 fail closed；含多租户回归测试。原「取消」仅指 **BYOK 作为产品能力**（自助注册 / 配额）不做 |
| ~~SC12~~ | ~~本地单机零外部依赖可跑通全功能~~ | 🔄 **重写为 D1–D9**（承诺从「零依赖」降为「一条命令」） |
| ~~SC13~~ | ~~用户可在网页端自助完成全流程~~ | 🔄 **部分保留**：本地单用户仍需「填 Key → 对话 → 管 KB/MCP/Skill」闭环（见 Phase 15） |
| ~~SC14~~ | ~~同一套代码可切换本地/线上两种部署形态~~ | ➖ **取消**（D1：单形态） |
| ~~SC15~~ | ~~IM 平台接入~~ | ➖ **已取消**（不做 IM） |
| ~~SC16~~ | ~~插件体系可用~~ | ➖ **已取消**（不做插件） |

> **D1–D10 是本项目「本地可用」的验收标准**，优先级等同 P0。详见 [local-deployment-plan.md](./local-deployment-plan.md)。
> SC8 由「9 Stage 全实现」改为「Web 场景所需 Stage 全部生效」——原标准源于 AstrBot 的 IM 管线，与当前定位不符。
>
> 🔄 **SC11 已从「取消」改回「达成」**（2026-09-18）：取消的应是 **BYOK 运营化**（自助注册 / 配额），而不是**数据归属隔离**本身。二者此前被当成一件事处理，属**过度归并**——已实现的隔离见 `ef08cc1`。
>
> ⚠️ **承诺的降级要说清楚**：原 SC12 写的是「**零外部依赖**」，现在是「**一条命令启动（前置：装 Docker）**」。
> 这不是文字游戏——前者要求消灭所有外部进程，后者只要求消除**手工配置**。**后者才是真正被用户感知到的那个**：用户不在乎后台有没有 PostgreSQL，只在乎要不要自己敲 20 条命令。

---

## 五、已知问题 / 待办

### 5.1 P0 级（阻塞产品可用）

> ⚠️ **原 #1「本地部署硬依赖外部服务」已删除。**
> 它不再是「问题」，而是**方案本身**（D4/D5）。保留它会造成严重误导——读文档的人会以为要去消灭 PostgreSQL 和 Milvus。
> **正确的表述**：外部服务存在不是问题，**手工配置它们**才是问题。而这个问题的解法是 Docker Compose，不是删数据库。

1. **`compose.yml` 无法本地直接运行**：线上版依赖 `${DOMAIN}` / `${STACK_NAME}` / Traefik external 网络（`compose.yml:174` `external: true`）/ Let's Encrypt 证书 → 需完整改造成本地版。→ **D1**
2. **shell / file 工具无权限开关**：`shell_execute` / `file_write` 当前默认可用。Docker 隔离降低了风险，但**容器仍挂载了工作目录与 Docker socket 的可能性**，不应默认开放。→ **D6**
3. **`SECRET_KEY` 每次重启变化**：`config.py:34` 是 `secrets.token_urlsafe(32)` 默认值 → 重启后**所有已签发 JWT 失效，登录态丢失**。容器环境下每次 `up` 都重新生成，问题比裸机更严重。→ **D3 必须落盘**
4. **`FIRST_SUPERUSER_PASSWORD` 默认 `changethis`**：`config.py:160` 仅发 `UserWarning`。首次启动引导须**随机生成并打印**。→ **D3**
5. **集成测试默认被跳过**：`pytestmark = pytest.mark.integration` 导致 18 个真实链路测试**不进默认流水线**，形成"以为测了其实没测"的盲区。→ **D4.2 纳入常规验证**
6. **数据迁移路径未验证**：本机 PG 存在版本可能与容器内 `postgres:18` 不一致；Milvus 向量数据能否跨实例迁移**尚未调研**（M1）。→ **D5 前置调研，先于一切迁移动作**

### 5.2 P1 级（影响体验）

7. **e2e 测试未实跑**：断言已中文化但没跑过 `npx playwright test`（需前后端 + mailcatcher 环境）
8. **管理页缺口**：KB / MCP / Skill / Persona 管理页未做，用户无法自助配置
9. **后端 API 错误消息为英文**：中文化需改后端
10. **`tasks.md`/`checklist.md` 勾选状态未维护**：复选框与实际进度不符
11. **侧边栏 Logo 仍是 FastAPI**：SVG 文字烧死在 `frontend/public/assets/images/fastapi-logo.svg`
12. **前端是双端口 dev server**（5173 + 8000）：Docker 单容器需改为前端构建为静态产物由后端托管 → **D1.3**
13. **SPA 路由 fallback 必须补**：前端改由后端托管后，任何未匹配路径须回退 `index.html`，否则**刷新页面即 404**。这是单容器方案最易漏的一步 → **D1.3**
14. **开发数据含大量测试空壳**：22 个知识库中仅 2 个有文档。迁移时需区分「真实资产」与「测试残留」→ **D5.1 迁移前盘点**

### 5.3 P2 级（工程卫生）

15. **`_chat_cache` / `_embed_cache` 无界增长**：纯 dict 永不淘汰（`provider.py:142`），长期运行内存只增不减 → 需加 LRU/TTL（**与用户数无关**，故保留）
16. **`is_default` 无 DB 级唯一约束**：单用户下同样可能出现两条默认（并发/异常）→ 需部分唯一索引兜底（**与用户数无关**，故保留）
17. **Persona 模型存在但零实现**：已建表、已进 CRUD，但无 Manager / 无注入 / 无 API / 无 UI
18. **AgentRun 模型存在但未采集**：无 token 用量、耗时、工具调用次数写入点
19. **WS 通道未接 Pipeline**：`agent_ws.py` 直接调 `agent.stream()`，绕过 `PipelineScheduler`，RateLimit 在 WS 下失效
20. **LangGraph 检查点实际未启用**：`graph.py:54` 的 `create_compiled_agent_graph()` 只是 `graph.compile()`，**未传 checkpointer**。文档中 Phase 8.4 写的「SQLAlchemyStore → PostgreSQL」需核实澄清（若确实未启用，应修正文档而非宣称已完成）
21. **前端 git 换行符混乱**：CRLF/LF 混用，可加 `.gitattributes` 统一
22. **`spec.md` 定位已过期**：未覆盖「本地单用户 + Docker 交付」，**待同步**（见 10.1）
23. **Milvus `auto_id` 警告**：`vec_store.py:49-53` 构造 `MilvusVectorStore` 未传 ids → 触发 `No ids provided and auto_id is False. Setting auto_id to True automatically.` 功能正常，但配置不干净
24. **psycopg 连接泄漏**：测试中出现 `ResourceWarning: <psycopg.Connection object> was deleted while still open` → 连接未显式关闭，长期运行可能耗尽连接池

---

## 六、AstrBot 对标能力矩阵

> 详细实现说明见 [astrbot-architecture.md](./astrbot-architecture.md)
> 图例：✅ 已完成 ｜ 🔶 部分完成 ｜ ⬜ 未开始 ｜ ➖ 有意不采用
>
> **本轮定位变更后，本矩阵已按「只对标 Agent 能力栈」收缩**。原表里的平台适配器、消息事件、事件总线、插件体系等能力整体降级为「不做」。

### 6.1 核心对标区（Agent 能力栈 — 复刻目标）

| 能力域 | AstrBot 实现 | IrsBot 现状 | 本轮优先级 |
|---|---|---|---|
| **Provider 体系** | 5 类能力 + 装饰器注册 + 动态 import | 🔶 Chat + Embedding；**归属隔离已实现**（`user_id` 必填 + 双分支过滤 + 缓存键隔离 + fail closed） | P0（cache 淘汰）｜P1（Rerank） |
| **Tool 系统** | computer/message/cron/KB/web_search | 🔶 5 个，**缺权限开关** | **P0**（权限开关，见 **D6**）｜P2（新增工具） |
| **MCP** | stdio/sse/streamable_http + 安全 + 桥接 | ✅ 全套 | — |
| **Skill** | 4 种来源 + 渐进式披露 + 沙箱同步 | 🔶 local + 披露 + 安全 | P2 |
| **RAG** | 5 解析器 + 3 分块器 + 稠密/稀疏/RRF/Rerank | ✅ **混合检索链路已实跑验证**（9 项集成测试通过），缺 Rerank | P1（Rerank） |
| **Agent 引擎** | `ToolLoopAgentRunner` 手写 ReAct | ✅ LangGraph StateGraph（差异化优势） | 保留，见 6.3 |
| **上下文管理** | token 计数 + 轮次截断 + 摘要 + tool_call 配对修复 | 🔶 仅摘要压缩 | P1 |
| **Pipeline 管线** | 9 Stage 洋葱模型 | 🔶 4 Stage 顺序循环，**范围需按 Web 场景重定义** | P1 |
| **Persona** | `PersonaManager` + 会话级绑定 | ⬜ 仅数据模型 | P2 |
| **内容安全审核** | 关键词 + 百度 AIP 双策略 | ⬜ 无 | P2 |
| **Agent 统计** | `AgentStats`（token/耗时/TTFT） | ⬜ 无 | P2 |
| **多模态** | `ContentPart`: Text/Think/ImageURL/AudioURL | ⬜ 仅纯文本 | P2（Web 上传图片加分项） |
| **Cron 定时任务** | `CronJobManager` + `cron_tools` | ⬜ 无 | P3（无主动推送场景） |
| **STT / TTS** | 4 STT + 12 TTS 实现 | ⬜ 无 | P3（按需） |

### 6.2 明确不采用区 ➖（本轮定位收缩）

> 这些是 AstrBot 的强项，但在「**本地单用户 Agent 应用，走浏览器、不接 IM**」的定位下**整体不做**。保留本节是为了避免后续反复讨论。

| 能力 | AstrBot 实现 | 不做的理由 |
|---|---|---|
| **平台适配器抽象** | `Platform(ABC)` + `PlatformManager` + 18 平台 | 无 IM 接入需求 |
| **消息事件模型** | `AstrBotMessage` + `AstrMessageEvent` + UMO | 无跨平台消息抽象需求 |
| **消息组件链** | `Plain/Image/At/Reply/File/Record/...` | Web 端用 JSON/Markdown，不需要平台消息段模型 |
| **事件总线** | `asyncio.Queue` + 按 UMO 路由 | FastAPI 路由即入口，无归一化需求 |
| **唤醒词 / @ 触发** | `WakingCheckStage` | 无群聊场景 |
| **群白名单 / 会话开关** | `WhitelistCheckStage` / `SessionStatusCheckStage` | 无群聊场景 |
| **会话串行化** | `session_lock_manager.acquire_lock(umo)` | Web 端为请求-响应模型；同一会话并发由前端约束即可（可选加锁，P3） |
| **流式分段回复** | `ResultDecorateStage` 分段 + 间隔发送 | 无 IM 消息长度限制 |
| **文件 token 服务** | `api/file/<token>` 对外 URL | Web 端可直接带鉴权访问 |
| **主动消息推送** | `Context.send_message` + Cron | 浏览器是拉取模型 |
| **插件 (Star) 体系** | 目录约定 + 注册 API + 17 事件钩子 + 热重载 | 无插件分发场景；Skill/Tool/MCP 已覆盖扩展需求 |
| **事件钩子** | 17 个 `EventType` 切点 | 随插件体系一并取消（可留 2–3 个内部钩子，见 Phase 12.4） |
| **T2I（文本转图片）** | 渲染长文本为图 | Web 端 Markdown 渲染已解决 |
| **Computer Use / 沙箱** | boxlite / cua / shipyard | 与 shell 工具职责重叠，安全面大 |
| **热更新器** | `updator.py` | 用 `docker compose pull && up -d` 替代 |
| **18 种平台适配器** | — | 无 IM 需求 |
| **i18n 多语言** | 多语言包 | 保持中文优先 |
| **API Key 作用域化 Open API** | — | 无对外平台化需求（用户登录本身已鉴权） |

### 6.3 Agent 引擎补强项

| 能力 | AstrBot | IrsBot | 本轮优先级 |
|---|---|---|---|
| 最大工具轮数 | `max_step=30`，达上限后 `func_tool=None` + 总结提示 | ✅ 15 步上限（可提到 30） | P2 |
| 空输出重试 | tenacity `AsyncRetrying` 重试 3 次 | ⬜ 无 | P1 |
| 中断 | `_abort_signal` + `request_stop()` | ✅ interrupt | — |
| 工具调用超时 | `run_context.tool_call_timeout = 120s` | 🔶 执行器有超时，未统一 | P1 |
| 工具结果落盘 | >27500 tokens 自动落盘 | ⬜ 无 | P3 |
| 上下文注入装饰 | persona / skills / KB / 时间 / web 搜索按需 | 🔶 inject_knowledge + inject_skills | P2（补 persona/时间） |
| 上下文压缩 | TruncateByTurns / LLMSummary + token 计数 + 轮次切分 + tool_call 配对修复 | 🔶 ConversationSummaryBuffer | **P1** |
| 子代理 | `HandoffTool` + `SubAgentOrchestrator` | ⬜ 无 | P3 |
| Agent 统计 | `AgentStats`（token/耗时/TTFT） | ⬜ 无 | P2 |

### 6.4 既有优势（保留）

| 优势 | 说明 | D1/D2 后是否仍成立 |
|---|---|---|
| LangGraph 状态机编排 | 相对 AstrBot 手写循环：可观测、可持久化检查点、可中断恢复 | ✅ 核心优势 |
| 自动 OpenAPI + SDK 生成 | FastAPI 自动产出前端 `client/sdk.gen.ts`，AstrBot 手写 API 层 | ✅ |
| 规范化迁移体系 | Alembic + SQLModel，AstrBot 用自研 `migra_*` 脚本 | ✅（PostgreSQL，**本项目也用 Alembic 建表**） |
| 结构化测试基线 | 294 单测 + 18 集成测试实跑，AstrBot 测试覆盖较薄 | ✅ |
| api_key 加密落库 | AES-256-GCM + 历史明文兼容，AstrBot 明文存 JSON | ✅ 仍成立（本地也可能有人共用机器） |
| ~~多用户 + BYOK~~ | ~~AstrBot 是单用户单实例；IrsBot 一个部署服务多用户，各自带 Key~~ | ➖ **已移出**：单用户（D2）；多用户能力移交另一个项目 |

> **注意**：本项目现在是**单用户**。原「多用户 + BYOK 是核心差异化」的表述已作废 —— 差异化现在落在「**Docker 一条命令交付 + LangGraph 编排 + 规范工程化 + 真实测试基线**」这四项上。

---

## 七、已完成 / 待完成事项梳理

### 7.1 已完成（可关单）

| 模块 | 交付物 | 证据 |
|---|---|---|
| Phase 1–2 基础 + 对话管理 | 9 模型 / CRUD / ConversationManager / 上下文摘要 | 294 单测 |
| Phase 3 Provider (Chat/Embedding) | Manager + Fallback + 热重载 + CRUD + 加密 | `tests/provider/` 13 项 |
| Phase 4 Tool | ToolRegistry + 5 内置工具 + 执行器 | `tests/tool/` |
| Phase 5 MCP | 客户端 + 安全 + 桥接 + 6 REST 端点 | `tests/mcp_client/` + `test_agent_mcp.py` |
| Phase 6 Skill | Manager + Parser + Security + 5 REST 端点 | `test_agent_skills*.py` |
| Phase 7 RAG 主链路 | Parsers + Chunkers + Milvus + BM25/RRF + REST | `tests/core/knowledge_base/` |
| Phase 8 Agent 主链路 | StateGraph + 节点 + Runner + 检查点 | `test_agent_graph.py` |
| Phase 10.1/10.2/10.4 | WS API + 调试聊天页 + 上下文记忆 | `test_agent_ws*.py` |

### 7.2 部分完成

| 模块 | 已完成 | 待完成 | 处置 |
|---|---|---|---|
| Phase 3 Provider | Chat + Embedding + CRUD + 加密 | **缓存淘汰**（P0，与用户数无关）/ Rerank（P1）/ STT-TTS（P3） | **随手修（原归 L1，L 系列已作废）** / 14.1 |
| Phase 7 RAG | 基础链路 + 混合检索（**9 项集成测试已实跑通过**） | Rerank（P1）/ 解析器（P2） | 14.1 / 14.2 |
| Phase 8 Agent | 主链路（**检查点实际未启用，见 5.3 #18**） | 重试 / 超时统一 / 统计 / 上下文补强 | 8.2 / 8.3 |
| Phase 9 Pipeline | 4 Stage | 范围重定义 + WS 接入 + 补必要 Stage | **8.2（P1）** |
| Phase 10.3 | Provider 设置页 | 其余管理页 | 见 8.5 |
| Phase 10.5 | 代码 + 13 测试 | UI 实测 5 项 | 先关单，见第三节 |

### 7.3 未开始（本次新识别，按新定位重排）

> 「归属」列已全面对齐 **D1–D7**（Docker 化交付）与 **8.2 / 8.3 / 8.5**（后续阶段）。

| # | 事项 | 类别 | 优先级 | 归属 |
|---|---|---|---|---|
| 1 | **Compose 本地化改造**（剥离 Traefik/域名/adminer/HTTPS） | 交付 | **P0** | **D1** |
| 2 | **补全 Milvus 全家桶**（etcd + MinIO + milvus，含依赖顺序与 healthcheck） | 交付 | **P0** | **D1.2** |
| 3 | **前端改后端托管**（多阶段构建 + SPA 路由 fallback） | 交付 | **P0** | **D1.3** |
| 4 | **一键启动脚本**（Windows `.cmd` / macOS·Linux `.sh`） | 交付 | **P0** | **D2** |
| 5 | **首次启动引导**（`SECRET_KEY` 落盘 + 随机管理员密码 + 打印地址） | 安全 | **P0** | **D3** |
| 6 | **端到端验证 + README** | 交付 | **P0** | **D4** |
| 7 | **数据迁移**（本机 PG + Milvus → 容器；强制备份） | 交付 | **P0 ★ 最高风险** | **D5** |
| 8 | **shell / file 工具权限开关**（默认关 + 路径白名单） | 安全 | **P0** | **D6** |
| 9 | **交付文档**（备份/恢复/卸载说明） | 交付 | **P0** | **D7** |
| 10 | **缓存淘汰**（`_chat_cache` / `_embed_cache` 加 LRU/TTL） | 安全 | P1 | 随手修（原 Phase 11 保留项） |
| 11 | **`is_default` DB 唯一约束** | 安全 | P1 | 随手修（原 Phase 11 保留项） |
| 12 | Pipeline 范围重定义 + WS 接入 Pipeline | 骨架 | P1 | 8.2（12.1/12.2） |
| 13 | 上下文 token 计数 + 轮次截断器 + tool_call 配对修复 | Agent | P1 | 8.2（12.5） |
| 14 | Agent 空输出重试 + 工具超时统一 | Agent | P1 | 8.2（12.5） |
| 15 | RAG Rerank 段 + Provider Rerank 能力 | 质量 | P1 | 8.3（14.1） |
| 16 | 配置闭环（填 Key → 对话 → 管资源） | 前端 | P1 | 8.5（15.2） |
| 17 | 管理页：KB / MCP / Skill / Persona | 前端 | P1 | 8.5（15.2） |
| 18 | 登录/消息基础限流 + 输入长度限制 | 安全 | P1 | 8.5 设置页 / 随手 |
| 19 | 后端错误消息中文化 | 体验 | P1 | 8.5（15.3） |
| 20 | Persona 系统（Manager + 注入 + API + UI） | 骨架 | P2 | 8.3（14.3） |
| 21 | AgentRun 统计采集 + 统计页 | 运维 | P2 | 8.3（14.3） |
| 22 | RAG 聚合模式（KB 查询工具） | 骨架 | P2 | 8.3（14.2） |
| 23 | Skill source_type 四类来源 | 骨架 | P2 | 8.3（14.4） |
| 24 | 多模态 ContentPart 体系（Web 传图） | 体验 | P2 | 8.3（14.5） |
| 25 | 内容安全审核（**降为可选**） | 骨架 | P2 | 8.6 保留项 |
| 26 | 备份导入导出（**`docker compose exec` 导出 SQL + 卷备份**） | 运维 | P2 | 8.6 保留项 / D7 |
| 27 | 日志分级与敏感信息脱敏（api_key 不进日志） | 运维 | P2 | 8.6 保留项 |
| 28 | `tasks.md` / `checklist.md` / `spec.md` / `astrbot-architecture.md` 状态同步 | 文档 | P2 | 第十节 |
| 29 | Handoff 子代理 / 后台任务工具 | Agent | P3 | 8.3（14.6） |
| 30 | Cron 定时任务（浏览器内定时提醒） | 体验 | P3 | 8.3（14.6） |
| 31 | STT / TTS | 体验 | P3 | ➖ 暂不做 |
| 32 | 前端 `.gitattributes` 换行符统一 | 卫生 | P3 | 随手 |

> **已移出本表的事项**（原编号）：多用户隔离相关的 3 项（原 #1/#2/#3）随 D2 取消 —— ⚠️ **2026-09-18 更正**：取消的是「多用户**运营化**」部分，**归属隔离本身已实现**（`ef08cc1`，见 8.4），故这三项中真正作废的是运营化相关项；在线部署开关分层（原 #14）与多用户配额（原 #24）随 D1 移交另一个项目。
> **已从本表删除的事项**：「数据库 URI 可切换（SQLite / PostgreSQL）」「UUID 方言适配（`GUID` TypeDecorator）」「建表策略（SQLite `create_all`）」「向量库可插拔（FAISS）」——**这四项随 D4 整体失去意义**。PostgreSQL 与 Milvus 就是主力方案，不需要"可切换"和"可插拔"。

---

## 八、后续开发计划（总览）

> ⚠️ **格局已变（D4–D7）**：本项目只做本地单用户，**保持 PostgreSQL + Milvus，走 Docker 一键启动**。原「Phase 11–16」中：
> - **Phase 13 本地部署免依赖** → **作废**，由 **D1–D7** 取代（承诺从「零外部依赖」改为「一条命令」）
> - **Phase 11 Provider 多用户化** → **拆两半**（2026-09-18 修订）：**多用户运营化**（自助注册 / 配额 / 计费）→ 降级不做；**归属隔离** → **已实现为硬约束**。另保留 2 项，见 8.4
> - **Phase 16 线上部署与工程化** → **移出本项目**（网页版独立）
>
> **本节从「施工手册」降为「战略地图」**：只保留阶段划分、依赖关系、里程碑。**具体到行号的施工步骤一律写在 [local-deployment-plan.md](./local-deployment-plan.md)**，避免两份文档各说一套。

### 8.0 总体规划

| 阶段 | 主题 | 优先级 | 核心产出 | 依赖 | 详案 |
|---|---|---|---|---|---|
| **Phase D1** | **Compose 本地化改造** | **P0 ★ 关键路径起点** | 可本地运行的 `compose.yml`（6 服务）+ 前端后端托管 | 无 | [local-deployment-plan.md](./local-deployment-plan.md) §3 |
| **Phase D2** | **一键启动脚本** | **P0 ★** | `.cmd` / `.sh` 双份脚本 | D1 | 同上 §4.1 |
| **Phase D3** | **首次启动引导** | **P0 ★** | `SECRET_KEY` 落盘 + 随机密码 + 打印地址 | D1 | 同上 §4.2 |
| **Phase D4** | **端到端验证** | **P0 ★** | 干净环境跑通 + 测试矩阵 + README | D1+D2+D3 | 同上 §5 |
| **Phase D5** | **数据迁移** | **P0 ★ 最高风险** | 本机开发数据完整迁入容器 | **D4** | 同上 §6 |
| **Phase D6** | **工具权限开关** | **P0** | `shell` / `file_write` 默认关闭 | 无（可并行） | 同上 §7 |
| **Phase D7** | **交付** | **P0** | 交付/备份/卸载文档 | D4+D5 | 同上 §8 |
| **Phase 12** | 管线完整化 + 上下文管理补强 | P1 | Pipeline 范围重定义 + WS 接入 + token 计数 / 轮次截断 / 重试 | D1–D4 | 8.2 |
| **Phase 14** | Agent 能力补强 | P1–P2 | Rerank / Persona / 统计 / 聚合检索 / 多模态 | Phase 12 | 8.3 |
| **Phase 15** | 前端完善（对话 + 配置台） | P1 | 对话体验打磨 + KB/MCP/Skill/Persona 管理页 + 配置闭环 | D1–D4 + 14 | 8.5 |
| ~~Phase 11~~ | ~~Provider 多用户化（BYOK）~~ | ➖ | **运营化降级；归属隔离已实现** | — | 8.4 |
| ~~Phase 13~~ | ~~本地部署免依赖~~ | ➖ | → **作废，由 D1–D7 取代** | — | [local-deployment-plan.md](./local-deployment-plan.md) |
| ~~Phase L1–L4~~ | ~~SQLite 化 / FAISS 化 / 一键启动 / 验证~~ | ➖ | → **全部作废（D4）**，部分重编号为 D2–D7 | — | — |
| ~~Phase 16~~ | ~~线上部署与工程化~~ | ➖ | **移出本项目**（D1） | — | 见文末迁移清单 |

**关键路径**：`D1 → D2/D3 → D4 → D5`（**D5 必须严格在 D4 之后**）

> ⚠️ **为什么 D5 不能在 D4 之前**：数据迁移是**不可逆操作**，一旦把本机 126 个会话搬进一个还没验证过的容器环境，出了问题就很难回溯。
> **先证明新房子能住，再搬家具进去。** 顺序不能颠倒。

**并行机会**：
- **D6（工具权限开关）完全独立**，可随时插入，不阻塞任何阶段
- **D1.1–D1.3 内部可并行**（剥离 Traefik / 补 Milvus / 前端托管是三块独立工作）
- **D2 与 D3 可合并实现**（都在启动脚本里），但**概念上要分开**——脚本负责"起来"，引导负责"能用"

**排序理由**：
1. **D1–D4 最先做，且是唯一的 P0**——它决定「用户能不能自己跑起来」。当前 `compose.yml` 依赖 `${DOMAIN}` / Traefik / 证书，**别人拿到仓库根本跑不起来**。这不是"加功能"，是**"让交付成立"**。
2. **D5 排在 D4 之后而非之前**——见上方警示。迁移的前提是「目标环境已验证」。
3. **Phase 12 排在 D 系列之后**——管线是上层能力的挂载点，但它**不应照搬 AstrBot 的 9 Stage**，而是先做「Web 场景到底需要哪些 Stage」的裁剪判断，否则会做大量无用功。
4. **Phase 14 与 12 部分交错**——Rerank 依赖检索链路稳定；Persona / 统计没有硬依赖，可提前。
5. **Phase 15 必须早于「宣布可用」**——用户必须能纯网页完成「填 Key → 对话 → 管 KB/MCP/Skill」。缺管理页 = 用户必须改配置文件 = 产品不成立。
6. **原 Phase 11 / 13 / 16 均已移出**——11 **仅「运营化」部分**因单用户降级（**归属隔离反而已实现**，见 8.4），13 因 D4 作废，16 因网页版拆分。它们的价值转移到了别处，不是"延期"，是"不在这里做"。

---

### 8.1 各阶段详案索引

> 本节只做**索引**。施工细节请点进对应文档，避免同一内容在两处维护。

| 阶段 | 详案位置 | 说明 |
|---|---|---|
| **D1–D7**（Docker 化交付，P0） | [local-deployment-plan.md](./local-deployment-plan.md) | **精确到行号**的改动清单（`compose.yml` / `config.py` / `Dockerfile`）、完整 YAML 示例、启动脚本、首启引导、数据迁移步骤与回滚、风险登记 |
| Phase 12（管线 + 上下文，P1） | 本文档 **8.2** | 含 12.1–12.5 五组任务 |
| Phase 14（Agent 能力，P1–P2） | 本文档 **8.3** | 含 14.1–14.6 六组任务 |
| ~~Phase 11~~（部分降级） | 本文档 **8.4** | 运营化为何不再适用 + **已实现的归属隔离** + 保留的 2 项 |
| Phase 15（前端，P1） | 本文档 **8.5** | 含 15.1–15.3 三组任务 |
| ~~Phase 16~~（移出） | 本文档 **8.6** | 逐项「留下 / 搬走」迁移清单 |
| 依赖图 / 优先级 / 里程碑 | 本文档 **8.7 / 8.8 / 8.9** | — |

---

### 8.2 Phase 12: 管线完整化 + 上下文管理补强（P1）

> 依赖：D1–D4 完成（需容器环境可跑通）。**不阻塞本地可用**——本地跑起来是第一优先。

**目标**：把 Pipeline 从「4 Stage 顺序循环」改造为「按 Web 场景裁剪的洋葱模型」，并把上下文管理补齐到生产可用。

#### 12.1 Pipeline 范围重定义（先决策，后编码）
- [ ] 列出**候选 Stage**并逐个判定「Web 场景是否需要」：
  | Stage | AstrBot 用途 | Web 场景是否需要 | 结论 |
  |---|---|---|---|
  | WakingCheck | 唤醒词 / @ 判定 | ❌ 无群聊 | 不做 |
  | WhitelistCheck | 群白名单 | ❌ 无群聊 | 不做（→ 改为 ResourceOwnerCheck：会话归属校验） |
  | SessionStatus | 会话开关 | ✅ 会话级启用/停用 | 做（`Conversation.is_enabled`） |
  | RateLimit | 限流 | ✅ 按用户限流 | 做（已有，需扩到 WS + 按 user 维度） |
  | ContentSafety | 内容审核 | 🔶 可选（`ENABLE_CONTENT_SAFETY` 已有关闭开关） | 做（默认关） |
  | PreProcess | 前处理 | ✅ 输入规范化 / 长度限制 | 做（已有） |
  | Process | 主处理 | ✅ Agent 调用 | 做（已有） |
  | ResultDecorate | 出参装饰 | ✅ 敏感信息过滤 / 引用标注 | 做（简化版） |
  | Respond | 发送 | 🔶 Web 是 WS 推送 | 做（推送而非发送） |
- [ ] 产出结论表并写入文档（避免后续争议）
- [ ] 明确**不做洋葱模型也没关系**——若最终只剩 5 个顺序 Stage，优先保证正确性而非形式

#### 12.2 洋葱模型改造（若必要）
- [ ] `Stage.process()` 支持返回 `AsyncGenerator[PipelineContext, None]`
- [ ] `PipelineScheduler._process_stages(ctx, from_stage)` 递归实现前置/后置嵌套
- [ ] 向后兼容：返回普通协程的 Stage 走顺序分支
- [ ] `stage_order.STAGES_ORDER` 常量定义权威顺序
- [ ] 测试：FakeStage 记录调用顺序，断言前置/后置嵌套正确

#### 12.3 WS / REST 接入 Pipeline（修复已知问题 #13）
- [ ] `agent_ws.py` 删除绕过 Pipeline 的直连调用，改为投递到 Scheduler
- [ ] REST `/agent/conversations/{id}/chat` 同样走 Scheduler
- [ ] `RateLimitStage` 在 WS 与 REST 两通道均生效（且按 `user_id` 维度）
- [ ] 前端 WS 协议保持兼容（`history` / `text_chunk` / `tool_call` / `done` 不变）
- [ ] 测试：同一逻辑在两通道行为一致；限流在 WS 下确实生效

#### 12.4 内部钩子（精简版，非 AstrBot 的 17 个 EventType）
- [ ] 保留 2–3 个内部切点：`on_llm_request` / `on_llm_response` / `on_agent_done`
- [ ] 用途：Playground 调试回显、统计采集（Phase 14.3）、未来扩展
- [ ] **不做**第三方插件注册接口
- [ ] 测试：钩子在对应切点被调用；抛异常不中断管线

#### 12.5 Agent 与上下文补强
- [ ] `token_counter`：中英文 / 图片分权重估算；优先采用 Provider 返回的真实 usage
- [ ] `ContextTruncator`：`truncate_by_turns` / `dropping_oldest_turns` / `halving` 三策略
- [ ] `fix_messages()`：保证 `assistant(tool_calls)` 与 `tool` 消息配对，防截断后 API 报错
- [ ] `split_into_rounds()` 轮次切分
- [ ] Agent 空输出重试：`tenacity` 指数退避 3 次
- [ ] 工具调用超时统一到 `run_context.tool_call_timeout`（默认 120s）
- [ ] 最大工具轮数 15 → 30（与 AstrBot 对齐），达上限后 `func_tool=None` + 总结提示
- [ ] 测试：截断后消息序列通过 Provider 校验；空输出重试确实触发

**验收**：SC8 通过——Web 场景所需 Stage 全部生效；WS 与 REST 限流行为一致；长对话截断不报错。
**优先级**：P1 ｜ **依赖**：D1–D4 ｜ **阻塞**：Phase 14/15

---

### 8.3 Phase 14: Agent 能力补强（P1–P2）

> 依赖：Phase 12（检索链路稳定后加 Rerank）。16 个 Stage 与 Persona / 统计无硬依赖，可提前。

**目标**：把 Agent 能力栈补到 AstrBot 同级。

#### 14.1 RAG 质量补强
- [ ] Provider Rerank 能力：`get_rerank_model()` + `RERANK` 类型 + `MODEL_SOURCES` 补 rerank 来源
- [ ] 检索链路插入 Rerank 段（RRF 之后，`top_m_final=5`）；未配置时优雅降级
- [ ] MarkItDown / URL / EPUB / DOCX 解析器（按需增量）
- [ ] 测试：有/无 Rerank 两条路径；顺序断言（稠密 → 稀疏 → RRF → Rerank）

#### 14.2 RAG 聚合模式
- [ ] `knowledge_base_query` 工具支持 Agentic 模式（LLM 自行决定检索词与次数）
- [ ] 对应 AstrBot `kb_agentic_mode`
- [ ] 测试：Agent 可自主决定是否检索、检索几次

#### 14.3 Persona 与统计
- [ ] `PersonaManager`：CRUD + 会话级绑定（模型已存在，需补 Manager）
- [ ] Agent 注入：persona prompt → SystemMessage（与 skills / KB 注入同一装饰链）
- [ ] REST API + 控制台页面
- [ ] `AgentRun` 统计采集：token 用量（prompt/completion）、耗时、TTFT、工具调用次数与名称
- [ ] 统计页数据源对接 Phase 15
- [ ] 测试：Persona 在对话中生效；统计字段落库正确

#### 14.4 Skill 来源扩展
- [ ] `source_type` 四类来源（local / 远程 URL / git / marketplace 占位）
- [ ] 测试：各来源安装路径与安全校验

#### 14.5 多模态（P2，Web 传图）
- [ ] `ContentPart` 体系：`TextPart` / `ThinkPart` / `ImageURLPart`
- [ ] `Message.content` 支持 `str | list[ContentPart]`；DB JSON 列多态序列化
- [ ] `ThinkPart` 支持 `_no_save` 不落库
- [ ] 前端：图片上传 + 粘贴 + 预览；后端：接收 → 多模态 Message
- [ ] Provider 能力感知：不支持图片输入时降级（转文字描述或切 Fallback）
- [ ] 测试：多模态消息端到端可存可显

#### 14.6 可选增强（P3）
- [ ] Handoff 子代理 + `SubAgentOrchestrator`
- [ ] 后台任务工具 + 工具结果落盘（>27500 tokens）
- [ ] Cron 定时任务（浏览器内定时提醒场景）
- [ ] 追发消息（follow_up）

**验收**：RAG 检索带 Rerank 质量明显提升；Persona 可在对话中生效；统计页有真实数据；Web 可上传图片对话。
**优先级**：P1（14.1–14.3）｜ P2（14.4–14.5）｜ P3（14.6）
**依赖**：Phase 12 + D1–D4

---

### 8.4 原 Phase 11 的处理（**拆分：运营化降级 / 归属隔离已实现**）

> ⚠️ **本节已于 2026-09-18 修订。** 原表述是「Phase 11 因 D2（本地单用户）**整体降级**，串 Key 问题在单用户下不存在」——**这个归并是错的**。
>
> Phase 11 里其实混着**两件性质不同的事**，必须拆开看：

| 拆分项 | 内容 | 处置 | 理由 |
|---|---|---|---|
| **(A) 多用户「运营化」** | 自助注册、配额、计费、多账号自助闭环 | ➖ **降级不做** | D2 本地单用户 + D1 运营能力已随网页版拆分出去 |
| **(B) 「归属隔离」** | 每条数据 / 每个 Provider 只能被它的归属者取到 | ✅ **已实现为硬约束** | 见下方「为什么隔离必须做」 |

#### 为什么「隔离」不能跟着「运营化」一起砍

原判「单用户下不存在串 Key」**只对 (A) 成立**。 (B) 有独立价值，三条理由：

1. **越权面与用户数无关**：`get_chat_model(provider_id=None)` 若不带 `user_id` 过滤，取的是**全库**默认源。哪怕只有一个账号，这也意味着任何一处传参失误都会让「取我的默认源」变成「取第一条默认源」——**用户配了 A 家的 Key，实际跑的是 B 家的**，且无任何报错。这是**静默错误**，比报错危险。
2. **本代码库要被另一个多用户项目复用**：留一个「忽略 user_id」的签名，等于把越权缺陷**预埋**给对方，对方接入时未必能想起来补。
3. **安全默认优于留白**：`user_id=None` 时 **fail closed**（查不到任何源 → 明确 `RuntimeError`），而不是回落成「取全库任意默认源」。

> **一句话**：砍掉的是**运营功能**，不是**安全边界**。这两者此前被当成一件事处理了。

#### 已实现内容（提交 `ef08cc1`）

| 项 | 实现 |
|---|---|
| **`user_id` 必填** | `get_chat_model(self, user_id: uuid.UUID \| None, ...)` / `get_embedding_model(self, user_id, provider_id=None)` —— **位置参数、无默认值**，调用方必须显式交代归属 |
| **两条查找分支都过滤** | `provider_id` 分支与「取默认」分支**均**带 `ProviderConfig.user_id == user_id`。⚠️ 只改一条是典型漏改点（`provider_id=None` 那条才是越权入口） |
| **缓存键含 `user_id`** | `cache_key = f"{user_id}:{provider_id}:{model_name}:{temperature}"` —— 否则两个用户用同一个 `provider_id=None` 会**命中同一条缓存**，直接拿到别人的模型实例 |
| **`None` 时 fail closed** | 查不到任何源即 `RuntimeError: No active provider configured`，**绝不**回落为「取全库任意默认源」 |
| **删除默认源时按用户补位** | `delete_provider()` 的接替者查询同样带 `user_id`，避免删自己的默认源却把**别人**的源提上来（`a746d10`） |

#### 原 Phase 11 各子任务逐项裁定

| 原任务 | 裁定 |
|---|---|
| 11.1 读取路径贯穿 `user_id`（必填参数） | ✅ **已做**（`ef08cc1`）。原判「加参数只是增加噪音」忽略了 `provider_id=None` 分支的越权语义 |
| 11.2 缓存键隔离（键含 `user_id`） | ✅ **已做**（同上）。原判「只保留缓存淘汰」把两件事混为一谈 |
| 11.3 传参链路改造（WS / REST / Agent 节点） | ✅ 已做（鉴权后注入当前用户） |
| 11.4 多用户隔离回归测试 | ✅ **已做**：`test_delete_default_does_not_touch_other_users` + `tests/api/routes/test_providers.py` 多租户用例（随 `a746d10`/`ef08cc1` 新增 7 条） |
| 11.5 `is_default` 唯一约束 | 🔶 **仍保留待做**，理由不变（见下） |

#### 另外保留的两项（与用户数无关，必须做）

| 项 | 为什么与用户数无关 | 位置 |
|---|---|---|
| **`_chat_cache` / `_embed_cache` 无界增长** | 单用户下 dict 也永不淘汰，长期运行内存只增不减 → 需加 LRU 或 TTL | `agent/provider.py:142-143` |
| **`is_default` 无 DB 级唯一约束** | 单用户下并发 / 异常同样可能产生两条默认 | `db/models.py` ProviderConfig |

> 这两项原归属 Phase 11，现**随 L 系列作废而降为「随手修」**（同属 `provider.py` 与 `models.py`，遇到就改，不单开阶段）。

#### 配套：注册入口默认关闭（D2.1，`41cccfd`）

本地部署的服务是 **localhost 可达**的。若 `POST /users/signup` 匿名开放，「单用户」就只是**口头约定**——任何能访问该端口的人都能自助开号。

- 关闭时：`POST /users/signup` → **403** `Open user registration is forbidden on this server`
- ⚠️ **守卫必须置于「邮箱查重」之前**：否则未开放时仍能从「该邮箱已存在」的报错反推系统内有哪些账号，**把注册闸门变成账号枚举探测面**
- 默认值：**关闭**（沿用 D6 的「高危能力默认关」范式）

#### 配套：运行时开关（2026-09-18 升级 —— 把 D2.1 从「写死」改成「可切换」）

**动机**：原实现把开关写死在 `.env`（`USERS_OPEN_REGISTRATION`），改一次要重启 backend。用户要求 **管理员应能自行在「多租户」与「单用户」之间切换**，不把单用户钉死。

| 件 | 内容 |
|---|---|
| 存储 | 新增 `app_settings` 通用 KV 表（`key` / `value` / `updated_at`）+ 迁移 `d4e5f6a7b8c9` |
| 读取层 | `app/core/settings_runtime.py`：键名常量 + `get_setting` / `set_setting` + **`signup_allowed()`（全项目唯一判断点）** + `deployment_mode()`（展示标签）+ `count_users()` |
| 优先级 | **`app_settings` 表 > `.env` > 代码默认值**。表里没记录时回落 `.env` → **升级后现网行为零变化** |
| 端点 | `GET` / `PATCH /settings/deployment`（超管）、`GET /utils/public-settings`（匿名，只暴露一位布尔，供登录页渲染注册入口） |
| 前端 | `/admin` 页顶部「部署模式」两态开关（切到多租户时弹二次确认）+ 登录页按开关显示「注册」入口 |
| 不做缓存 | **每请求直读 DB**。多 worker / WS 进程各持副本必然不一致，而主键单行查询开销可忽略 |

**⚠️ 一个刻意的收窄：只有「注册是否开放」这一项是运行时的。**

「单用户 / 多租户」只是它的**展示标签**（由 `signup_allowed()` 派生），**不是独立配置项**。原因：既然超管在两种模式下都能建号、`/admin` 两种模式都保留、归属隔离两种模式都生效，那么「多租户 + 关注册」与「单用户」在**所有可观测行为上完全等同**——留两个开关只会造出一个产出相同结果的档位，读设置的人无从判断该选哪个。

**冗余状态比缺失状态更危险**：它会让人误以为存在一道其实不存在的约束。完整推演见 [multi-tenant-plan.md](./multi-tenant-plan.md) 第十一节。

**与 D2 归属隔离的关系**：本开关**不动**归属隔离。`provider.py` 的 `user_id` 过滤两种模式下都生效（见本节上半部分）。**砍掉的是运营功能，不是安全边界。**

**优先级**：P1 ｜ **状态：✅ 已实现（2026-09-18）**

**优先级**：P1（保留的两项）｜ **归属**：随手修（不单开阶段）

---

### 8.5 Phase 15: 前端完善（对话 + 配置台）（P1）

**目标**：让用户**完全通过网页**完成「填 Key → 对话 → 管 KB / MCP / Skill」全流程。

#### 15.1 对话体验（产品主体）
- [ ] 会话列表管理（新建 / 重命名 / 删除 / 搜索）
- [ ] 消息操作（重新生成 / 复制 / 编辑重发 / 删除）
- [ ] 流式渲染打磨（打字机、代码块高亮、Markdown 表格）
- [ ] 工具调用可视化（折叠面板展示入参/结果，当前已有基础）
- [ ] 引用与检索来源展示（RAG 命中片段 + 相似度）
- [ ] 中断当前生成（调用已有 `interrupt`）
- [ ] 错误态与重试提示中文化
- [ ] 移动端适配

#### 15.2 配置台管理页（关键）
- [ ] **配置闭环**：首次进入 → 引导填 Key → 首轮对话（空状态引导）
- [ ] Provider 管理页（10.3 / 10.5 收尾）
- [ ] 知识库页：KB 列表 / 文档上传 / 分块与检索参数 / 检索测试
- [ ] MCP 页：列表 / 连接测试 / 工具预览
- [ ] 技能页：列表 / 上传 / 详情
- [ ] Persona 页：列表 / 编辑 / 会话绑定
- [ ] 会话管理页：列表 / 查看历史（含工具调用折叠）/ 启用停用 / 删除
- [ ] 统计页：token 用量 / 耗时 / 工具调用（依赖 14.3）
- [ ] 设置页：账号 / 密码 / **工具权限开关（依赖 D6）** / 外观

#### 15.3 其它
- [ ] 侧边栏信息架构重组：对话 / 知识库 / MCP / 技能 / 模型源 / 会话 / 统计 / 设置
- [ ] Logo 替换（去掉 FastAPI SVG）
- [ ] 每个页面至少 1 个 Playwright e2e（**在容器环境跑**）

**验收**：用户全程零配置文件操作；管理页覆盖 Provider / KB / MCP / Skill / Persona。
**优先级**：P1 ｜ **依赖**：D1–D4（容器环境）、D6（工具开关）、14.3（统计 / Persona）

---

### 8.6 原 Phase 16 的迁移清单（移出本项目）

> **Phase 16「线上部署与工程化」已随 D1 移出本项目**，去往独立的网页版项目。
> 本节**只保留「哪些东西搬走了」的记录**，避免将来误以为"忘了做"。

| 原任务 | 去向 |
|---|---|
| 16.1 部署开关分层（`ENABLE_REGISTRATION` / `ENABLE_MULTIMODAL` 等） | ➡️ 另一个项目 |
| 16.1 `FIRST_SUPERUSER_PASSWORD` 强制非默认校验 | 🔶 **本项目改为「首次启动随机生成并打印」**（见 **D3**） |
| 16.2 Rate Limiting（登录 + 消息双维度） | ➡️ 另一个项目；本项目**单用户**保留基础限流即可 |
| 16.2 输入长度限制 | 🔶 **保留在本项目**（防 Prompt Injection 与超大 payload） |
| 16.2 CORS 白名单收紧 | ➡️ 另一个项目（本项目 localhost） |
| 16.2 HTTPS / 反代配置文档 | ➡️ 另一个项目 |
| 16.3 用户管理（管理员视角） | ➡️ 另一个项目 |
| 16.3 每用户配额 | ➡️ 另一个项目 |
| 16.3 备份导入导出 | 🔶 **保留在本项目**（本地用户同样需要备份数据）→ 用 `docker compose exec db pg_dump` + 卷备份，可并入 Phase 15 设置页 |
| 16.3 日志分级与脱敏（api_key 不进日志） | 🔶 **保留在本项目** |
| 16.4 `tasks.md` / `checklist.md` 同步 | 🔶 **保留**（文档卫生，见第十节） |
| 16.4 `spec.md` 对齐定位 | 🔶 **保留**（见 10.1） |
| 16.4 `astrbot-architecture.md` 优先级同步 | 🔶 **保留**（见 10.6） |
| 16.4 e2e 全量实跑 | 🔶 **保留**（D4 阶段一并做） |
| 16.4 `.gitattributes` 换行符统一 | 🔶 **保留**（随手做） |
| 16.4 内容安全审核 | 🔶 **降级为 P2 可选**（本地单用户，非必需） |

**判定原则**：**「本机使用者自己需要」的留下，「面向陌生用户」的搬走。**

---

### 8.7 依赖关系图

```
Phase 10 收尾 (10.5 验收 + e2e)
     │
     ▼
┌──────────────────────────────────┐
│  Phase D1–D7（Docker 化交付）★P0 │  ← 唯一 P0，决定交付能否成立
│  D1 Compose 本地化改造           │
│   ├─ 1.1 剥离 Traefik/域名      │
│   ├─ 1.2 补 Milvus 全家桶       │
│   └─ 1.3 前端改后端托管         │
│         │                        │
│         ├──► D2 启动脚本         │
│         ├──► D3 首次引导         │
│         │      │                 │
│         │      ▼                 │
│         └──► D4 端到端验证       │
│                 │                │
│                 ▼                │
│            D5 数据迁移 ⚠️高风险  │
│  D6 工具权限开关（独立，可随时） │
│  D7 交付文档                     │
└──────────────────────────────────┘
     │
     ├──────────────────┐
     ▼                  ▼
Phase 12 (管线+上下文)  Phase 14.1–14.3 (Rerank/Persona/统计)
     │                  │
     └────────┬─────────┘
              ▼
       Phase 14.4–14.5 (Skill 来源 / 多模态)
              │
              ▼
       Phase 15 (前端：对话 + 配置台)
```

**详细依赖见 [local-deployment-plan.md](./local-deployment-plan.md) 第一节。**

> ~~Phase 11（Provider 多用户化）~~ 已降级 → 见 8.4。~~Phase 13（本地部署免依赖）~~ 已作废 → 由 D1–D7 取代。~~Phase 16（线上部署）~~ 已移出 → 见 8.6。

### 8.8 优先级矩阵

| 优先级 | 事项 | 理由 |
|---|---|---|
| **P0** | **Phase D1–D7 全部** | D 系列是交付底线（跑不起来则一切无意义）；D5 是唯一的高风险项，必须单独盯 |
| **P1** | Phase 12 全部、Phase 14.1–14.3、Phase 15 全部；缓存淘汰 + `is_default` 约束 | 能力骨架 + 用户可见闭环 + 既有缺陷 |
| **P2** | Phase 14.4–14.5、内容安全、备份导出、日志脱敏 | 锦上添花与工程卫生 |
| **P3** | Handoff、Cron、STT/TTS | 低频需求 |

> ⚠️ **与上一版的区别**：上一版有 **两个** P0（Phase 11 + Phase 13）。现在**只剩一个**——因为 Phase 11 降级了。这意味着**注意力应该更集中**，不要因为"少了一个 P0"而误以为"事情变少了"。
>
> **第三版又变了一次**：P0 从「本地化（SQLite 化）」变成「Docker 化交付」。**数量同为 1，但内容完全不同**——这才是关键。同样是"一个问题"，但解法从"删数据库"变成了"打包数据库"。

### 8.9 里程碑

| 里程碑 | 完成标志 | 对应阶段 |
|---|---|---|
| **M1：装得上** ★ | 干净机器装好 Docker → 一条命令 → 全栈 6 服务 healthy | **D1 + D2** |
| **M2：用得了** ★ | 浏览器打开即对话；重启不丢登录态；无任何手工配置 | **D3 + D4** |
| **M3：搬得走** ★ | 本机 126 会话 / 22 知识库完整迁入容器，且可回滚 | **D5** |
| **M4：给得出** | 他人拿到仓库同样一条命令跑通；交付文档齐备 | **D4.3 + D7** |
| **M5：管得住** | Pipeline 覆盖 Web 场景所需 Stage；限流/截断/重试生效 | Phase 12 |
| **M6：能力齐** | Rerank / Persona / 统计可用 | Phase 14 |
| **M7：能自助** | 用户纯网页完成 填 Key → 对话 → 管资源 | Phase 15 |

> **M1–M4 是所有里程碑中唯一的前置条件** —— 在它们完成前，其余里程碑都只是"在跑不起来的系统上加功能"。
>
> ⚠️ **M3 要单独提醒**：它是唯一**不可逆**的里程碑。前三个都是"加东西"，只有它是"搬家"。搬之前必须先备份，且要验证过备份可以恢复——**未经恢复演练的备份不算备份**。

---

## 九、本次文档更新说明

| 变更 | 内容 |
|---|---|
| **文件重命名** | `progress.md` → `istbot-implement-plan.md`（按用户要求） |
| **定位对齐（第三轮）** | 第零节定位由「IM 机器人框架」修正为「**自托管多用户 AI Agent 平台，本地部署为产品主体**」；新增 0.1 一句话定位 / 0.2 定位决策表 / 0.4 本地线上双形态 / 0.5 已否定判断追溯 |
| **对标范围收缩** | 第六节矩阵重排：原「平台适配器 P0 / 插件体系 P1 / IM 场景专项」整体移入 **6.2 明确不采用区**；核心对标区改为 Agent 能力栈 |
| **P0 集合变更** | 由「平台适配器 + 事件总线 + IM 接入」变为「**Provider 多用户隔离** + **本地部署免依赖**」 |
| **SC 变更（第三轮）** | SC15/SC16（IM 接入、插件体系）划取消；SC8 由「9 Stage 全实现」重定义为「Web 场景所需 Stage 全部生效」；SC11–SC14 重写为多用户 BYOK / 本地免依赖 / 网页自助闭环 / 双形态切换 |
| **新增已知问题（第三轮）** | Phase 3.5 多用户隔离缺口（P0）；Phase 7.7 向量库不可插拔（P0）；Phase 4.4 工具无权限开关（P0） |
| **被否定的早期判断** | 「平台适配器 P0」「插件体系 P1」「Web 仅控制台」「不做多租户」「Rerank P0」「多模态 P1」「Cron P1」七条，均在 0.5 节留痕 |
| — | — |
| **定位对齐（第四轮，最新）** | 第零节改为「**本地部署的 AI Agent 桌面级应用，单用户**」；新增 0.0 决策表（D1/D2/D3）；0.4 由「双形态」改为「已改单形态」 |
| **Phase 重排（第四轮）** | 新增 **L1–L4**（本地化施工，并入 [local-deployment-plan.md](./local-deployment-plan.md)）；**Phase 11 降级**；**Phase 13 重命名为 L1–L4**；**Phase 16 移出** |
| **P0 集合变更（第四轮）** | **收窄为只剩一个**：本地化（L1–L4 + 保留的 2 项）。原 Phase 11 不再是 P0 |
| **SC 变更（第四轮）** | 新增 **L1–L8**；SC11 取消；SC12 重编号为 L1–L3；SC13 部分保留；SC14/15/16 取消 |
| **第六至十节原地改写（第五轮）** | ⚠️ **修复了文档内部自相矛盾**：<br>• 第八节由「Phase 11–16 完整施工手册」**降维为战略地图**（8.0 总览 / 8.2 Phase 12 / 8.3 Phase 14 / 8.5 Phase 15）<br>• 新增 **8.4 原 Phase 11 降级说明**（含保留的 2 项 + 「留接口不留逻辑」义务）<br>• 新增 **8.6 原 Phase 16 迁移清单**（逐项判定「留下 / 搬走」）<br>• 6.4 节删除「多用户 BYOK 是核心差异化」，改为三项新差异化<br>• 6.2 / 6.1 节定位描述与优先级对齐<br>• Phase 3.5 由「多用户隔离缺口（P0）」改为「缓存淘汰缺失（P0）」<br>• Phase 4.4 / 7.7 的归属由旧 Phase 编号改为 L3.5 / L2<br>• 7.2 / 7.3 全部归属改为 L1–L4 + 8.x 编号<br>• 移除已删除测试文件 `test_uuid_portability.py` 的「新增」标注<br>• 8.1/8.2/8.3 重排为 8.7/8.8/8.9（依赖图 / 优先级矩阵 / 里程碑） |
| — | — |
| **🔴 技术栈回滚（第五轮，根本性转向）** | **D4 推翻上一轮的「消灭 PostgreSQL」方案**：<br>• 第零节定位改为「**单用户使用，Docker 一条命令启动**」（删掉「零外部依赖」承诺）<br>• 0.0 决策表新增 **D4/D5/D6/D7**；D3 划掉并标注「已变更」<br>• 0.1 一句话定位：部署形态改「Docker Compose 一键启动」；新增「数据库 = PostgreSQL（容器内，可配环境变量指向外部）」「向量库 = Milvus（容器内，含 etcd + MinIO）」<br>• 0.1 新增警示块：说明「零外部依赖」承诺**已撤回**的理由<br>• 0.2 定位决策表：数据库/向量库行改回 PostgreSQL / Milvus，依据改为「保持已验证的技术栈（D4）」<br>• 0.4 「为复用留余地」义务重写（三条：Provider 留参数位 / 保留 Alembic 且本地也用它建表 / 保留 `compose.yml`）<br>• 0.3 差异化优势改写：从「零外部依赖」改为「**跨平台零适配成本**」，并与 AstrBot Desktop 的 Tauri 路线做对照<br>• 0.5 追溯表新增三条被推翻的判断（含「exe 双击即用 ⟺ 必须换数据库」这一**核心错误推论**） |
| **阶段重编号（第五轮）** | **L1–L4 全部作废**，重编号为 **D1–D7**（D1 Compose 改造 / D2 启动脚本 / D3 首次引导 / D4 端到端验证 / **D5 数据迁移** / D6 工具权限 / D7 交付）。**关键路径变为 `D1 → D2/D3 → D4 → D5`** |
| **P0 集合变更（第五轮）** | 从「消灭外部依赖（L1–L4）」变为「**Docker 化交付（D1–D7）**」。**数量同为 1，内容完全不同**——解法从"删数据库"变成"打包数据库" |
| **SC 变更（第五轮）** | **L1–L8 全部重写为 D1–D9**：新增「一条命令起全栈」「浏览器即用」「前端单端口」「重启不丢登录态」「开发数据完整迁移」「可分发」「测试基线不退化」；L7/L8 重定义为 D4/D7 |
| **P0 问题表重写（第五轮）** | **删除原 #1「本地部署硬依赖外部服务」**——它已从"问题"变为"方案"，保留会造成严重误导；新增 #1 `compose.yml` 无法本地运行 / #4 `FIRST_SUPERUSER_PASSWORD` 默认值 / #5 集成测试默认被跳过 / #6 数据迁移路径未验证 |
| **测试基线实跑（第五轮，新增 1.1 节）** | 发现集成测试被 `pytestmark = pytest.mark.integration` **默认跳过**（这是"跑了测试但不知道真实情况"的根因）。手动放行后实跑：`test_vec_store.py` **9 passed**（60.35s）、全量集成 **18 passed**（90.93s）。**RAG 链路获得真实证据背书** |
| **待确认项收缩（第五轮）** | 10.2「向量库选型 FAISS」→ **作废**（已选 Milvus）；10.4「PostgreSQL 是否删除」→ **消解**（保留）；10.5 Q2–Q6 → 替换为 **M1–M3 施工前调研**（Milvus 向量数据可迁移性 / 当前 Milvus 启动方式 / PG 版本兼容性） |
| — | — |
| **D2 语义拆分（第六轮，2026-09-18）** | 🔴 **修复文档与已发布代码方向相反的漂移**。原文档把 Phase 11 当成「因单用户整体降级」，并写下「留接口不留逻辑 / 单用户下忽略 `user_id`」的**义务**；而代码（`ef08cc1`）恰恰相反——`user_id` 已是**必填参数**且隔离逻辑**已实现**。现拆为 **(A) 多用户运营化**（降级不做）与 **(B) 归属隔离**（已实现为硬约束），并说明为何不能一起砍（静默越权 / 供另一项目复用 / fail closed 安全默认） |
| **SC11 恢复（第六轮）** | `~~SC11~~ 取消` → **✅ 达成**。取消的应是 BYOK 运营化，不是数据归属隔离本身 |
| **新增 SC D10（第六轮）** | **无自助注册入口**：匿名 `POST /users/signup` 必须 403 且不泄露账号存在性；已于 2026-09-18 实机验证（含**响应逐字节一致**的防枚举断言） |
| **0.0 决策表新增 D2.1（第六轮）** | **注册入口默认关闭**（`USERS_OPEN_REGISTRATION=false`，`41cccfd`），沿用 D6「高危能力默认关」范式 |
| **实证校准（第六轮）** | 用**实机探测**替换文档假设：容器重建后实测 ① `POST /users/signup` → 403 + 约定话术 ② 已存在 / 不存在邮箱响应逐字节一致 ③ 单账号 `admin@example.com` ④ Provider 列表恰 1 条默认 ⑤ 系统提示词端点可用。**不再以「文档写的」为准，以「容器里跑的」为准** |
| **第六至八节活引用同步（第六轮）** | 0.2 / 0.4 / 0.5 / 一节阶段表 / Phase 3.5 / SC 表 / 6.1 能力矩阵 / 8.0 总览 / 8.1 索引 / 8.4 详表 —— **只改活引用**；0.5 与 §九 中的历轮留痕、以及 `~~划掉~~` 项**一律保留**（追溯性引用是防摇摆依据） |
| — | — |
| **D2.1 由「硬约束」改为「运行时可切换」（第七轮，2026-09-18）** | 用户要求「管理员可以选择多租户和单用户开关」。原 D2.1 把开关写死在 `.env`，改一次要重启 backend。**修订为运行时开关**：`app_settings` 表 > `.env` 兜底，超管在 `/admin` 页切换即时生效。`.env` 的 `USERS_OPEN_REGISTRATION` **降为兜底初值**（不再是最终生效值） |
| **新增 8.4「配套：运行时开关」（第七轮）** | 完整落地说明：KV 表 + `settings_runtime` 读取层 + 两个端点（`/settings/deployment` 超管、`/utils/public-settings` 匿名）+ 前端两态开关。含**为何只留一个开关**的推演 |
| **D10 SC 升级（第七轮）** | 由「达成」→「**达成并升级**」：默认仍关闭，但改由运行时开关控制；两种模式下防枚举断言均成立 |
| **0.4 复用义务补一条（第七轮）** | 新增 `app_settings` + `settings_runtime`：另一个多用户项目可直接复用「网页改开关、免重启」这套机制 |
| **⚠️ 发现的编号冲突（第七轮，未修，待定）** | 全仓存在**三套互不相干的「D 编号」**：① 本文 0.0 决策表 `D1–D7 / D2.1` ② 本文 SC 验收表 `D1–D10` ③ `local-deployment-plan.md` 施工阶段 `D1–D7 + D1.1…`。同一文件 `PROGRESS.md` 里 `D2.1` 既有「注册入口」义、又有「Windows 启动脚本」义。**本轮不擅自重编号**（会大面积波及引用），但建议后续统一 |

---

## 十、待确认事项

### 10.1 `spec.md` 需同步更新 ✅ **以弃用结案（2026-09-17）**
> 原「待同步」待办已按**弃用方式结案**：`spec.md` 连同 `tasks.md` / `checklist.md` / `implementation-plan.md` 均改名 `DEPRECATED-*` 并加声明头（其内容停留在「IM 机器人框架」旧定位，同步已无意义）。
> 以下为当时的同步建议，仅作历史留痕：
`spec.md` 描述的是「Agent 平台 + Web 聊天界面」，**既不含单用户本地形态，也不含 Docker 交付形态**。建议：
- 明确「**本地单用户**」：删/标注「多用户与 BYOK」章节
- 新增「**交付形态**」章节：**Docker Compose 一键启动**；前置条件 = 装一次 Docker；默认容器内 PostgreSQL + Milvus
- 明确「**网页版已拆分独立**」：原线上部署相关内容整体移出
- 若第二轮已加入「平台适配器」「插件体系」章节 → **标注为不采用**（保留追溯，不要直接删）
- 把「WebUI/Dashboard」明确定位为「**对话主体 + 配置台**」双职责
- SC 对齐本文第四节（SC1–SC10 + **D1–D9**）

### 10.2 向量库选型 ✅ **已决定：Milvus**（第五轮修正）
> ~~原结论「已决定：FAISS」**已作废**~~（D4）。
>
> 上一轮基于「依赖极轻」选择 FAISS，但那个判断服务于一个**已被推翻的目标**（零外部依赖）。
> 一旦确认走 Docker 路线，FAISS 的唯一优势就消失了——而它的代价（**需自行维护分块原文快照**，因为它没有 `get_all_documents()` 等价物）依然存在。
>
> **当前结论**：**保持 Milvus**。已有 9 项集成测试真实验证过它（见 1.1），换掉等于**把已验证的东西换成未验证的**。

### 10.3 Skill 是否需要用户级隔离 ✅ **已消解**
D2 确立本地单用户后，此问题不存在 —— Skill 保持**全局目录**（`data/skills/`）即可。

### 10.4 PostgreSQL 支持是否保留 ✅ **已消解（第五轮反转）**
> ~~原建议「保留依赖与迁移脚本，本地默认 SQLite」~~
>
> **D4 后此问题不复存在**：PostgreSQL **就是本项目的主力数据库**，不存在"是否保留"的讨论。
> `psycopg[binary]` 保留在主依赖（`backend/pyproject.toml:15`），Alembic 脚本继续使用，**且本地也用它建表**。
>
> ⚠️ **一个教训**：这个问题在上一轮被包装成「不对称权衡，选可逆的那边」——听起来很理性，但它**在一个错误的前提下做选择**。
> 如果整个方向是错的，再漂亮的权衡分析也只是让错误看起来更有说服力。

### 10.5 施工前必须完成的调研（M1–M3）✅ **已消解**（M2/M3 完成 + D5 判定不迁移）
> **结案说明（2026-09-17）**：D1–D7 已全部完成，「施工前前置」的说法随之失效。
> - **M2 ✅**：现网 Milvus = `milvusdb/milvus:v2.6.14` **单容器内嵌 etcd + local 存储**（`D:\Milvus\standalone.bat` 独立 `docker run`）→ 已按此重写 `compose.override.yml`（D1.2，绑定挂载零迁移复用）
> - **M3 ✅**：本机 PG `18.3` 与 `postgres:18` 完全兼容，`pg_dump/restore` 可直接用
> - **M1 ➖ 失去必要性**：D5 盘点后**判定不迁移**（容器库为权威库、Milvus 走绑定挂载复用），「向量数据跨实例迁移」不再是被依赖的路径；备份齐全（`backups/20260917_095030/`）
> 以下为原始调研表，仅作历史留痕：
| 编号 | 待调研 | 为什么必须先做 | 归属 |
|---|---|---|---|
| **M1** | **Milvus 向量数据能否跨实例迁移**？现有 collection 如何导出/导入 | **决定 D5 的可行性**。若不能迁移，则 22 个知识库需**重新上传文档重建索引**（依赖 2 个原始文档是否还在） | D5 前置 |
| **M2** | **当前 Milvus 是怎么启动的**？etcd / MinIO 是独立容器还是内嵌 | 决定 `compose.yml` 里 Milvus 全家桶的写法；也决定迁移时数据卷在哪 | D1.2 前置 |
| **M3** | **本机 PG 版本**与 `postgres:18` 是否兼容 | 决定用 `pg_dump` / `pg_restore` 还是需要中间版本；**版本跨代可能有语法不兼容** | D5 前置 |

### 10.6 已确认的环境实况（本轮探测，供 D1–D5 参考）

| 项 | 实况 |
|---|---|
| Docker | ✅ 已装，可运行 |
| `milvus-standalone` | ✅ `Up 45 hours (healthy)`，镜像 `milvusdb/milvus:v2.6.14` |
| PostgreSQL | ⚠️ **本机安装版**（5432 监听进程 `postgres`，PID 9196）；另有 `full-stack-fastapi-template-db-1` 容器 **`Exited (255) 7 days ago`** |
| 开发数据 | `conversations: 126` / `messages: 108` / `knowledge_bases: 22` / `personas: 21` / `mcp_servers: 17` / `agent_runs: 20` / `documents: 2` / `user: 1` |
| 数据质量 | ⚠️ **22 个知识库只有 2 个文档** → 大量为测试空壳，D5 需先盘点 |
| API Key | ✅ `.env` 中 31 项配置齐全（含 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `OPENAI_API_KEY`） |

> ⚠️ **两套 PG 并存是个隐患**：一个是本机安装版（有开发数据），一个是已停 7 天的容器版。
> **D5 前必须确认到底哪个是"真的"** —— 搬错了就是搬了个空壳。

### 10.7 `astrbot-architecture.md` 同步 🔄 **需回滚（第五轮）**

该文档在**上一轮**被改为「SQLite 默认 / FAISS 本地默认」，**这一轮必须改回**：

| 位置 | 上一轮被误改为 | **本轮需回滚为** |
|---|---|---|
| 第七节选型表 · 数据库 | 「SQLite 默认」 | 「**PostgreSQL**（容器内；可配环境变量指向外部）」 |
| 第七节选型表 · 向量库 | 「FAISS 本地默认」 | 「**Milvus**（容器内，含 etcd + MinIO）」 |
| 第七节路线提醒 | 「IM 整体层整层不做；只吸收 Agent 能力栈」 | ✅ **保留**（这条是对的） |
| 第八节优先级 | 「P0 = 本地零依赖 + 工具开关 + 缓存淘汰」 | 「P0 = **Docker 化交付（D1–D7）** + 工具开关」 |

> **为什么这条重要**：`astrbot-architecture.md` 是 IrsBot 的**对标基准文档**。它自己的定位行若还写着已废弃的技术选型，将来读它的人会照着过期的基准做判断 —— 这比主计划的矛盾更隐蔽。
>
> **而且这次是反向污染**：上一轮我把它改错了，这一轮要改回来。**文档的错误是双向传播的**——不只是"忘了更新"，还包括"更新错了"。
