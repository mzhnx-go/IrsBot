# AstrBot 架构与功能分析（IrsBot 对标基准）

> 分析对象：`D:\AstrbotSourceCode\AstrBot-master`（AstrBot 源码）
> 用途：作为 IrsBot 复刻工作的功能基准与架构参照
> 分析时间：2026-09-16
>
> **IrsBot 定位（2026-09-16 最新，第五轮修正）**：**本地部署的 AI Agent 应用，单用户使用，Docker 一条命令启动**。用户在**浏览器里对话**（Web 是产品主体，不是控制台），接入自己的 API Key，具备 Skill / Tool / MCP / RAG 能力。
> **不接 IM**（平台适配器 / 消息事件 / 插件体系整体不做）；**不做网页版**（多用户线上部署已拆分到另一个独立项目）。
> 本文件的取舍判断均基于此定位，实施计划见 [istbot-implement-plan.md](./istbot-implement-plan.md)，本地化施工详案见 [local-deployment-plan.md](./local-deployment-plan.md)。

---

## 一、总体分层

AstrBot 是**单进程、单实例、无 DI 容器**的异步应用。组件全部挂在生命周期对象上，通过全局单例 + `Context` 门面暴露给插件。

| 层 | 位置 | 职责 |
|---|---|---|
| 入口层 | `cli/__main__.py` → `cli/commands/cmd_run.py` | `FileLock` 防多实例 → `asyncio.run(run_astrbot())` |
| 编排层 | `core/initial_loader.py` → `core/core_lifecycle.py` | `AstrBotCoreLifecycle.initialize()/start()`；与 Dashboard 用 `asyncio.gather` 并存 |
| 全局单例 | `core/__init__.py` | `astrbot_config`、`logger`、`db_helper`、`sp`(SharedPreferences)、`html_renderer`、`file_token_service` |
| 接入层 | `core/platform/` | `Platform(ABC)` + `PlatformManager` + 18 个平台适配器 + 内置 `WebChatAdapter` |
| 总线层 | `core/event_bus.py` | `asyncio.Queue` + 单消费者 `dispatch()`，按 UMO 路由到对应 `PipelineScheduler` |
| 管线层 | `core/pipeline/` | 9 个 Stage 的**洋葱模型**编排（`stage_order.STAGES_ORDER`） |
| 处理层 | `pipeline/process_stage/` | 插件路径 / 本地 Agent / 第三方 Agent 三路分发 |
| 引擎层 | `core/agent/runners/` | `ToolLoopAgentRunner`（手写 ReAct）+ Coze/Dify/Dashscope/DeerFlow 外部桥接 |
| 能力层 | `core/tools/`、`core/skills/`、`agent/mcp_client.py`、`core/knowledge_base/`、`persona_mgr.py`、`cron/` | 工具、技能、MCP、RAG、人格、定时任务 |
| 模型层 | `core/provider/` | 5 类能力 × N 个实现，装饰器注册 + 动态 import |
| 存储层 | `core/db/` | PostgreSQL（容器内，可配环境变量指向外部）；Milvus（容器内，含 etcd + MinIO） |
| 外接口 | `dashboard/` | Quart + hypercorn；24 个 route 模块、JWT Cookie、TOTP、Open API(scopes)、插件自有 Web 页面 |

**关键设计判断：AstrBot 刻意不依赖 LangChain。** Agent 循环、消息事件模型、Provider 抽象、向量检索全部自研。这条路线换来了极低的框架耦合度和对多平台消息语义的完全掌控，代价是通用生态（LCEL、LangGraph 检查点、LangSmith 追踪）无法直接复用。

---

## 二、消息处理流程

### 2.1 两段式：事件入列 → 总线分发 → 洋葱管线

```
适配器收到平台原始消息
   └─ 构造 AstrBotMessage（平台无关数据体）
        └─ 构造 AstrMessageEvent（行为层，含 send/react/set_extra）
             └─ Platform.commit_event()  →  event_queue.put_nowait(event)
                  └─ EventBus.dispatch()  ← 单消费者协程
                       ├─ astrbot_config_mgr.get_conf_info(event.unified_msg_origin) → conf_id
                       ├─ pipeline_scheduler_mapping[conf_id] → PipelineScheduler
                       └─ asyncio.create_task(scheduler.execute(event))  ← _pending_tasks 持强引用
```

