# 多租户 / 单用户运行时开关 实施计划

> 状态：**📝 待确认（v2，2026-09-18 修订）**——v1 的两个配置键砍掉一个，理由见 **第十一节**
> 日期：2026-09-18
> 关联：`plan/istbot-implement-plan.md`（D2 / D2.1）、`plan/PROGRESS.md`、`plan/local-deployment-plan.md`
> 前置提交：`41cccfd`（注册闸门）、`ef08cc1`（Provider 归属隔离）、`d1630f5`（D2 语义拆分文档同步）

---

## 一、背景

D2 决策把本地版定为**单用户**，落地方式是 `USERS_OPEN_REGISTRATION=false`（部署级 `.env`，
`41cccfd`）。用户随后指出：**不应把单用户写死**——管理员应能自行在「多租户」与「单用户」之间切换。

## 二、现状核查结论（2026-09-18 代码审查）

| 层 | 现状 | 结论 |
|---|---|---|
| **数据层** | `ProviderConfig` / `Conversation` / `Message` / `KnowledgeBase` / `Document` / `MCPServer` / `Persona` / `AgentRun` **全部**带 `user_id` + `ON DELETE CASCADE` | ✅ **已是完整多租户**，开关**不需要**新建任何归属结构 |
| **隔离逻辑** | `provider.py` 两条查找分支均带 `user_id` 过滤；`user_id=None` 时 fail closed；缓存键含 `user_id` | ✅ 安全边界**已实现**，两种模式下都必须保留 |
| **注册闸门** | `users.py:191` 读 `settings.USERS_OPEN_REGISTRATION`，守卫置于查重**之前**（防枚举） | 🔶 部署级、需重启，改为运行时 |
| **用户管理面** | `/admin` 页（超管可见）+ 侧边栏 Admin 入口 | ✅ 保留（见 §三 决策 2） |
| **运行时可配置机制** | **不存在**。所有开关都在 `Settings`（`.env`） | ❌ 需新建 |

**关键结论**：这个开关控制的是**策略**（谁能进系统），**不是代码路径**。
数据层的多租户能力一直都在，开关只决定「要不要对外开这个口子」。

## 三、需求确认（对应本轮三个决策）

| # | 决策点 | 用户选择 | 含义 |
|---|---|---|---|
| 1 | 开关载体 | **运行时开关（DB + `/admin` 页）** | 超管在网页上切换，立即生效，无需重启 |
| 2 | 「单用户模式」严格程度 | **仅关自助注册，超管仍可建号** | 单用户模式**不**禁止超管 `POST /users/`；因此 `/admin` 页与侧边栏入口**两种模式都保留** |
| 3 | 节奏 | **先写计划文档** | 本文档 → 确认后编码 |

> ⚠️ **决策 2 已经推翻过一次设计**：v1 初稿曾计划「单用户模式下隐藏 `/admin` 与侧边栏 Admin 入口」。
> 既然超管在单用户模式下仍需建号，`/admin` 必须可达 → 该隐藏逻辑取消。
> **决策 2 在 v2 又推翻了第二块**——它使 `deployment.mode` 变成空壳键，见 §四 与 §十一。

## 四、开关语义（权威定义）

### 4.1 系统里只有一个策略决策

**「匿名自助注册是否开放」**。除它以外，所有与「模式」相关的行为**恒定不变**：

- 超管始终可建号（`POST /users/`）
- `/admin` 页与侧边栏 Admin 入口始终保留
- 归属隔离始终按 `user_id`（Provider / KB / 会话 / MCP / 人设）
- 多账号始终可共存（开关不删也不冻结任何已有账号）

因此运行时配置**只有一键**：`users.open_registration`。

| 开关 | UI 呈现 | 行为 |
|---|---|---|
| **关**（默认） | 单用户模式 | `POST /users/signup` → 403；登录页无注册入口；超管仍可建号 |
| **开** | 多租户模式 | `POST /users/signup` 放行；登录页显示注册入口；超管仍可建号 |

