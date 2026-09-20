# 聊天输入框附件能力 + 侧边栏对话入口整理（施工详案）

> 状态：**待审阅，未施工**
> 提出：2026-09-21（用户）
> 依据：用户对侧边栏与输入框的两组截图 + 三条决策问答

---

## 一、需求原文与拆解

用户原文（2026-09-21）：

> 我要你实现几个功能
> 聊天按钮不需要，对话已经有了
> 把新对话移到最近对话的上面
> 为输入信息添加上传文件功能
> 如图三，点击上传按钮后如图三
> 先创建文档在实现功能

拆成 4 件事：

| # | 需求 | 截图依据 | 性质 |
|---|---|---|---|
| A | 侧边栏去掉「聊天」入口 | 图一 | 纯前端，低风险 |
| B | 「新对话」移到「最近对话」标签**上面** | 图一 | 纯前端，低风险 |
| C | 输入框加「＋」上传按钮 | 图二（输入框缺按钮） | 前后端，主体工程 |
| D | 点击「＋」弹出菜单：~~上传文档~~ / 上传图片 / ~~共享屏幕和应用~~ / 截屏提问 | 图三 | 前后端 |

### 已确认的决策（2026-09-21 用户三问三答）

| 问题 | 用户决策 | 含义 |
|---|---|---|
| 上传文档怎么用 | **解析后附进本条消息** | 不做「存入知识库」分支，不选库、不向量化。**本轮有效**，下一轮需重新上传 |
| 上传图片怎么用 | **先判断模型是否支持视觉；不支持则调用 OCR 识图** | 两条路径，需要「视觉能力判定」+「OCR 回退」两个子系统 |
| 截屏提问是否保留 | **保留**：「就是启动截图然后将截图输入到输入框提问而已」 | 走图片同一套链路，只是图片来源是屏幕捕获 |
| 共享屏幕和应用 | **不要** | 菜单里不出现该项 |

→ 最终菜单为 **3 项**：上传文档 / 上传图片 / 截屏提问。

---

## 二、现状勘察（已读代码，非推测）

| 位置 | 现状 | 对本需求的影响 |
|---|---|---|
| `backend/app/api/routes/agent_ws.py:537` | 上行协议 `{"type":"message","content":"<纯字符串>"}` | **必须扩协议**才能带附件 |
| `backend/app/core/db/models.py:199` | `Message.content` 是 `dict`（JSON 多态），实际存 `{"text":…, "tool_trace":…, "citations":…, "stopped":…}` | 附件元数据**可直接搭车**，无需新列、无需迁移 |
| `backend/app/core/agent/agent.py:185,222` | `HumanMessage(content=user_message)`，user_message 是 `str` | LangChain 接受 `list[content_block]`，多模态**有基础** |
| `backend/app/core/knowledge_base/parsers.py:21` | `DocumentParser.SUPPORTED_EXTENSIONS = {.pdf,.txt,.md,.docx}`，`parse(path)` 统一返回 `list[Document]` | **直接复用**做文档解析，不重写 |
| `backend/app/api/routes/knowledge_base.py:261` | 已有 multipart 上传范例（`UploadFile` + 落盘 `KB_FILE_STORAGE_DIR/{uuid}/` + 原始名入库） | **照抄该模式**即可 |
| `backend/app/core/agent/provider.py:101` | `get_model_capabilities()` 按「provider_type + 固定模型名」查表；**用户自带的 `qwen3.8-flash` 不在 `supported_models` 里 → 返回 `None`** | ⚠️ **现成能力表对本项目常态（自带 base_url + 自填模型名）失效**，视觉判定必须另想办法 |
| `frontend/src/hooks/useAgentChat.ts:285` | `sendMessage(content: string)` | 需扩签名带附件 |
| `frontend/src/routes/_layout/chat.tsx:198` | 输入框是 `<textarea>` + 发送按钮，**无「＋」按钮** | 需加按钮 + 菜单 + 附件条 |
| `frontend/src/routes/_layout/chat.tsx:107` | `isStreaming` 变假时 `invalidateQueries(["conversations"])` | 附件消息落库后侧边栏刷新逻辑不受影响 |

### 关键结论

1. **不用加表、不用加迁移**：`Message.content` 已是 JSON 多态，附件元数据挂在 `content.attachments` 即可，与已有的 `tool_trace` / `citations` 同一层级。
2. **文档解析零新依赖**：`DocumentParser` 已有 pdf/txt/md/docx 四条路。
3. **视觉能力判定是本次最大的不确定点**（见第四章）。