### 2.2 九个 Stage（`core/pipeline/stage_order.py` 权威顺序）

| # | Stage | 职责 | 中止方式 |
|---|---|---|---|
| 1 | `WakingCheckStage` | 唤醒判定（wake_prefix / @ / AtAll / 引用 bot / 私聊 / 管理员）；逐个跑 handler filter，通过的写入 `event.set_extra("activated_handlers")` | `stop_event()` |
| 2 | `WhitelistCheckStage` | `id_whitelist` 校验 UMO / group_id | `stop_event()` |
| 3 | `SessionStatusCheckStage` | `SessionServiceManager.is_session_enabled` 会话总开关 | `stop_event()` |
| 4 | `RateLimitStage` | 固定窗口限流；`stall`（sleep 等窗口）或 `discard`（丢弃） | 可中止 |
| 5 | `ContentSafetyCheckStage` | 关键词 / 百度审核策略；命中返回提示并停止 | 可中止 |
| 6 | `PreProcessStage` | 预回应 emoji、路径映射、Record→wav、STT 语音转文本 | — |
| 7 | `ProcessStage` | 插件优先，其次 LLM / Agent | — |
| 8 | `ResultDecorateStage` | 回复前缀、内容安全复检、`OnDecoratingResultEvent`、分段回复、TTS、T2I、Node 转发、@/引用 | — |
| 9 | `RespondStage` | 空链过滤、路径映射、分段间隔发送、流式 `send_streaming`、`OnAfterMessageSentEvent`、`clear_result` | 终态 |

**编排实现（`scheduler.py`）**：`registered_stages.sort(key=STAGES_ORDER.index)` → 逐个 `initialize(ctx)`。核心 `_process_stages(event, from_stage)`：

- Stage 返回 **`AsyncGenerator`** → `async for` 消费完后**递归调用 `_process_stages(event, i+1)`** 再回归做后置处理 → **这就是洋葱模型**。
- Stage 返回**普通协程** → 顺序 `await`。
- 每步后检查 `event.is_stopped()` 提前 break。

**数据传递的真实位置**：`PipelineContext` 只承载 `astrbot_config` / `plugin_manager` / `astrbot_config_id` / `call_handler` / `call_event_hook`。**所有跨 Stage 业务数据都挂在 `AstrMessageEvent` 上**（`message_str`、`_result`、`_extras`、`is_wake`、`is_at_or_wake_command`、`_has_send_oper`、`call_llm`、`session`）。这是 AstrBot 一个重要取舍：事件对象即管线上下文。

### 2.3 ProcessStage 的三路分发

```
ProcessStage.process()
 ├─ 读 event.get_extra("activated_handlers")
 │    └─ 有 → StarRequestSubStage（插件路径，call_handler 执行 handler）
 │              └─ handler 可 yield ProviderRequest（覆盖 LLM 请求）
 │                   → event.set_extra("provider_request") → 进入 agent 子阶段
 └─ 若无发送动作 且 is_at_or_wake_command 且未 call_llm → LLM 路径
      └─ AgentRequestSubStage.initialize()
           ├─ agent_runner_type == "local"  → InternalAgentSubStage
           └─ 否则                          → ThirdPartyAgentSubStage
```

- **InternalAgentSubStage**：`MainAgentBuildConfig` → `build_main_agent()` → 按 `action_type` 走 live / 流式 / 普通；用 `session_lock_manager.acquire_lock(umo)` 串行化同会话；结束 `_save_to_history()` 落库。
- **ThirdPartyAgentSubStage**：按 `runner_type` 实例化 `Coze/Dify/Dashscope/DeerFlow AgentRunner`，`step_until_done()` 聚合 chunk；带 `_start_stream_watchdog` 防资源泄漏。
- **follow_up 机制**（`process_stage/follow_up.py`）：LLM 执行中用户追发的消息**不会被丢弃**，而是被 `try_capture_follow_up()` 捕获为同一 runner 的后续轮次（`runner.follow_up(text)` → `FollowUpTicket`），用模块级 `_FOLLOW_UP_ORDER_STATE` + `asyncio.Condition` 按 seq **严格串行放行**。

---

## 三、插件（Star）机制

### 3.1 分层