> **「单用户 / 多租户」是呈现层标签，由这一个布尔派生**（`multi_tenant ⇔ open_registration=true`），
> 不是独立配置项。这样 UI 保留用户熟悉的词汇，但配置层不留空壳状态。

### 4.2 两个模式的行为对照

| 项 | 单用户（`open_registration=false`，默认） | 多租户（`open_registration=true`） |
|---|---|---|
| `POST /users/signup`（匿名自助注册） | **403** | **放行** |
| `POST /users/`（超管建号） | 允许 | 允许 |
| `GET /users/`（超管列用户） | 允许 | 允许 |
| `/admin` 页 + 侧边栏 Admin 入口 | **保留** | 保留 |
| 登录页「注册」链接 | 不显示 | 显示 |
| Provider / KB / 会话 / MCP / 人设 **归属隔离** | **按 `user_id`** | **按 `user_id`** |
| 已有账号 | 保留可登录，不自动删 | 保留可登录 |

**唯一行为差异就是注册闸门本身。** 这是刻意的——不把「运营功能」和「安全边界」再次归并到一起
（D2 语义拆分已踩过这个坑）。

## 五、技术方案

### 5.1 存储：新增 `app_settings` KV 表

| 字段 | 类型 | 说明 |
|---|---|---|
| `key` | `str` 主键 | 本次用到 `users.open_registration`；键名定义为模块常量，防手误拼出新键 |
| `value` | `str` | 统一按字符串存，读取时类型化 |
| `updated_at` | `datetime` | 便于审计 |

**为什么用通用 KV 而不是单行类型化表**：本项目开关会持续增加（`ENABLE_RAG`、`ENABLE_MCP`、
默认模型等未来都可能要运行时可调）。KV 表加一个键**不需要新迁移**；类型校验下沉到读取助手，
安全性等价。当前只用一键，属于「表稍重、但下一步零成本」的取舍。

**运行时键**：

| 键 | 取值 | DB 无记录时的兜底 |
|---|---|---|
| `users.open_registration` | `"true"` \| `"false"` | `settings.USERS_OPEN_REGISTRATION`（已有，默认 `False`） |

**兜底链的意义**：DB 里没有记录时行为**完全等同于当前已发布版本**——`.env` 说了算。
首次升级后系统行为零变化；现有 3 条注册闸门测试（monkeypatch `settings.USERS_OPEN_REGISTRATION`）
在测试用的干净 DB 下依然有效，不必改写。**KV 有记录时覆盖 `.env`**（运行时优先）。

**不做进程内缓存**：主键单行查询开销可忽略；引入缓存就要处理失效（多 worker / WS 进程各自持有副本），
收益为负。**明确决策：每次请求直读 DB。**（这也让「切换后立即生效」天然成立。）

### 5.2 后端改动

| # | 改动 | 文件 | 说明 |
|---|---|---|---|
| B1 | `AppSetting` 表模型 | `backend/app/core/db/models.py` | KV 三字段 |
| B2 | Alembic 迁移 | `backend/app/alembic/versions/<rev>_add_app_settings_table.py` | `create_table` / `drop_table` 对称 |
| B3 | ~~新增 `DEPLOYMENT_MODE` 配置项~~ | — | **v2 取消**：不再需要模式配置项；`USERS_OPEN_REGISTRATION` 继续作兜底初值 |
| B4 | 读取助手 | `backend/app/core/settings_runtime.py`（新建） | `get_setting` / `set_setting`；键名常量；`get_open_registration(session)`；**`signup_allowed(session)`**（唯一派生点，禁止别处重复判断） |
| B5 | Pydantic 模型 | `backend/app/core/db/sqlmodel_models.py` | `DeploymentSettingsPublic`（`open_registration` + **派生的** `mode` + `user_count`）、`DeploymentSettingsUpdate`（`open_registration: bool`）、`PublicSettings`（`open_registration: bool`） |
| B6 | 注册闸门改造 | `backend/app/api/routes/users.py` | 守卫改为 `if not signup_allowed(session):` —— **位置不变，仍在查重之前**（防枚举，沿用 `41cccfd` 的教训） |
| B7 | 公开端点 | `backend/app/api/routes/utils.py` | `GET /utils/public-settings` → `{open_registration}`。**匿名可读**：登录页渲染「注册」链接必须在校验身份前拿到它；只暴露这一位布尔（试一次注册请求即可得知，不构成额外泄露） |
| B8 | 超管端点 | `backend/app/api/routes/settings.py`（新建） | `GET /settings/deployment`（超管）→ 含 `user_count` 供前端提示；`PATCH /settings/deployment`（超管）→ 只改 `open_registration` |
| B9 | 路由注册 | `backend/app/api/main.py` | `api_router.include_router(settings.router)` |
| B10 | 环境变量样例 | `.env` / `.env.example` | 保留 `USERS_OPEN_REGISTRATION=false`，注释改为「**首次兜底值**；部署后以网页开关为准」 |