---

## 三、待确认的决策（需你拍板后我才动手）

### 🔴 决策 1：OCR 用什么引擎？

「模型不支持视觉 → 调 OCR」这条链路里，**OCR 从哪来**必须先定。三个选项：

| 方案 | 做法 | 优点 | 代价 |
|---|---|---|---|
| **1a. 复用「视觉模型源」**（推荐） | 给 ProviderConfig 加 `supports_vision` 标记；OCR = 用用户**另一个**视觉模型源发一次「提取图中文字」的对话 | 零新依赖；不碰镜像体积与 wheelhouse 校验；与「用户自带 Key」一致 | 用户必须自己配一个视觉模型源，否则 OCR 无引擎（届时明确提示「请先添加一个视觉模型源」） |
| 1b. 本地 OCR 引擎 | 引入 `rapidocr-onnxruntime` | 完全离线、开箱可用 | 拖进 onnxruntime（~200MB+），要重跑 `scripts/wheelhouse.py update` 重下 wheel、镜像变大——**与已确认的「镜像瘦身不做」理由相冲突** |
| 1c. 不做 OCR | 模型不支持视觉时把图片存下来、只在消息里显示缩略图，并提示「当前模型不支持图片理解」 | 最省 | **不满足你的要求**，仅作兜底 |

**我的建议：1a。** 理由与「上游接口适配器」同源——能力边界由用户自带的服务提供，我们不往镜像里塞重型本地模型。

> **实际决策（2026-09-21，用户拍板）：走 1b 本地 OCR 引擎。** 用户明确选了本地方案
> （「不依赖网络、开箱可用」优先于镜像体积）。已知代价如实记录：镜像 +~200MB；
> `rapidocr` 硬依 GUI 版 `opencv-python`，`python:3.13-slim` 需补
> `libgl1 libglib2.0-0 libxcb1 libsm6 libxext6 libxrender1`（换 headless 也躲不掉）；
> wheelhouse 需重下 wheel（`scripts/wheelhouse.py update`，清单 151 包）。
> 另：该方案下**能力边界**与 1a 相反——OCR 是否可用由镜像决定，不由用户是否配了视觉源决定。

### 🟡 决策 2：视觉能力怎么判定？

| 方案 | 说明 |
|---|---|
| **2a. Provider 显式标记 + 模型名启发式兜底**（推荐） | `ProviderConfig.supports_vision`（`None` = 自动）。自动 = 按模型名模式匹配（`vl`/`vision`/`4o`/`claude-3`/`gemini`/`glm-4v`/`qvq`/`internvl`/`minicpm-v`/`llava`…）。模型源表单加三态选择：自动 / 支持 / 不支持 |
| 2b. 纯模型名启发式 | 不加字段、不改表单，但用户遇到误判无法纠正，只能改模型名 |
| 2c. 上游探测（发一张 1×1 图试错） | 最准，但每次换模型要打一次上游，且错判后要缓存结果，复杂度高 |

**我的建议：2a。** 加一个可空字段的代价很小，却把「猜不准」变成「可纠正」，且启发式默认值让绝大多数场景无需手动设置。

### 🟡 决策 3：附件落盘保留多久？

附件文件（图片/文档）要落盘。选项：随消息删除而删 / 保留 N 天 / 永久保留。

**我倾向：随会话删除而删**（`conversations` 级联删除时一并清目录），暂不做定时清理——与现有「软删除惰性清理」相比这里更简单，因为附件是**一次性上下文**（你说的「本轮有效」），历史消息里只需要保留**可展示的元数据 + 缩略图**。

---

## 四、技术方案

### 4.1 数据形态（不新增表）

`Message.content` 扩展为：

```jsonc
{
  "text": "帮我看看这份财报讲了什么",
  "attachments": [
    {
      "id": "7f3a9c1b…",         // 服务端生成的 32 位 hex（uuid4().hex），后端据此读文件
      "kind": "document",        // document | image
      "filename": "2024财报.pdf",
      "size": 284113,
      "extracted_chars": 18420,  // 文档解析出的字符数（前端可显示「已解析 1.8 万字」）
      "truncated": false         // 超长被截断时为 true
    },
    { "id": "9c1b7f3a…", "kind": "image", "filename": "截图-2026-09-21.png", "size": 88213 }
  ]
}
```