| 文件 | 职责 |
|---|---|
| `star/star.py` | 纯数据层：`StarMetadata` + 全局 `star_registry: list` / `star_map: dict` |
| `star/base.py` | `class Star(...)` 所有插件父类；**`__init_subclass__` 在类定义时自动注册**（v3.5.19 起无需装饰器）；钩子 `initialize()` / `terminate()` |
| `star/register/star_handler.py` | 注册 API 工厂：`register_command` / `_command_group` / `_event_message_type` / `_platform_adapter_type` / `_regex` / `_permission_type` / `_custom_filter` / `_llm_tool` / `_agent` 及全部 `on_*` 钩子 |
| `star/star_handler.py` | `EventType` 枚举（17 种）+ `StarHandlerMetadata` + `StarHandlerRegistry`（按 priority 降序） |
| `star/star_manager.py` | `PluginManager`：load / reload / install / uninstall / turn_on/off + 热重载 |
| `star/context.py` / `star_tools.py` | 插件侧上下文门面 / 主动发消息与事件构造 |

### 3.2 加载流程（8 步）

1. 扫 `data/plugins`（非保留）+ `astrbot/builtin_stars`（保留），只认 `main.py` 或 `<目录名>.py`
2. `_import_plugin_with_dependency_recovery()` → `__import__`；失败按 `requirements.txt` 预检/`pip_installer` 安装后重试
3. 读 `_conf_schema.json` → 构建 `AstrBotConfig`
4. 读 `metadata.yaml` 覆盖元数据 + `astrbot_version` PEP440 校验
5. 实例化 `star_cls(context[, config])`
6. **绑定**：对每个 handler 执行 `functools.partial(handler, star_cls)` 注入 self
7. 调用 `initialize()`，触发 `OnPluginLoadedEvent`
8. 注册进 `star_handlers_registry`

### 3.3 目录约定

```
data/plugins/<plugin_name>/
├── main.py                  # 必需，插件入口
├── metadata.yaml            # 必需，name/desc/version/author（可 repo/support_platforms/astrbot_version/display_name/pages）
├── requirements.txt         # 可选，依赖
├── _conf_schema.json        # 可选，配置 schema
├── logo.png / README.md     # 可选
└── .astrbot-plugin/i18n/*.json
```

### 3.4 事件钩子（`EventType` 全 17 种）

`OnAstrBotLoadedEvent`、`OnPlatformLoadedEvent`、`AdapterMessageEvent`、`OnWaitingLLMRequestEvent`、`OnLLMRequestEvent`、`OnLLMResponseEvent`、`OnAgentBeginEvent`、`OnAgentDoneEvent`、`OnDecoratingResultEvent`、`OnCallingFuncToolEvent`、`OnUsingLLMToolEvent`、`OnLLMToolRespondEvent`、`OnAfterMessageSentEvent`、`OnPluginErrorEvent`、`OnPluginLoadedEvent`、`OnPluginUnloadedEvent`。

### 3.5 过滤器体系（`star/filter/`）

| 过滤器 | 语义 | 关键点 |
|---|---|---|
| `CommandFilter` | 指令匹配 | **受 wake_prefix 约束**；用 `inspect.signature` 解析 handler 参数为 `handler_params`，支持 `GreedyStr` 与类型转换，结果写 `set_extra("parsed_params")` |
| `CommandGroupFilter` | 树形指令组 | `get_complete_command_names()` 递归拼父名；子指令打 `sub_command=True`，唤醒阶段跳过 |
| `EventMessageTypeFilter` | GROUP/PRIVATE/OTHER/ALL | `Flag` 组合 |
| `PermissionTypeFilter` | ADMIN/MEMBER | **语义特殊：失败走 `stop_event()` 而非继续** |
| `PlatformAdapterTypeFilter` | 限定平台 | `ADAPTER_NAME_2_TYPE` 名称映射 |
| `RegexFilter` | 正则匹配 | **不受 wake_prefix 约束** |
| `CustomFilter` / `And` / `Or` | 自定义组合 | `ABCMeta` 重载 `&` / `|` |

挂载方式：装饰器内统一 `handler_md.event_filters.append(filter)`；执行时在 `WakingCheckStage` 对所有 filter 做 **AND** 判定。

### 3.6 热重载与卸载

