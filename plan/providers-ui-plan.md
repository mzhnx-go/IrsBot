# 模型供应商界面 AstrBot 风格改造任务文档

> 版本：v1 ｜ 日期：2026-09-21
> 参照：AstrBot「模型提供商」页截图（顶部能力 Tab + 左列表右详情主从布局 + 高级配置 + 模型区）
> 范围：**纯前端改造**（新功能的后端能力均占位待实现，界面代码注释标明）
> 约定：**每完成一个小功能提交一次**，方便回退

---

## 一、需求拆解

| # | 需求 | 来源 | 性质 |
|---|---|---|---|
| R1 | 顶部能力 Tab 栏：对话 / 语音转文字 / 文字转语音 / 嵌入 / 重排序 | 截图 1 | 「对话」为现有功能；**其余四项占位待实现**（禁用态 + tooltip + 代码注释） |
| R2 | 主从两栏布局：左侧「模型源」列表卡片，右侧详情面板；未选中时显示「请选择一个模型源」空态 | 截图 1 | 纯布局 |
| R3 | 左列表卡片：供应商名 + API 地址 + 删除入口 + 查余额（含结果）；选中高亮 | 截图 1 | 迁移现有功能 |
| R4 | 右详情面板「设置」区：名称 / 类型 / API Key（可切换明文 + 「添加更多」占位）/ API 地址 / 模型名 / 默认源 / 视觉能力；**保存配置**按钮接现有 `updateProvider` | 截图 2 | 现有功能重排版 |
| R5 | 「高级配置…」区：超时时间 / 代理地址 / 自定义请求头 | 截图 2 | **前端占位待实现**（不接后端） |
| R6 | 「模型」区：可用模型数 / 搜索模型 / 获取模型列表 / 自定义模型 | 截图 2 | **前端占位待实现** |
| R7 | 每完成一个小功能提交一次 | 用户要求 | 流程 |

## 二、兼容性红线（改造中不许破坏）

1. e2e `agent-pages.spec.ts`：`/providers` 页 heading「模型源」；`provider-row` 每卡片含 `provider-balance-button`，行内 `provider-balance-result`；按 base_url 文本定位行。→ **查余额按钮与结果、base_url 文本必须留在左列表卡片内**。
2. `onboarding.spec.ts` / 聊天空态引导：`/providers?new=1` 自动打开「新增模型源」弹窗 → 保留该逻辑。
3. 现有写操作全部保留：新增 / 删除（确认弹窗）/ 设为默认 / 视觉能力三态 / 查余额（enabled=false 显式查询范式）。

## 三、实施阶段（每阶段一笔提交）

| 阶段 | 内容 | 提交信息 |
|---|---|---|
| **P0** | 本任务文档 | `docs(providers-ui): AstrBot 风格改造任务文档` |
| **P1** | 能力 Tab 栏 + 主从两栏布局：左列表卡片（含查余额/删除/默认徽标），右详情「设置」区接 `updateProvider`（保存配置）；空态「请选择一个模型源」；`?new=1` 保留 | `feat(providers-ui): 能力 Tab 栏 + 主从两栏布局 + 详情设置区` |
| **P2** | 「高级配置…」占位区：超时时间 / 代理地址 / 自定义请求头（禁用态，代码注释 `TODO: 待实现`） | `feat(providers-ui): 高级配置占位区（待实现）` |
| **P3** | 「模型」占位区：可用模型数 / 搜索框 / 获取模型列表 / 自定义模型（禁用态占位） | `feat(providers-ui): 模型区占位（待实现）` |
| **P4** | e2e 适配确认 + 构建 + 实机验收 + PROGRESS.md 留档 | `docs(progress): 模型供应商界面改造留档` |

## 四、风险与坑位