> 实施偏差（2026-09-21）：`id` 一路都是**裸 32 位 hex**（`uuid.uuid4().hex`），
> 没有 `att_` 前缀——下面示例里写作 `att_7f3a…` 只是文档最初的示意，实际以
> 本节为准。读取侧按 `^[0-9a-f]{32}$` 校验形状后再 glob，形状不对直接拒绝。

- 前端 `history` 事件已有 `content.get("text")` 口径 → **附件不破坏既有渲染**，只需新增 `attachments` 字段的读取。
- assistant 消息不带 attachments。

### 4.2 后端改动清单

**① 附件上传端点**（新文件 `backend/app/api/routes/attachments.py`）

```
POST /api/v1/agent/attachments        multipart: conversation_id + file
  → 201 {"id":"7f3a9c1b…", "kind":"document", "filename":"…", "size":…, "extracted_chars":…, "truncated":…}
  → 400 不支持的格式（.xlsx 等）/ 超过大小上限
  → 401 未登录
  → 404 会话不存在或不属于当前用户
```

- 落盘：`{CHAT_ATTACHMENT_DIR}/{user_id}/{conversation_id}/{att_id}_{safe_filename}`
  （目录按**用户/会话两级隔离**——删会话即 `shutil.rmtree` 整个会话目录，
  这也是「附件保留多久」的最简答案；`safe_filename` 剥掉路径分隔符等危险字符）
- 文档：`DocumentParser.parse()` → 拼接 `page_content` → 超限截断（建议 `ATTACHMENT_MAX_CHARS = 60000`，超出部分丢弃并回 `truncated=true`）
- 图片：只落盘 + 校验大小/魔数，**不做任何解析**（送模型时才读字节）
- 大小上限：`ATTACHMENT_MAX_BYTES`（建议图片 10MB、文档 20MB）

**② WS 上行协议扩展**（`agent_ws.py`）

```jsonc
// 旧（保持兼容）
{"type": "message", "content": "你好"}
// 新
{"type": "message", "content": "看看这个", "attachments": [{"id": "7f3a9c1b…"}]}
```

- `_run_turn_inner` 的 `content: str` 参数改为 `content: str, attachments: list[dict]`
- **越权防线**：按 `att_id` 查文件时必须先校验形状（`^[0-9a-f]{32}$`），再在 `CHAT_ATTACHMENT_DIR/{current_user.id}/{conversation_id}/` 目录内 glob，且只接受唯一命中——**绝不接受前端传任意路径**（否则变成任意文件读取漏洞）
- 用户消息落库：`content = {"text": …, "attachments": [完整元数据]}`

**③ 送模型**（`agent.py`）

```python
# 伪码
def _build_user_content(text, atts, supports_vision) -> str | list:
    doc_texts = [读取并解析的文档文本]          # 拼接为 "【附件：财报.pdf】\n<正文>"
    images = [a for a in atts if a.kind == "image"]
    if not images:
        return f"{text}\n\n" + "\n\n".join(doc_texts)
    if supports_vision:
        return [{"type":"text","text": 拼接文本}] + [
            {"type":"image_url","image_url":{"url": f"data:{mime};base64,{b64}"}}
            for b in images
        ]
    # OCR 回退（决策 1a）：逐个图片调视觉模型源，把识别文字并进文本
    return f"{text}\n\n{doc_texts}\n\n{ocr_texts}"
```

- 文档文本**始终**以文本块形式进上下文（与模型是否视觉无关）
- 历史轮次里的旧附件：`get_context_messages` 只还原 `content.text`（**不回放历史附件**），避免上下文爆炸——这与「本轮有效」的决策一致

**④ 视觉能力判定**（决策 2a）

- `ProviderConfig` 加 `supports_vision: bool | None`（`None` = 自动）
- 新增 `provider.py::resolve_supports_vision(pc) -> bool`：显式值优先，否则走 `_guess_vision_by_name(model_name)`
- 新增 `_looks_like_vision_model(name)`（纯函数，好测）

**⑤ 附件清理**

- `DELETE /agent/conversations/{id}` 时 `shutil.rmtree(CHAT_ATTACHMENT_DIR/{user_id}/{conversation_id})`——落地为 `attachments.remove_conversation_dir()`，目录不存在不报错（删会话不该因为「没有附件」失败）

### 4.3 前端改动清单

**① 侧边栏（需求 A + B）** — `AppSidebar.tsx` + `ConversationList.tsx`