- `ASTRBOT_RELOAD=1` 时启动 `_watch_plugins_changes()`，用 `watchfiles.awatch` 监听目录，变更即 `reload(name)`
- `reload()` = `_terminate_plugin()`（调 `terminate()`/`__del__`）→ `_unbind_plugin()`（清 star_map/star_registry/handler/llm_tools/`unregister_platform_adapters_by_module`）→ `_purge_modules()`（清 `sys.modules`）→ 重新 load
- `turn_off_plugin()` 把 module_path 写入 shared_preferences 的 `inactivated_plugins`；`uninstall_plugin()` 额外删目录

---

## 四、平台适配器机制

### 4.1 标准接口

```python
class Platform(abc.ABC):
    def __init__(self, config: dict, event_queue: asyncio.Queue): ...
    @abstractmethod async def run(self) -> Coroutine: ...        # 长驻收消息循环
    @abstractmethod def meta(self) -> PlatformMetadata: ...      # 平台元信息
    async def send_by_session(self, session, message_chain): ... # 可覆写
    async def terminate(self): ...
    async def webhook_callback(self, request): ...               # Webhook 型平台
    def commit_event(self, event): ...                           # 内置：put 到事件队列
```

`PlatformMetadata`：`name` / `description` / `id` / `default_config_tmpl` / `adapter_display_name` / `logo_path` / `support_streaming_message` / `support_proactive_message` / `module_path` / `i18n_resources` / `config_metadata`。

注册：`@register_platform_adapter(...)` → `platform_registry` + `platform_cls_map`；`PlatformManager.load_platform()` 按 `config["type"]` **match-case 动态 import** 适配器类，起 `run` / `wrapper` 双任务。

### 4.2 支持的 18 个平台

`aiocqhttp`(OneBot v11)、`qq_official`、`qq_official_webhook`、`telegram`、`wecom`、`wecom_ai_bot`、`weixin_official_account`、`weixin_oc`、`lark`(飞书)、`dingtalk`、`discord`、`slack`、`kook`、`satori`、`line`、`misskey`、`mattermost`、`webchat`。
（`PlatformAdapterType` 枚举另含 `VOCECHAT` / `MATRIX` 历史遗留项，无实现。）

### 4.3 消息事件与消息组件

- **`AstrBotMessage`**：平台无关**数据体**（`type`/`self_id`/`session_id`/`group`/`sender`/`message`(消息链)/`message_str`/`raw_message`/`timestamp`）
- **`AstrMessageEvent(abc.ABC)`**：**行为层**。核心方法：`send` / `send_streaming` / `react` / `get_messages` / `get_sender_id` / `get_self_id` / `is_private_chat` / `set_extra` / `stop_event` / `is_stopped` / `set_result` / `get_result` / `request_llm` / `make_result` / `plain_result` / `image_result` / `chain_result` / `should_call_llm`
- **`MessageSession`**：`platform_name + message_type + session_id`，`__str__` 即 **UMO**（`platform:id:message_type:session_id`）。UMO 是全链路主键：选配置、加锁、会话历史、follow-up 序号、限流/白名单判定全靠它
- **消息组件**（`core/message/components.py`）：`ComponentType` + `BaseMessageComponent(BaseModel)`，子类 `Plain/Image/Record/Video/File/Face/At/AtAll/Reply/Poke/Forward/Node/Nodes/Json/Share/Music/Location`。两种序列化：`toDict()` 同步 OneBot 消息段；`to_dict()` 异步版会把 Image/File/Video **上传文件服务并替换为 `api/file/<token>` 链接**

---

## 五、配置与扩展方式

### 5.1 三层配置

| 机制 | 实现 | 说明 |
|---|---|---|
| 单份配置 | `core/config/astrbot_config.py::AstrBotConfig(dict)` | `_conf_schema.json` 驱动：`_config_schema_to_default_config()` 依 `type/default` 生成默认值（`DEFAULT_VALUE_MAP`，支持 `object` 递归、`template_list`）；`check_config_integrity()` **自动补全新增键、剔除废弃键、同步顺序**；`__getattr__` 支持点号访问；`save_config()` 落盘 |
| 多份配置 | `core/astrbot_config_mgr.py::AstrBotConfigManager` | `confs: uuid/"default" -> AstrBotConfig`；`_load_conf_mapping(umo)` 把 **UMO 映射到 conf_id**，实现「不同会话用不同配置」 |
| 运行时偏好 | `SharedPreferences`(`sp`) | 存 DB；`umop_config_router` 负责 UMO→配置的路由持久化 |