**PATCH 校验规则（v2 已大幅简化）**：

| 请求 | 结果 |
|---|---|
| `{"open_registration": true}` | 200，注册闸门即刻放开 |
| `{"open_registration": false}` | 200，注册闸门即刻关闭（已有账号不受影响） |
| 非布尔值 | 422（Pydantic 类型校验） |
| 非超管调用 | 403 |

> v1 曾需一条「单用户模式下试图开注册 → 400」的互斥校验；**v2 因不存在互斥组合而取消**。

### 5.3 前端改动

| # | 改动 | 文件 | 说明 |
|---|---|---|---|
| F1 | client 再生成 | 运行 `openapi-ts` | `frontend/src/client/` 自动更新 |
| F2 | 部署模式开关 | `frontend/src/components/Admin/DeploymentMode.tsx`（新建） | 两态段控件「单用户 / 多租户」——**切换即等于开/关自助注册**。开启时弹**二次确认**（见下）；`user_count > 1` 时切回单用户显示「已有 N 个账号仍可正常登录，仅不再接受新注册」 |
| F3 | `/admin` 页接入 | `frontend/src/routes/_layout/admin.tsx` | 「用户」标题下方插入 `<DeploymentMode />`（仍限超管——`beforeLoad` 已拦） |
| F4 | 登录页注册入口 | `frontend/src/routes/login.tsx` | 读 `open_registration`，为真时渲染「还没有账号？注册」链接（`f8ea244` 删掉的入口，改为**条件**恢复） |
| F5 | react-query hook | `frontend/src/hooks/useDeploymentSettings.ts`（新建） | `deploymentSettingsQuery` / `updateDeploymentSettings` / `publicSettingsQuery`；PATCH 成功后失效两个缓存 |
| F6 | 构建校验 | — | `tsc` + `vite build` 通过，重建 `frontend/dist` |

**关于二次确认**（替代 v1 的「双开关防误触」）：从单用户切到多租户后**任何人**都能注册账号并使用
你配置的模型源（消耗你的 API Key）。因此切换为「多租户」时弹确认框，文案写明这一点。
这比再加一个冗余开关更直接，也更有效。

> `frontend/src/routes/signup.tsx` **已存在**（当初只删了登录页链接，未删路由），无需新建。

### 5.4 生效链路

```
超管在 /admin 切换 → PATCH /settings/deployment → app_settings 表落库
                                                   ↓
下一次 POST /users/signup → signup_allowed(session) 直读 DB → 403 或放行   （无需重启）
下一次 打开登录页        → GET /utils/public-settings        → 显示/隐藏注册入口
```

## 六、执行顺序与提交划分

| 步骤 | 内容 | git 提交 |
|---|---|---|
| 1 | B1 + B2 表与迁移 | `feat(settings): app_settings 运行时配置表与迁移` |
| 2 | B4–B9 + 必做测试 | `feat(settings): 自助注册运行时开关（单用户/多租户）` |
| 3 | F1–F6 前端 | `feat(frontend): /admin 页部署模式开关与登录页注册入口` |
| 4 | 文档同步（§七） | `docs: 运行时注册开关纳入 D2 决策与进度记录` |