- 删 `navGroups[0].items` 里的 `{ icon: MessageSquare, title: "聊天", path: "/chat" }`（连带 `MessageSquare` import）
- `ConversationList.tsx`：把「新对话」`SidebarMenuItem` **移到 `<SidebarGroupLabel>最近对话</SidebarGroupLabel>` 之前**（可加分隔线与上方分组隔开）
- ⚠️ 检查项：删掉「聊天」后，`/chat` 的进入路径只剩「新对话」与「最近对话」项。**首次登录落在 `/`（Dashboard）**，用户需点「新对话」进聊天——这符合「对话已经有了」的表述，但要确认这是你想要的默认落点

**② 输入框上传（需求 C + D）** — `routes/_layout/chat.tsx` 抽成组件

- 新增 `components/Chat/AttachmentMenu.tsx`：`＋` 按钮 + 下拉菜单 3 项
  - 上传文档 → `<input type="file" accept=".pdf,.txt,.md,.docx">`
  - 上传图片 → `<input type="file" accept="image/png,image/jpeg,image/webp,image/gif">`
  - 截屏提问 → `navigator.mediaDevices.getDisplayMedia({video:true})` → 取一帧画到 canvas → `toBlob` → 直接作为 image 附件（**不给用户选文件的机会**，截完即入输入框）
- 新增 `components/Chat/AttachmentChips.tsx`：输入框上方展示待发送附件（图标 + 文件名 + 大小 + 删除按钮 + 上传中/解析中状态）
- ⚠️ `getDisplayMedia` 要求**安全上下文**：`http://127.0.0.1:8000` 属于 secure context，**可用**；若将来用局域网 IP（`http://192.168.x.x`）访问则会被浏览器拒绝 → 菜单项需做能力检测（`navigator.mediaDevices?.getDisplayMedia` 不存在时置灰 + tooltip 说明）
- ⚠️ 截屏必须**立即 `track.stop()`** 关闭共享，不做持续共享（这正是「共享屏幕功能不需要」的技术落点）
- `useAgentChat.sendMessage(content, attachments)` 扩展；`ws.send({type:"message", content, attachments})`
- `ChatMessage` 类型加 `attachments?`；`MessageItem` 渲染用户消息的附件（图片显示缩略图，文档显示文件名 chip）

### 4.4 边界与防护

| 风险 | 防护 |
|---|---|
| **任意文件读取（路径穿越）** | 只按 `att_id` 查文件，白名单校验 `att_id` 形状 + 拼路径后 `resolve()` 必须在用户目录内 |
| 超大文件撑爆上下文 | 文档解析后按 `ATTACHMENT_MAX_CHARS` 截断并标记 `truncated` |
| 超大文件撑爆磁盘/内存 | 上传与读取都设字节上限，`UploadFile` 边读边计数，超限即 400 并删残片 |
| 伪装扩展名 | 图片校验魔数（PNG/JPEG/WebP/GIF），不信任 `Content-Type` 与扩展名 |
| WS 帧过大 | **附件不走 WS 传字节**，只传 `att_id`；字节由后端自己从磁盘读 |
| 用户误传敏感文件 | 不做额外处理，但附件目录按用户隔离，且随会话删除 |

---

## 五、阶段拆分（每阶段一个可回退的提交点）

| 阶段 | 内容 | 依赖 | 可独立验收 |
|---|---|---|---|
| **S0** | 侧边栏：删「聊天」+ 「新对话」上移 | 无 | ✅ 你打开 8000 就能看到 |
| **S1** | 后端附件基建：落盘 + 文档解析 + 上传端点 + 大小/格式/越权防护 + 单测 | 无 | ✅ curl 可验 |
| **S2** | 附件数据打通：WS 协议扩展 + 消息落库 + history 回放 | S1 | ✅ 发一条带附件的消息，刷新后附件仍在 |
| **S3** | 前端上传 UI：`＋` 菜单 + 附件 chip + 图片缩略图 + 上传/解析中状态 | S2 | ✅ 交互可验 |
| **S4** | 文档进上下文：模型真的能读到文档内容 | S3 | ✅ 问「这份文档讲了什么」，回答必须引用内容 |
| **S5** | 视觉判定 + 图片多模态直传 | S4 + 决策 2 | ✅ 用视觉模型问图片内容 |
| **S6** | OCR 回退 | S5 + 决策 1 | ✅ 用非视觉模型传图 → 走 OCR → 能答 |
| **S7** | 截屏提问 | S5 | ✅ 点菜单 → 授权 → 截图入输入框 |
| **S8** | e2e（Playwright）+ dist 重建 + 文档同步（PROGRESS.md 待办 + 进度记录） | 全部 | ✅ |