Provider 配置存 `data/cmd_config.json`；MCP 配置存 `data/mcp_server.json`；Skill 存 `data/skills/skills.json`。

### 5.2 六类扩展点

1. **插件（Star）** — 目录即插件，`/plugin` 指令与 WebUI 双通道装卸
2. **Provider 适配器** — `@register_provider_adapter` + `dynamic_import_provider` 惰性导入
3. **平台适配器** — `@register_platform_adapter`
4. **Pipeline Stage** — `@register_stage`，靠 `STAGES_ORDER.index` 排序，未登记则报错
5. **LLM Tool** — `@llm_tool`（`docstring_parser` 解析 `Args:` 生成 JSON Schema）或 `@builtin_tool`
6. **插件自带 Web API / 页面** — `Context.register_web_api()` + `metadata.yaml` 的 `pages` + `plugin_page_auth.py`

---

## 六、对外接口

| 通道 | 实现 |
|---|---|
| Dashboard HTTP | Quart（异步 Flask API）+ hypercorn；`dashboard/routes/` 下 24 个模块：`auth` `api_key` `backup` `chat` `chatui_project` `command` `config` `conversation` `cron` `file` `knowledge_base` `live_chat` `log` `open_api` `persona` `platform` `plugin` `session_management` `skills` `stat` `static_file` `subagent` `t2i` `tools` `update` `util` |
| 认证 | JWT Cookie（`DASHBOARD_JWT_COOKIE_NAME`）+ TOTP 双因素；`_AuthRateLimiter` 令牌桶按 IP 限流登录/改配置/TOTP setup |
| Open API | `routes/open_api.py` + `ALL_OPEN_API_SCOPES` 作用域化 API Key，供外部程序调用 |
| WebSocket | `WebChatAdapter`（`platform/sources/webchat/`）+ `webchat_queue_mgr`；`message_parts_helper` 处理分片 |
| 插件页面 | `PluginPageAuth` + `metadata.yaml: pages`，插件可自带前端 |
| CLI | `astrbot init / run / conf / password / plug` |

---

## 七、关键技术选型（对照 IrsBot）

| 领域 | AstrBot 选型 | IrsBot 选型 | 差异评估 |
|---|---|---|---|
| Agent 编排 | **自研手写 ReAct**（`ToolLoopAgentRunner`，OpenAI 风格 tool_calls） | **LangChain + LangGraph StateGraph** | IrsBot 更省代码、生态好；代价是框架升级面大、事件语义受 LangGraph 约束 |
| 消息事件模型 | 自研 `AstrMessageEvent` 抽象 | ➖ **不做**（无 IM） | 浏览器请求-响应模型已足够 |
| 管线编排 | **AsyncGenerator 洋葱模型** + 9 Stage | 4 Stage，普通 for 循环 | IrsBot 只需**按 Web 场景裁剪**（Phase 12），不必照搬 9 Stage |
| Provider 抽象 | 自研 `AbstractProvider` + 装饰器注册 + 动态 import | LangChain `init_chat_model()` + 自研 Manager | IrsBot 缺 STT/TTS/Rerank 三类（Rerank 为 **P1**） |
| 向量检索 | **FAISS + SQLite FTS5**，自研 Hybrid + RRF + Rerank | **Milvus**（容器内，含 etcd + MinIO）+ BM25 + RRF | ⚠️ **选型不同**：AstrBot 走轻量内嵌，IrsBot 走独立服务。IrsBot 缺 Rerank 段（P1） |
| Web 框架 | Quart（异步 Flask）+ hypercorn | FastAPI + uvicorn | IrsBot 自动 OpenAPI/SDK 生成是优势 |
| 数据库 | SQLite（默认）/ PostgreSQL；自研 `vec_db` 抽象 | **PostgreSQL**（容器内 `db`，可配环境变量指向外部）+ SQLModel + Alembic | ⚠️ **选型不同**：AstrBot 默认 SQLite，IrsBot **只支持 PostgreSQL** |
| 多平台 | 18 个适配器 | ➖ **不做** | 定位明确排除 IM |
| 插件生态 | 完整 Star 体系 + 热重载 | ➖ **不做**（Skill / Tool / MCP 已覆盖扩展需求） | 无插件分发场景 |
| 部署形态 | **单实例单部署者** | **单实例单部署者（本地单用户）** | **一致**。IrsBot 不做多租户，`user_id` 仅作数据归属 |

