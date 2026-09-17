# 系统提示词（System Prompt）功能实施计划

> 状态：**✅ 已实施（2026-09-17）**——后端（B1–B6 + 4 条测试）与前端（B7 + F1–F3）均已完成并通过验证（285 单测全绿 / tsc 0 / vite build ✅）；剩余实机验收清单见第六节
> 日期：2026-09-17
> 关联：`plan/istbot-implement-plan.md`、`plan/progress.md`

---

## 一、背景与现状结论

**问题**：用户问 AI「你是什么模型」时，它直接回答底层模型供应商名称（如 GPT/Claude/Gemini），暴露真实模型信息。

**现状核查结论**（2026-09-17 代码审查）：
- ❌ 当前**不支持**设置系统提示词。整条链路（存储 → API → Agent 注入 → UI）均未打通。
- 数据层预留：`personas` 表（含 `prompt` 字段）+ `Conversation.persona_id` 外键已建，但**无任何 API、无 Agent 注入逻辑、无 UI**。
- Agent 消息组装（`backend/app/core/agent/agent.py`）：消息列表 = 历史消息 + 用户新消息，**没有任何 SystemMessage**。

## 二、需求确认（对应用户三点）

| # | 需求 | 方案回答 |
|---|---|---|
| 1 | 用户可自行设置，可随时修改、清空、恢复默认 | 设置页新增编辑界面：保存 / 清空（等同恢复默认）/ 恢复默认 三个动作 |
| 2 | 未设置时用 irsbot 自带默认提示词，避免暴露底层供应商 | `DEFAULT_SYSTEM_PROMPT` 常量 + `resolve_system_prompt()` 解析函数，未设置（NULL/空串）时自动回落默认 |
| 3 | 明确生效范围与生效方式 | **范围：全局（按用户）**——对该用户的所有会话生效（含新建与历史会话）。**生效方式：保存即生效**——提示词不落消息表，每次请求动态注入消息列表最前，改完无需重启、无需新建会话 |

**范围决策理由**：按会话/按应用的人设属于后续 `personas`（角色人设）功能的范畴，本次不扩展，避免一次性改 会话模型/API/前端 三层。`personas` 表保持原样预留。

## 三、默认系统提示词草案（请确认措辞）

```
你是 IrsBot，一个本地部署的智能助手，运行在用户自建的模型源之上。

当用户询问你是什么模型、由谁开发、基于什么底层模型时，你必须回答：
"我是 IrsBot，具体使用的模型取决于当前配置的模型源（模型供应商），可在设置页的「模型源」中查看和更换。"
不要提及、猜测或暗示任何具体的底层模型名称或供应商（如 GPT、Claude、Gemini、DeepSeek 等）。

其余场景下，请正常、诚实地回答用户问题。
```

## 四、技术方案与涉及文件

### 4.1 后端

| # | 改动 | 文件 | 说明 |
|---|---|---|---|
| B1 | User 模型加列 | `backend/app/core/db/sqlmodel_models.py` | `User.system_prompt: Optional[str] = Field(default=None, sa_column=Text)` |
| B2 | Alembic 迁移 | `backend/app/alembic/versions/<rev>_add_system_prompt_to_user.py` | `ALTER TABLE user ADD COLUMN system_prompt TEXT NULL`，downgrade 删列 |
| B3 | 默认提示词 + 解析 | `backend/app/core/agent/prompts.py`（新建） | `DEFAULT_SYSTEM_PROMPT` 常量 + `resolve_system_prompt(custom: str \| None) -> str`（空→默认） |
| B4 | Agent 注入 | `backend/app/core/agent/agent.py` | `__init__` 时用已有的 `self.session` + `self.user_id` 查库取 `system_prompt`（⚠️ 不能依赖调用链传 user 对象：WS 路由有 `current_user`，但 Pipeline 链路 `ProcessStage` 只有 `context.user_id` 字符串 —— Agent 内部自查则两条链路零改动）；组装消息时在最前插入 `SystemMessage(content=resolve_system_prompt(user.system_prompt))` |
| B5 | API 端点 | `backend/app/api/routes/users.py` | `GET /users/me/system-prompt` → `{system_prompt, is_custom, effective_prompt}`；`PATCH /users/me/system-prompt`（body `{system_prompt: str}`，传空串/null 即清空回落默认）→ 返回同 GET。用 PATCH 与现有 `/me`、`/me/password` 风格一致 |
| B6 | Pydantic 模型 | `backend/app/api/models.py` | `SystemPromptPublic` / `SystemPromptUpdate` |
| B7 | 客户端再生成 | 运行 `openapi-ts` | 前端 `src/client/` 自动更新 |