> S0 与 S1 无依赖关系，可并行；S0 很适合当第一个「先让用户看到东西」的交付。

**实施结果（2026-09-21）**：S0–S8 全部完成，提交链
`1dfe24c`(S0) → `10e8123`(S1) → `c98a67b`(S2) → `17950bd`(S3) → `f24080d`(S4)
→ `419da15`(S5) → `2f3ea1e`(S5b 模型源页三态开关) → `6dca04a`(S6)
→ `844589e`(S7) → `14abe8d`(S8)。每个 S 一个可回退提交点。

---

## 六、验收标准

1. 侧边栏「工作台」分组只剩 Dashboard / 会话管理；「新对话」在「最近对话」标签之上。
   **✅ 达成**（e2e 断言用 DOM 纵坐标比较，不靠文案顺序）。
2. 输入框左侧有「＋」按钮，点击弹出三项菜单，**无「共享屏幕和应用」**。
   **✅ 达成**（`chat-attachments.spec.ts` 断言菜单恰为三项；截屏项在
   `navigator.mediaDevices.getDisplayMedia` 缺失时置灰）。
3. 上传 .pdf/.txt/.md/.docx → 输入框上方出现附件 chip → 发送后模型回答能体现文档内容。
   **✅ 达成**（e2e 覆盖到 chip「已解析 N 字」；端到端读文档内容在 S4 手工验收）。
4. 上传图片 + 视觉模型 → 模型能描述图片内容；换成非视觉模型 → 走 OCR，模型能看到图里的文字。
   **✅ 达成**（S6 容器内实测：非视觉模型下 content 含 `【图片 OCR：扫描件.png】` + 识别文本）。
5. 截屏提问 → 浏览器弹一次屏幕捕获授权 → 截图作为附件入输入框 → **授权弹窗关闭后共享立即停止**。
   **✅ 达成**（`captureScreenshot()` 在 `finally` 里 `stop()` 全部轨道，抓一帧即停）。
6. 所有错误路径都有中文提示：格式不支持、文件过大、解析失败、模型不支持视觉且无 OCR 引擎、屏幕捕获被拒绝。
   **✅ 达成**（后端 400/404 中文 detail；OCR 不可用与「未识别到文字」分别给出不同说明；
   截屏失败 `toast.error("未能截屏：屏幕捕获被拒绝或已取消")`）。
7. 后端新增单测全绿（附件端点 + 视觉判定 + 截断 + 越权）；e2e 全绿。
   **✅ 达成**（`tests/core/agent/test_attachments.py`、`tests/core/agent/test_ocr.py`、
   `tests/provider/test_vision_capability.py`；全量非集成 **706 passed**。
   e2e `chat-attachments.spec.ts` 3 条在 8000 实机 dist 通过）。
8. 刷新页面后，历史消息里的附件仍然可见（图片缩略图 + 文档 chip）。
   **✅ 达成**（S2 已把附件元数据随消息落库并在 `history` 回放）。

---

## 七、风险登记

| 风险 | 等级 | 说明 | 应对 |
|---|---|---|---|
| 视觉判定误判 | 中 | 启发式对新模型名可能猜错 | 决策 2a 的显式覆盖；误判时用户可在模型源页一键改。**已实锤一例**：`agnes-3.0-flash` 真支持视觉，但名字里没有 `vl`/`vision`/`4o` 等模式 → 启发式判为不支持；已把该源在库中显式标为「支持视觉」。结论：启发式只能当兜底，**新源默认三态为「自动判断」时要预期它会漏** |
| OCR 无引擎可用 | 中 | 决策 1a 下，用户没配视觉模型源时 OCR 不可用 | 明确中文提示 + 指路「模型源」页；图片仍保存并显示。**实际走了 1b（本地引擎）**，本行降为「引擎缺失/未识别到文字」两种情形，提示文案分开写 |
| 上下文膨胀 | 中 | 文档 + 多图会显著吃 token | 文档截断上限（`ATTACHMENT_MAX_CHARS=60000`）；历史不回放附件正文；单条消息附件数上限 `MAX_PER_MESSAGE=10` |
| 截屏在非安全上下文失效 | 低 | 局域网 IP 访问时不可用 | 能力检测 + 置灰 + 说明 |
| 附件目录无限增长 | 低 | 用户反复上传但不发消息 | 上传即落盘，未发送的附件成为孤儿——落地为「目录按 `{user}/{conversation}/` 组织，删会话即删整目录」，孤儿文件随所属会话消失；`MAX_PER_MESSAGE` 再压一层 |