> **路线提醒（已更新）**：AstrBot 的「消息事件 + 平台适配器 + Star 插件 + Pipeline 洋葱」是一套强耦合的 **IM 整体设计** —— IrsBot **整层不做**。
> IrsBot 要吸收的是它的 **Agent 能力栈**（Pipeline 裁剪版 + Agent 引擎 + Provider + Tool + Skill + MCP + RAG + 上下文管理），而**不是**平台接入层。切勿把 AstrBot 的 Stage 与适配器零散塞进 FastAPI。

---

## 八、AstrBot 有、IrsBot 完全缺失的能力（速查）

> 按 IrsBot 现定位标注优先级：**P0** 本地可用硬门槛 ｜ **P1** 能力与体验 ｜ **P2** 工程卫生 ｜ **➖** 有意不采用
>
> ⚠️ **本节已于 2026-09-16 第五轮重标**。上一版把「平台适配器 / 消息事件 / 事件总线 / 唤醒词」列为 P0 —— 那是 IM 框架定位下的判断，**现已作废**。
> 上一版还曾把「本地零外部依赖：SQLite + FAISS」列为 P0 —— **亦已作废**（D4：保持 PostgreSQL + Milvus）。

- **[P0]** **Docker 化交付**：`compose.yml` 本地化改造 + 一键启动脚本 + 首次引导（→ D1–D7）
- **[P0]** `shell` / `file_write` 工具默认关闭 + 路径白名单（→ D6）
- **[P1]** 缓存淘汰（`_chat_cache` / `_embed_cache` 无界增长）
- **[P1]** Pipeline **Web 场景裁剪版**（SessionStatus / RateLimit / PreProcess / Process / ResultDecorate 简化版，共 5 个左右；**不做** WakingCheck / Whitelist 的 IM 语义）
- **[P1]** RAG Rerank 段 + Provider Rerank 能力
- **[P1]** 上下文管理补强（token 计数 / 轮次截断 / tool_call 配对修复 / 空输出重试）
- **[P1]** 前端配置台：KB / MCP / Skill / Persona 管理页 + 配置闭环
- **[P2]** Persona 人格系统（IrsBot 仅有数据模型）
- **[P2]** 统计与追踪（`AgentStats` / `TokenUsage` / `AgentRun`）
- **[P2]** Skill 四类来源、RAG 聚合模式、多格式解析器
- **[P2]** 内容安全审核（**本地单用户下为可选**，默认关）
- **[P2]** 备份导入导出、日志脱敏
- **[P3]** 子代理 Handoff（`transfer_to_<agent>`）+ `SubAgentOrchestrator`
- **[P3]** follow_up 追发消息串行机制
- **[P3]** 多模态 `ContentPart`（Web 传图是加分项，非必需）
- **[P3]** 会话串行化 `session_lock_manager`（Web 是请求-响应模型，可选加锁）
- **[P3]** STT / TTS（按需）
- **[➖]** 平台适配器抽象与 18 平台接入、`AstrBotMessage` / `AstrMessageEvent` / UMO 三件套 —— **无 IM**
- **[➖]** 消息组件链 + 双向序列化 —— Web 用 JSON / Markdown
- **[➖]** 事件总线（`asyncio.Queue` + 按 UMO 路由）—— FastAPI 路由即入口
- **[➖]** 唤醒词 / @ 触发判定、群白名单、流式分段回复 —— 无群聊场景
- **[➖]** Star 插件体系 + 17 事件钩子 + 热重载 —— 用 Skill / Tool / MCP 替代（可留 2–3 个内部钩子）
- **[➖]** 文件 token 服务、主动消息推送 + Cron —— 浏览器是拉取模型
- **[➖]** T2I、Computer Use / 沙箱、热更新器 —— Web 已解决渲染 / 与 shell 职责重叠 / 用 git + Docker 替代
- **[➖]** TOTP 双因素、API Key 作用域化 Open API —— 本地单用户可延后
- **[➖]** 多租户架构 —— 已拆分到另一个项目
