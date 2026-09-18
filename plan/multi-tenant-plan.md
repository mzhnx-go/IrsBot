# 多租户 / 单用户运行时开关 实施计划

> 状态：**📝 待确认（计划阶段，未编码）**
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
| **用户管理面** | `/admin` 页（超管可见）+ 侧边栏 Admin 入口 | ✅ 保留（见 §3 决策 2） |
| **运行时可配置机制** | **不存在**。所有开关都在 `Settings`（`.env`） | ❌ 需新建 |

**关键结论**：这个开关控制的是**策略**（谁能进系统、注册是否开放），**不是代码路径**。
数据层的多租户能力一直都在，开关只是决定「要不要用它」。

## 三、需求确认（对应本轮三个决策）

| # | 决策点 | 用户选择 | 含义 |
|---|---|---|---|
| 1 | 开关载体 | **运行时开关（DB + `/admin` 页）** | 超管在网页上切换，立即生效，无需重启 |
| 2 | 「单用户模式」严格程度 | **仅关自助注册，超管仍可建号** | 单用户模式**不**禁止超管 `POST /users/`；因此 `/admin` 页与侧边栏入口**两种模式都保留** |
| 3 | 节奏 | **先写计划文档** | 本文档 → 确认后编码 |

> ⚠️ **决策 2 修正了初稿设想**：初稿曾计划「单用户模式下隐藏 `/admin` 与侧边栏 Admin 入口」。
> 既然超管在单用户模式下仍需建号，`/admin` 必须可达 → **该隐藏逻辑取消**。

## 四、开关语义（权威定义）

两个开关，一组派生规则：

```
signup_allowed = (deployment.mode == "multi_tenant") AND open_registration
```

| 项 | 单用户（默认） | 多租户 |
|---|---|---|
| `POST /users/signup`（匿名自助注册） | **403**（无条件） | 由 `open_registration` 决定 |
| `POST /users/`（超管建号） | **允许** | 允许 |
| `GET /users/`（超管列用户） | 允许 | 允许 |
| `/admin` 页 + 侧边栏 Admin 入口 | **保留** | 保留 |
| 登录页「注册」链接 | 不显示 | 仅 `open_registration=true` 时显示 |
| Provider / KB / 会话 / MCP / 人设 **归属隔离** | **按 `user_id`（不变）** | **按 `user_id`（不变）** |
| 已有账号 | 保留可登录，不自动删 | 保留可登录 |

**两个模式之间唯一的行为差异**：自助注册是否**有可能**被打开。这是刻意的——其余一切（尤其是归属隔离）
两模式一致，避免把「运营功能」和「安全边界」再次归并到一起（D2 语义拆分已踩过这个坑）。

## 五、技术方案

### 5.1 存储：新增 `app_settings` KV 表

| 字段 | 类型 | 说明 |
|---|---|---|
| `key` | `str` 主键 | 如 `deployment.mode` |
| `value` | `str` | 统一按字符串存，读取时类型化 |
| `updated_at` | `datetime` | 便于审计 |

**为什么用通用 KV 而不是单行类型化表**：本项目的开关会持续增加（`ENABLE_RAG`、`ENABLE_MCP` 等
未来都可能要运行时可调）。KV 表加一个键**不需要新迁移**；类型校验下沉到读取助手，安全性与类型化表等价。

**运行时键**：

| 键 | 取值 | DB 无记录时的兜底 |
|---|---|---|
| `deployment.mode` | `"single_user"` \| `"multi_tenant"` | `settings.DEPLOYMENT_MODE`（**新增**，默认 `"single_user"`） |
| `deployment.open_registration` | `"true"` \| `"false"` | `settings.USERS_OPEN_REGISTRATION`（已有，默认 `False`） |

**兜底链的意义**：DB 里没有记录时行为**完全等同于当前已发布版本**——`.env` 说了算。
这样首次升级后系统行为零变化；现有 3 条注册闸门测试（monkeypatch `settings.USERS_OPEN_REGISTRATION`）
在测试用的干净 DB 下依然有效，不必改写。

**不做进程内缓存**：主键单行查询开销可忽略；引入缓存就要处理失效（多 worker / WS 进程各自持有副本），
收益为负。**明确决策：每次请求直读 DB。**

### 5.2 后端改动