---

## 八、与既有约定的关系

- **不改历史迁移**：本方案不新增表、不新增列（除决策 2a 的 `supports_vision`，那需要一个新迁移）。
- **不影响单端口部署**：新增端点走同一后端；前端改动需 `npm run build` 重建 dist。
- **PROGRESS.md 待办**：本方案落地后新增一条待办并在进度记录追加一行（含踩坑留档）。
- **文档同步**：`istbot-implement-plan.md` 未覆盖本需求（延伸需求），故只记 PROGRESS.md——与「模型源余额查询」同一处理方式。

---

## 九、实施记录与偏差（2026-09-21 闭环）

| 项 | 计划 | 实际 | 原因 |
|---|---|---|---|
| 附件 id 形态 | `att_7f3a…`（前缀 + 短 id） | 裸 32 位 hex（`uuid4().hex`） | 前缀无功能价值；形状校验用 `^[0-9a-f]{32}$` 即可，少一层约定 |
| 落盘布局 | `{user_id}/{att_id}_{safe_name}` | `{user_id}/{conversation_id}/{att_id}_{safe_filename}` | 多一层**会话**目录，删会话直接 `rmtree`，不必反查「这个 att_id 属于哪个会话」 |
| 上传端点 | `POST /api/v1/agent/attachments`（multipart: file） | 同路径，另带 `conversation_id` 表单字段 | 落盘要按会话分目录，且要在写入前校验**会话归属** |
| 类型判定 | 「校验大小/魔数」 | 文档走**扩展名白名单**（与 `DocumentParser.SUPPORTED_EXTENSIONS` 同源），图片才**嗅探魔数** | 文档格式由解析器定义，魔数嗅探对 docx/pdf 无增量收益；图片的扩展名与 Content-Type 都是客户端可伪造的，必须看字节 |
| OCR 引擎 | 决策 1a（复用视觉源，推荐） | **1b 本地 `rapidocr`** | 用户拍板；见 §三「实际决策」 |
| 孤儿附件清理 | 方案未定 | 目录随会话删除，`MAX_PER_MESSAGE=10` | 用布局本身消掉这个问题，不写定时任务 |

**踩坑留档**

1. **截图首帧未必就绪**：`video.play()` 返回时首帧可能还没解码，立刻 `drawImage` 会得到全黑图 → 等一帧 `requestAnimationFrame` 再画。
2. **OCR 依赖的系统库**：`rapidocr` 硬依 GUI 版 `opencv-python`，slim 镜像先后报 `libxcb.so.1`、`libGL.so.1`；换 `opencv-python-headless` 也躲不掉（依赖是硬编码的）→ Dockerfile 装 `libgl1 libglib2.0-0 libxcb1 libsm6 libxext6 libxrender1`。
3. **测试必须与引擎解耦**：OCR 用例一律 monkeypatch `ocr.recognize` / `ocr.is_available`，否则「本机没装引擎就挂」——这恰恰是会误报的测试。
4. **Windows GBK 控制台**：`scripts/wheelhouse.py` 的 emoji 输出在 GBK 终端抛 `UnicodeEncodeError`（清单已写完、只是末尾打印崩），跑脚本时带 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`。
5. **离线 wheel 源的坑**：`antlr4-python3-runtime==4.9.3` 只有 sdist（`omegaconf` 钉 `==4.9.*`），`pip download --only-binary=:all:` 找不到 → 加入 `scripts/wheelhouse.py` 的 `SDIST_ONLY_PACKAGES`，改走 sdist 离线构建。另外当时清华 PyPI 镜像整站 403（宿主与容器皆是），缺的 wheel 只能从 pypi.org 补下。

**测试落点**

- `tests/core/agent/test_attachments.py`：落盘/读回、`safe_filename`、`describe` 从磁盘反推元数据（不信客户端声明）、`build_turn_content` 各分支（纯文本 / 文档 / 图片 × 视觉 / OCR 回退 / 混合 / 文件丢失退化）。
- `tests/core/agent/test_ocr.py`：`is_available`、引擎单例与失败粘滞、`recognize` 拼行、`build_image_context` 截断。
- `tests/provider/test_vision_capability.py`：三态值 + 模型名启发式命中/未命中。
- `frontend/tests/chat-attachments.spec.ts`：菜单三项（无「共享屏幕」）、文档 chip、截屏 chip。