每步提交前：后端 `py_compile` + 相关 pytest；前端 `tsc` + `vite build`。
全程遵守 git 备份约定，出问题可 `git reset --hard <上一提交>` 回退。

## 七、文档同步清单（与本计划同批必做）

| 文档 | 需改内容 |
|---|---|
| `plan/istbot-implement-plan.md` | **D2.1 表述要改**：现写「注册入口默认关闭」是**硬约束**，须改为「默认关闭，可由超管在运行时开启」；新增 **D2.2** 运行时配置机制（`app_settings` + `/admin` 开关）；0.4 复用义务表补运行时可配置一节；一节能力矩阵、SC D10 措辞随之调整 |
| `plan/PROGRESS.md` | 当前阶段、第八节新增「运行时开关」小节、十一节追加进度记录 |
| `plan/local-deployment-plan.md` | D2 子阶段表的注册闸门行（`.env` → 运行时，`.env` 降为兜底初值） |
| `.env` / `.env.example` | `USERS_OPEN_REGISTRATION` 注释改为「首次兜底值」 |
| `.workbuddy/memory/MEMORY.md` | D2 决策行、新增「运行时可配置机制」约定 |

> ⚠️ 这已是 D2 相关表述的**第三次**修订（`41cccfd` → `d1630f5` → 本次）。
> 根因是需求在演进，属预期；但每次都必须**反向 grep 回查**，确认没有遗留「写死 / 方向相反」的表述。

## 八、测试与验收清单

**自动化（沙箱可做）**：

- [ ] `py_compile` 全部改动文件
- [ ] 迁移链校验：`upgrade` / `downgrade` 对称；在已有数据上 dry-run 无副作用
- [ ] 前端 `tsc` + `vite build`
- [ ] 后端测试（**必做**，项目规则：All API endpoints must have corresponding test cases）：
  - `settings_runtime`：KV 读写；键缺失 → 兜底取 `.env`
  - **优先级矩阵（4 组，锁住「KV 覆盖 .env」这一关键语义）**：
    - KV 无记录 + `USERS_OPEN_REGISTRATION=false` → **403**
    - KV 无记录 + `USERS_OPEN_REGISTRATION=true` → **200**（兜底链生效）
    - KV=`true` + `USERS_OPEN_REGISTRATION=false` → **200**（KV 覆盖 `.env`）
    - KV=`false` + `USERS_OPEN_REGISTRATION=true` → **403**（KV 覆盖 `.env`）
  - **防枚举回归**：关闭态下，已存在邮箱与不存在邮箱的 403 响应**逐字节一致**（沿用 `41cccfd` 断言）
  - `GET /utils/public-settings`：匿名可读 200；开 → `true`；关 → `false`
  - `GET /settings/deployment`：超管 200 / 普通用户 403 / 匿名 401；`mode` 字段与 `open_registration` 一致
  - `PATCH /settings/deployment`：超管改 200 且**立即影响** `POST /users/signup`；非超管 403；非布尔值 422
  - **现有 3 条注册闸门测试**（monkeypatch `settings.USERS_OPEN_REGISTRATION`）应保持通过（兜底链生效）

**实机（用户 Windows 机器，`docker compose up -d --build backend` 后）**：

1. 默认状态：`/admin` → 显示「单用户模式」；`POST /users/signup` → 403
2. 切「多租户」（确认框）→ 退出登录 → 登录页出现「注册」链接 → 完成一次注册 → 新账号可登录
3. 新账号进「设置」→ 只看得到自己创建的 Provider（看不到 admin 的）→ **归属隔离未被动摇**
4. 切回「单用户」→ 注册链接消失、`POST /users/signup` → 403 → 已有 2 个账号仍可正常登录
5. 回归：Provider 五项（§10.6）、系统提示词、RAG 问答不受影响

## 九、风险与回退