| # | 改动 | 文件 | 说明 |
|---|---|---|---|
| B1 | `AppSetting` 表模型 | `backend/app/core/db/models.py` | KV 三字段 |
| B2 | Alembic 迁移 | `backend/app/alembic/versions/<rev>_add_app_settings_table.py` | `create_table` / `drop_table` 对称 |
| B3 | 配置项 | `backend/app/core/config.py` | 新增 `DEPLOYMENT_MODE: Literal["single_user","multi_tenant"] = "single_user"`；置于 `USERS_OPEN_REGISTRATION` 邻近并补注释 |
| B4 | 读取助手 | `backend/app/core/settings_runtime.py`（新建） | `get_setting` / `set_setting`；`get_deployment_mode(session)` / `get_open_registration(session)` / **`signup_allowed(session)`**（唯一派生点，禁止别处重复拼条件） |
| B5 | Pydantic 模型 | `backend/app/core/db/sqlmodel_models.py` | `DeploymentSettingsPublic`（`mode` / `open_registration` / `signup_allowed` / `user_count`）、`DeploymentSettingsUpdate`（两个字段均可选）、`PublicSettings`（`signup_enabled: bool`） |
| B6 | 注册闸门改造 | `backend/app/api/routes/users.py` | 守卫改为 `if not signup_allowed(session):` —— **位置不变，仍在查重之前**（防枚举，沿用 `41cccfd` 的教训） |
| B7 | 公开端点 | `backend/app/api/routes/utils.py` | `GET /utils/public-settings` → `{signup_enabled}`。**匿名可读**：登录页渲染「注册」链接必须在校验身份前拿到它；只暴露这一位布尔（试一次注册请求即可得知，不构成额外泄露） |
| B8 | 超管端点 | `backend/app/api/routes/settings.py`（新建） | `GET /settings/deployment`（超管）→ 含 `user_count` 供前端提示；`PATCH /settings/deployment`（超管）→ 改 mode / open_registration |
| B9 | 路由注册 | `backend/app/api/main.py` | `api_router.include_router(settings.router)` |
| B10 | 环境变量样例 | `.env` / `.env.example` | 补 `DEPLOYMENT_MODE=single_user` + 注释说明「首次部署兜底值，之后以网页开关为准」 |

**PATCH 校验规则**：

| 请求 | 结果 |
|---|---|
| `{"mode": "multi_tenant"}` | 200 |
| `{"mode": "single_user"}`（当前 2 个账号） | 200，响应带 `user_count`，仅阻止**新建**账号，不删已有 |
| `{"mode": "single_user", "open_registration": true}` | **400**，提示「单用户模式下无法开放自助注册，请先切换到多租户」 |
| `{"open_registration": true}`（当前单用户） | **400**，同上 |
| 非法 `mode` 值 | 422（Pydantic `Literal` 校验） |
| 非超管调用 | 403 |

### 5.3 前端改动

| # | 改动 | 文件 | 说明 |
|---|---|---|---|
| F1 | client 再生成 | 运行 `openapi-ts` | `frontend/src/client/` 自动更新 |
| F2 | 部署模式卡片 | `frontend/src/components/Admin/DeploymentMode.tsx`（新建） | 单选段控件「单用户 / 多租户」+「允许自助注册」Switch；`mode==single_user` 时 Switch **禁用**并提示「需先切换到多租户模式」；`user_count > 1` 且切到单用户时显示「当前存在 N 个账号，单用户模式下不再允许自助注册」 |
| F3 | `/admin` 页接入 | `frontend/src/routes/_layout/admin.tsx` | 「用户」标题下方插入 `<DeploymentMode />`（仍限超管——`beforeLoad` 已拦） |
| F4 | 登录页注册入口 | `frontend/src/routes/login.tsx` | 读 `signup_enabled`，为真时渲染「还没有账号？注册」链接（`f8ea244` 删掉的入口，改为**条件**恢复） |
| F5 | react-query hook | `frontend/src/hooks/useDeploymentSettings.ts`（新建） | `deploymentSettingsQuery` / `updateDeploymentSettings` / `publicSettingsQuery`；PATCH 成功后失效两个缓存 |
| F6 | 构建校验 | — | `tsc` + `vite build` 通过，重建 `frontend/dist` |

> `frontend/src/routes/signup.tsx` **已存在**（当初只删了登录页链接，未删路由），无需新建。

### 5.4 生效链路

```
超管在 /admin 切换 → PATCH /settings/deployment → app_settings 表落库
                                                  ↓
下一次 POST /users/signup → signup_allowed(session) 直读 DB → 403 或放行   （无需重启）
下一次 打开登录页        → GET /utils/public-settings        → 显示/隐藏注册链接
```

## 六、执行顺序与提交划分

| 步骤 | 内容 | git 提交 |
|---|---|---|
| 1 | B1 + B2 表与迁移 | `feat(settings): app_settings 运行时配置表与迁移` |
| 2 | B3–B9 + 必做测试 | `feat(settings): 部署模式运行时开关（单用户/多租户）` |
| 3 | F1–F6 前端 | `feat(frontend): /admin 页部署模式开关与登录页注册入口` |
| 4 | 文档同步（§七） | `docs: 部署模式开关纳入 D2 决策与进度记录` |

每步提交前：后端 `py_compile` + 相关 pytest；前端 `tsc` + `vite build`。
全程遵守 git 备份约定，出问题可 `git reset --hard <上一提交>` 回退。

## 七、文档同步清单（与本计划同批必做）