| # | 坑 | 应对 |
|---|---|---|
| 1 | e2e 按行定位依赖 base_url 文本与行内余额按钮 | 左卡片保留 `provider-row` / `provider-balance-*` testid 与 base_url 文案 |
| 2 | `?new=1` 自动开弹窗逻辑别丢 | `AddProviderDialog initialOpen` 原样保留 |
| 3 | API Key 明文不可回显（后端只写不读） | 详情面板 Key 输入框留空占位「已加密存储，留空则不修改」——**留空不提交**；只有输入新值才进 PATCH |
| 4 | routeTree 由 vite 生成，改路由文件先 `npx vite build` | 本次不动路由文件，仅组件内部重构 |
| 5 | 「语音转文字」等四 Tab 无后端能力 | 禁用态 + title 提示 + 代码注释，避免用户误以为可配置 |

## 五、验收标准

1. 版式与 AstrBot 截图一致：顶部 Tab、左列表右详情、空态文案、设置/高级配置/模型三分区；
2. 现有功能全部可用：新增/删除/设默认/视觉/查余额/保存配置；
3. 四个占位 Tab 与高级配置、模型区明确标注「待实现」；
4. e2e 全绿（agent-pages / onboarding），tsc + vite build 通过，实机 8000 验收。

> ✅ **P0–P4 已全部完成（2026-09-21，提交链 `5708966 → 00504df`）。**
> 以下为**未完成部分的实施文档**——界面上所有「待实现」占位的落地设计。

---

## 六、未完成部分实施文档（P5–P9）

> 原则：每阶段独立提交、可单独回退；后端先行（迁移 + 端点 + 测试），前端解除占位。
> 前端占位位置全部带 `TODO(待实现)` 注释，grep `TODO(待实现)` 可列出全部接线点。

### P5 供应商能力维度（四个占位 Tab 的后端地基）

**目标**：让「语音转文字 / 文字转语音 / 嵌入 / 重排序」成为真实的供应商类别。

| 项 | 设计 |
|---|---|
| 数据模型 | `ProviderConfig` 新增 `capability` 列（`chat` / `stt` / `tts` / `embedding` / `rerank`），**默认 `chat`** 兼容存量数据；迁移 `add_provider_capability` |
| 默认源互斥 | 现 `is_default` 部分唯一索引升级为 `(user_id, capability)` 维度——每种能力各自一条默认（迁移前先按组去重，参照 `e7f8a9b0c1d2` 的做法） |
| API | 列表/新增/PATCH 全部带 `capability` 过滤；`GET /providers?capability=embedding` |
| 嵌入的存量迁移 | 现在 embedding 用 `.env` 的 `EMBEDDING_API_KEY/BASE_URL/MODEL`（RAG 链路）。迁移策略：**读时兼容**——RAG 先查 `capability=embedding` 的默认 Provider，查不到回落 `.env` 配置；`.env` 两个值都在时启动横幅提示可迁移 |
| 前端接线 | `CAPABILITY_TABS` 的 `enabled` 改为真值；`useProviders` 查询参数化 `capability`；Tab 切换换列表缓存 key（`["providers", capability]`）；各 Tab 的「新增」弹窗带 capability 字段（隐藏无关的视觉能力行） |
| 验收 | 每类能力可独立增删改查 + 设默认；chat 存量行为零变化（回归 e2e） |

### P6 高级配置（超时 / 代理 / 自定义请求头）

**目标**：详情面板「高级配置…」三行从禁用态转为可用，随「保存配置」提交。

| 项 | 设计 |
|---|---|
| 数据模型 | `ProviderConfig` 新增三列：`timeout_seconds: int = 120`、`proxy_url: str = ""`、`extra_headers: JSON = {}`；迁移 `add_provider_advanced_config` |
| 生效点 | ① `ProviderManager.get_chat_model` → httpx 客户端 `timeout=`；② 代理：openai 兼容客户端传 `http_client=httpx.Client(proxy=...)`（注意 **Docker 容器内 `127.0.0.1` 不通宿主机**，描述文案已写明）；③ 请求头：`default_headers` 合并 |
| 脱敏 | `extra_headers` 里可能放鉴权头 → 展示层复用 `core/logging.py` 的 `redact()`；入库前不脱敏（原值要用） |
| 校验 | `timeout_seconds` 5–600；`proxy_url` 必须 `http(s)://`；headers 值必须字符串（AstrBot 同款约定） |
| 前端接线 | 三个 `disabled` 移除 → 受控输入进表单 state；`保存配置` 一并 PATCH；「修改」按钮弹 headers 键值对编辑小弹窗（空值行可增删） |
| 验收 | 改超时后对慢上游生效；代理生效（可用本地假代理验证）；headers 合并进请求（echo 服务验证）；单测覆盖校验边界 |