| 风险 | 缓解 |
|---|---|
| 运行时开关被误解为「关掉隔离」 | §四 明确：归属隔离**不随开关变**；`signup_allowed` 是**唯一**判断点，禁止各处自行拼条件 |
| 误开自助注册（一次点击即对外开放） | UI 二次确认（写明「任何人可注册并消耗你的 API Key」）+ 超管专属 + 开启后登录页立刻可见，易于发现 |
| 公开端点泄露部署信息 | 只暴露 `open_registration` 一位布尔；此项本身可由「试一次注册」得知，不构成额外泄露 |
| 多 worker / WS 进程读到不一致的开关 | 不缓存，每请求直读 DB → 天然一致 |
| 切换后立即生效导致会话中途行为变化 | 开关只影响**新建请求**（注册、链接渲染），不影响进行中的会话 |
| 回退 | 每步独立提交；整功能回退：`git reset --hard <步骤1前 HEAD>` + `alembic downgrade -1`（drop 表）。**表删掉后行为自动回落到 `.env`，等同当前已发布版本**，无残留 |

---

## 十、待确认项（编码前请拍板）

1. **砍掉 `deployment.mode`**（v2 核心修订）：把「单用户/多租户」降为**呈现层标签**，配置层只保留 `open_registration`
   一键。理由 = 你的决策 2 使两个键的组合出现**完全等效的冗余状态**（详见 §十一）。是否接受？
2. **公开端点**：`GET /utils/public-settings` 匿名可读（只返回 `open_registration`）是否接受？
3. **入口位置**：开关放在 `/admin`（用户管理页，本来就只有超管能进）是否合适？还是放到「设置」页做成超管专属 tab？
4. **文档改动**：`istbot-implement-plan.md` 的 **D2.1 要从「硬约束」改回「默认关闭 + 可运行时开启」**，确认可改？

## 十一、修订记录（v1 → v2）

### v1 设计与它的问题

v1 设两个运行时键：

```
deployment.mode            : "single_user" | "multi_tenant"
deployment.open_registration : bool
signup_allowed = (mode == "multi_tenant") AND open_registration
```

配套：`settings.DEPLOYMENT_MODE` 新增配置项；「单用户下试图开注册 → 400」的互斥校验。

**问题**：因为决策 2（单用户模式下超管仍可建号），`mode` 既不约束超管建号、也不约束 `/admin` 可见性，
于是出现**完全等效的冗余状态**：

| | 单用户（`mode=single_user`） | 多租户 + 关注册（`mode=multi_tenant`, `open_registration=false`） |
|---|---|---|
| `POST /users/signup` | 403 | 403 |
| 超管建号 / `/admin` 可见 | 允许 / 是 | 允许 / 是 |
| 归属隔离 | 按 `user_id` | 按 `user_id` |

两者在所有可观测行为上**完全等同**。设置页会出现两个产出相同结果的档位——读设置的人无法判断该选哪个，
维护者也会误以为 `mode` 还管着什么。**冗余状态比缺失状态更危险**：它让人以为存在一道其实不存在的约束。

### v2 处置

| 项 | v1 | v2 |
|---|---|---|
| 配置键 | 2 个（`mode` + `open_registration`） | **1 个**（`users.open_registration`） |
| `mode` | 独立配置项 | **呈现层标签**，由布尔派生 |
| 派生规则 | `AND` 复合，成为「唯一判断点」 | 直读布尔，简化 |
| 互斥校验（400） | 需要 | **取消**（不存在互斥组合） |
| `settings.DEPLOYMENT_MODE` | 新增 | **不新增** |
| 「防误触」手段 | 双开关（需两步） | 单开关 + **二次确认对话框** |

### 什么情况下 `mode` 会重新变成真开关

若将来需要**「多用户 + 仅管理员建号」**（企业内部分发账号的常见场景），`mode` 才有真实语义
（约束超管建号、或限制自助注册以外的入口）。届时**在 KV 表加一个键即可，零迁移**——这正是选 KV 表的收益。
现在不做，因为**现在它是空壳**。