| 文档 | 需改内容 |
|---|---|
| `plan/istbot-implement-plan.md` | **D2.1 表述要改**：现写「注册入口默认关闭」是**硬约束**，须改为「由运行时开关控制，默认关闭」；新增 **D2.2** 部署模式运行时开关（单用户/多租户，默认单用户）；0.4 复用义务表补运行时开关一节；一节能力矩阵、SC D10 措辞随之调整 |
| `plan/PROGRESS.md` | 当前阶段、第八节新增「部署模式开关」小节、十一节追加进度记录 |
| `plan/local-deployment-plan.md` | D2 子阶段表的注册闸门行（.env → 运行时） |
| `.env` / `.env.example` | `DEPLOYMENT_MODE` 与注释 |
| `.workbuddy/memory/MEMORY.md` | D2 决策行、新增「运行时可配置机制」约定 |

> 这已是 D2 相关表述的**第三次**修订（`41cccfd` → `d1630f5` → 本次）。
> 根因是需求在演进，属预期；但每次都必须**反向 grep 回查**，确认没有遗留「写死 / 方向相反」的表述。

## 八、测试与验收清单

**自动化（沙箱可做）**：

- [ ] `py_compile` 全部改动文件
- [ ] 迁移链校验：`upgrade` / `downgrade` 对称；在已有数据上 dry-run 无副作用
- [ ] 前端 `tsc` + `vite build`
- [ ] 后端测试（**必做**，项目规则：All API endpoints must have corresponding test cases）：
  - `settings_runtime`：KV 读写；DB 无记录 → 兜底取 `.env`；`signup_allowed` 派生
  - **`signup_allowed` 组合矩阵（4 组）**：
    - 单用户 + `open_registration=false` → 403
    - 单用户 + `open_registration=true`（**绕过 API 直写 KV**）→ **仍 403**（证明读的是派生值而非裸 KV，双保险有效）
    - 多租户 + `open_registration=false` → 403
    - 多租户 + `open_registration=true` → **200 建号成功**
  - **防枚举回归**：单用户下，已存在邮箱与不存在邮箱的 403 响应**逐字节一致**（沿用 `41cccfd` 断言）
  - `GET /utils/public-settings`：匿名可读 200；单用户 → `signup_enabled=false`；多租户+开 → `true`
  - `GET /settings/deployment`：超管 200 / 普通用户 403 / 匿名 401
  - `PATCH /settings/deployment`：超管改 mode 200；单用户下开注册 400；非法 mode 422；普通用户 403
  - **现有 3 条注册闸门测试**（monkeypatch `settings.USERS_OPEN_REGISTRATION`）应保持通过（兜底链生效）

**实机（用户 Windows 机器，`docker compose up -d --build backend` 后）**：

1. 默认状态：`/admin` → 显示「单用户」；`POST /users/signup` → 403
2. 切「多租户」→ 打开「允许自助注册」→ 退出登录 → 登录页出现「注册」链接 → 完成一次注册 → 新账号可登录
3. 新账号进「设置」→ 只看得到自己创建的 Provider（看不到 admin 的）→ **归属隔离未被开关破坏**
4. 切回「单用户」→ 注册链接消失 → `POST /users/signup` → 403 → 已有 2 个账号仍可正常登录
5. 「单用户」下试图打开注册开关（若 UI 未禁用）→ 400 + 明确提示
6. 回归：Provider 五项（§10.6）、系统提示词、RAG 问答不受影响

## 九、风险与回退

| 风险 | 缓解 |
|---|---|
| 运行时开关被误解为「关掉隔离」 | §四 明确：归属隔离**两模式都不变**；`signup_allowed` 是**唯一**派生点，禁止各处自行拼条件 |
| 单用户模式误开自助注册 | 双重保险：UI 禁用 + 后端 PATCH 400 + `signup_allowed` 用 AND 派生（即使 KV 被手工写脏也不会开） |
| 公开端点泄露部署信息 | 只暴露 `signup_enabled` 一位布尔；此项本身可由「试一次注册」得知，不构成额外泄露 |
| 多 worker / WS 进程读到不一致的模式 | 不缓存，每请求直读 DB → 天然一致 |
| 切换后立即生效导致会话中途行为变化 | 开关只影响**新建请求**（注册/链接渲染），不影响进行中的会话 |
| 回退 | 每步独立提交；整功能回退：`git reset --hard <步骤1前 HEAD>` + `alembic downgrade -1`（drop 表）。**表删掉后行为自动回落到 `.env`，等同当前已发布版本**，无残留 |

---

## 十、待确认项（编码前请拍板）

1. **表形态**：`app_settings` 通用 KV（本文推荐） vs 单行类型化表。选 KV 的理由是后续加运行开关不必再写迁移。
2. **公开端点**：`GET /utils/public-settings` 匿名可读（只返回 `signup_enabled`）是否接受？
3. **PATCH 校验**：单用户模式下尝试开注册 → **400 明确报错**（本文推荐） vs 静默忽略并回落 false。
4. **`/admin` 保留**：因决策 2（超管仍可建号），两模式下 `/admin` 与侧边栏入口**都保留**——确认？
5. **文档改动**：`istbot-implement-plan.md` 的 **D2.1 要从「硬约束」改回「运行时开关默认关」**（当初 `41cccfd` 的表述会被本次削弱），确认可改？