### P7 模型管理（获取模型列表 / 自定义模型）

**目标**：详情面板「模型」区从占位转为真实的每供应商模型清单。

| 项 | 设计 |
|---|---|
| 数据模型 | 新表 `provider_models`：`id / provider_id / model_id(str) / display_name / capability / created_at`；`(provider_id, model_id)` 唯一 |
| 获取模型列表 | `POST /providers/{id}/models/fetch`：后端用该源 Key 透传上游 `GET /models`（openai 兼容；anthropic/gemini 各自适配），**upsert** 进表并返回数量；上游不可达 → 中文错误提示（复用 `provider_balance` 的错误映射风格） |
| 自定义模型 | `POST /providers/{id}/models`（手填 model_id + 显示名）、`DELETE /providers/{id}/models/{mid}` |
| 默认模型切换 | 「设置」区的 `model_name` 升级为从 `provider_models` 下拉选择（保留手填兜底）；对话取 `capability=chat` 默认源的默认模型 |
| 前端接线 | 「获取模型列表」按钮接 fetch 端点（显式动作、不自动拉，参照查余额的 `enabled:false` 范式）；搜索框做本地过滤；列表行支持删除 |
| 验收 | 对 Agnes（openai 兼容）实拉模型列表成功；自定义模型增删生效；对话用新默认模型 |

### P8 多 API Key（「添加更多」按钮）

**目标**：同一供应商多把 Key，自动轮换。

| 项 | 设计 |
|---|---|
| 数据模型 | 新表 `provider_keys`：`id / provider_id / encrypted_key / is_active / last_used_at / fail_count`；现 `provider_configs.api_key` 迁移为首行 |
| 轮换策略 | 顺序轮换（按 `last_used_at` 最旧优先）；请求失败（401/403/429）`fail_count += 1`，连败 3 次冷却 5 分钟；全部冷却时如实报错 |
| 影响面 | `ProviderManager.get_chat_model`、`provider_balance`、`model fetch` 三处取 Key 的入口统一改为 `resolve_key(provider_id)` |
| 前端接线 | 「添加更多」弹小窗批量粘贴（一行一个 Key）；列表显示打码 Key（`sk-***abc1`）与状态；可停用/删除单把 |
| 验收 | 两把 Key 轮流使用（日志可证）；一把失效自动切换；加密落库（`enc:v1:`） |

### P9 其他三类能力的 Agent 集成（Tab 放开的前置）

- **嵌入**：RAG 的 `EmbeddingClient` 从 Provider 体系取默认 `capability=embedding` 源（P5 已铺）；重排序同理 `capability=rerank`（现 `ENABLE_RERANK` 走 SiliconFlow env）。
- **语音转文字**：聊天输入框新增语音按钮 → 录音上传 → `POST /agent/audio/transcriptions`（后端调 STT 上游）；需浏览器 `MediaRecorder` 权限流程。
- **文字转语音**：回复气泡加「朗读」按钮 → `POST /agent/audio/speech` → 前端 `Audio` 播放；流式场景先整段后合成（不做流式 TTS，复杂度不划算）。
- **每项独立提交**，Tab `enabled` 在对应能力可用的那一刻放开。

### 优先级与依赖

```
P5（能力维度）──→ P9（三类能力集成，可按 STT→TTS→Embedding/Rerank 逐个做）
P6（高级配置）、P7（模型管理）、P8（多 Key）三者互不依赖，可并行，
均只依赖现有 ProviderConfig（P5 的迁移最好先做，避免两次改表）
```

建议顺序：**P5 → P7 → P6 → P8 → P9**（P7 用户感知最强、实现最小；P8 涉及密钥子表最重，放后）。