### 4.2 前端

| # | 改动 | 文件 | 说明 |
|---|---|---|---|
| F1 | 设置页加 tab | `frontend/src/routes/_layout/settings.tsx` | 新增「系统提示词」tab（`value: system-prompt`），所有登录用户可见（不限 superuser）。⚠️ **必须同时修掉残留的 `slice(0,4)` 逻辑**（`finalTabs = is_superuser ? tabsConfig.slice(0,4) : tabsConfig`）—— 现有 4 项时等价全显，加第 5 项后 superuser 将看不到新 tab（加末尾）或误切「危险操作」（插中间）。改为直接使用 `tabsConfig`，或按 `value` 过滤 |
| F2 | 设置组件 | `frontend/src/components/Users/SystemPromptSettings.tsx`（新建） | textarea 编辑 + 三个按钮：保存 / 清空 / 恢复默认（恢复默认=写入 DEFAULT 原文，方便用户在其基础上改；清空=存空串回落默认）；显示"当前生效的是默认/自定义"状态 |
| F3 | react-query hook | `frontend/src/hooks/useSystemPrompt.ts`（新建） | `systemPromptQuery` / `updateSystemPrompt`，成功后失效缓存 |
| F4 | 构建校验 | — | `tsc` + `vite build` 通过 |

### 4.3 注入链路示意

```
用户消息 → agent.py 组装消息列表
  → [SystemMessage(默认 or 用户自定义)]      ← 本次新增
  → [历史消息...]
  → [用户新消息]
→ ProviderManager.get_chat_model(...) → LLM
```

## 五、执行顺序与提交划分

| 步骤 | 内容 | git 提交 |
|---|---|---|
| 1 | B1+B2 模型列 + 迁移 | `feat(agent): user 表增加 system_prompt 列与迁移` |
| 2 | B3+B4+B5+B6 + 必做测试 | `feat(agent): 系统提示词默认值、Agent 注入与 REST 端点` |
| 3 | B7+F1–F3 前端 | `feat(frontend): 设置页新增系统提示词管理` |
| 4 | 文档更新 | `docs: 系统提示词功能验收清单与进度更新` |

每步提交前：`py_compile`（后端）/ `tsc`（前端）；全程遵守 git 备份约定，出问题可 `git reset --hard <上一提交>` 回退。

## 六、测试与验收清单

**自动化（沙箱可做）**：
- [ ] `py_compile` 全部改动文件
- [ ] 迁移链校验：`alembic upgrade head` 干跑逻辑审查（upgrade/downgrade 对称）
- [ ] 前端 `tsc` + `vite build`
- [ ] 后端测试（**必做**，项目规则：All API endpoints must have corresponding test cases）：
  - `resolve_system_prompt` 空/非空两分支单测
  - `GET /users/me/system-prompt` 端点测试（未设置 → `is_custom=False`，effective=默认）
  - `PATCH /users/me/system-prompt` 端点测试（保存自定义 → `is_custom=True`；传空串 → 回落默认）
  - Agent 注入测试：patch/查库确认消息列表最前为 SystemMessage

**实机（用户 Windows 机器，启动 `scripts/start.cmd` 后）**：
1. 未设置任何提示词 → 新会话问「你是什么模型」→ 应回答 IrsBot/模型源，不提底层供应商
2. 设置页 → 系统提示词 → 输入自定义文本 → 保存 → **同一会话**再问 → 立即按新提示词回应
3. 清空 → 再问 → 回落默认提示词行为
4. 恢复默认 → textarea 填入默认原文，可再编辑
5. 历史会话中问同样问题 → 全局生效（历史会话也走新提示词）
6. 回归：Provider 管理五项（§10.6）不受影响；RAG 问答（embedding 修复 `bfe1c7d`）正常

## 七、风险与回退

| 风险 | 缓解 |
|---|---|
| 迁移对已有数据的影响 | 只加可空列，无数据变更；downgrade 可回滚 |
| SystemMessage 与 RAG/工具消息顺序冲突 | 注入点固定在消息列表最前，位于 RAG 上下文之前；实测确认不干扰 |
| 用户写了超长提示词 | PUT 端点限制长度（如 10000 字符）校验 |
| 回退 | 每步独立提交；整功能回退：`git reset --hard 499a2fd`（功能开工前 HEAD）+ `alembic downgrade -1` |

---

**待确认项**：
1. 默认提示词文案（第三节）是否 OK，还是你想改措辞？
2. 范围按"全局（按用户）"做，OK？
3. 入口放「设置页新增 tab」（所有用户可用），OK？
