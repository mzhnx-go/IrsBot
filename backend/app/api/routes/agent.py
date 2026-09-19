# ── 标准库 ──
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Literal
from urllib.parse import quote

# ── 第三方库 ──
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

# ── 项目内部 ──
from app.api.deps import CurrentUser, SessionDep
from app.core import crud
from app.core.agent.conversation import ConversationManager
from app.core.agent.export import render_export
from app.core.db.sqlmodel_models import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationRename,
    ConversationResponse,
    MCPServerConnectResponse,
    MCPServerCreate,
    MCPServerResponse,
    MCPServerUpdate,
)
from app.core.mcp.bridge import MCPToolBridge
from app.core.mcp.client import MCPClient
from app.core.pipeline import PipelineContext, PipelineScheduler
from app.core.pipeline.base import EventKey
from app.core.pipeline.stages import (
    PostProcessStage,
    PreProcessStage,
    ProcessStage,
    RateLimitStage,
)
from app.core.skills.manager import SkillManager
from app.core.skills.security import (
    check_skill_md_size,
    check_zip_safety,
    validate_skill_name,
)

router = APIRouter(prefix="/agent",tags=["agent"])


#: 单会话导出的消息条数上限。
#: 导出是一次性把全部消息拼进内存再返回，必须有个明确上限兜底；
#: 正常对话远达不到这个量级，真触发说明数据异常，宁可截断也不能把进程撑爆。
EXPORT_MESSAGE_LIMIT = 10000


def _content_disposition(filename: str) -> str:
    """拼出支持中文文件名的 Content-Disposition 头。

    为什么不能只写 filename="中文.docx"：
        响应头按 latin-1 编码，非 ASCII 字符会让 Starlette 直接抛
        UnicodeEncodeError（表现为 500）。RFC 6266 的解法是双写——
        给老客户端一个纯 ASCII 的 filename 兜底，再给现代浏览器一个
        filename*=UTF-8''<百分号编码> 的真名，浏览器优先取后者。

    参数:
        filename: 目标文件名（可能含中文）。

    返回:
        完整的 Content-Disposition 头值。
    """
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "conversation"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    conversation_in: ConversationCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """创建一个新对话"""
    conversation = crud.create_conversation(
        session,
        title=conversation_in.title,
        user_id=current_user.id,
    )
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        session_id=conversation.session_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )

@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 20,
):
    """获取当前用户的对话列表"""
    conversations, total = crud.list_conversations(
        session,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return [
        ConversationResponse(
            id=c.id,
            title=c.title,
            session_id=c.session_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conversations
    ]


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationRename,
    session: SessionDep,
    current_user: CurrentUser,
):
    """重命名一个对话"""
    conversation = crud.get_conversation(
        session,
        conv_id=conversation_id,
        user_id=current_user.id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    conversation.title = body.title
    session.commit()
    session.refresh(conversation)
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        session_id=conversation.session_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """删除一个对话（会话内的消息随之级联删除）"""
    deleted = crud.delete_conversation(
        session,
        conv_id=conversation_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"message": "对话已删除"}


@router.get("/conversations/{conversation_id}/export")
def export_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    format: Literal["md", "txt", "json", "docx", "pdf"] = Query(
        default="md",
        description="导出格式：md / txt / json / docx / pdf",
    ),
):
    """把整个对话导出成文件下载。

    与其它会话端点一致，先按 user_id 校验归属，越权一律 404
    （而不是 403 —— 403 会泄露「这个 id 真实存在」）。

    参数:
        conversation_id: 会话 ID。
        format: 导出格式，取自 ExportFormat。

    返回:
        附件响应（Content-Disposition: attachment），
        Content-Type 与扩展名由格式决定。
    """
    conversation = crud.get_conversation(
        session,
        conv_id=conversation_id,
        user_id=current_user.id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")

    messages = ConversationManager(session).get_messages(
        conversation.id, limit=EXPORT_MESSAGE_LIMIT
    )
    exported = render_export(conversation, messages, format)

    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"Content-Disposition": _content_disposition(exported.filename)},
    )


@router.post("/conversations/{conversation_id}/chat",response_model=ChatResponse)
async def chat(
    conversation_id: uuid.UUID,
    chat_request: ChatRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """发送消息并获取 AI回复（Pipeline 流水线版本）"""
    conversation = crud.get_conversation(
        session,
        conv_id=conversation_id,
        user_id=current_user.id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    conv_manager = ConversationManager(session)
    conv_manager.add_message(
        conv_id=conversation.id,
        role="user",
        content=chat_request.message,
    )
    history = conv_manager.get_context_messages(conversation.id)

    context = PipelineContext(
        user_id=current_user.id,
        session_id=str(conversation_id),
        conversation_id=conversation.id,
        event_data={
            EventKey.SESSION: session,
            EventKey.USER_MESSAGE: chat_request.message,
            EventKey.HISTORY: history,
        },
    )

    scheduler = PipelineScheduler([
        RateLimitStage(),
        PreProcessStage(),
        ProcessStage(),
        PostProcessStage(),
    ])
    result = await scheduler.execute(context)

    if result.event_data.get(EventKey.RATE_LIMITED):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    if EventKey.ERROR in result.event_data:
        raise HTTPException(status_code=400, detail="发生错误")

    agent_result = result.event_data[EventKey.AGENT_RESULT]
    reply = agent_result["messages"][-1].content
    return ChatResponse(
        reply=reply,
        conversation_id=conversation.id,
    )


@router.post("/mcp-servers", response_model=MCPServerResponse, status_code=201)
def create_mcp_server(
    server_in: MCPServerCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """创建MCP Server 配置"""
    server = crud.create_mcp_server(
        session,
        name=server_in.name,
        transport_type=server_in.transport_type,
        user_id=current_user.id,
        url=server_in.url,
        command=server_in.command,
        args=server_in.args,
        env_vars=server_in.env_vars,
        is_active=server_in.is_active,
    )
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        transport_type=server.transport_type,
        url=server.url,
        command=server.command,
        args=server.args,
        env_vars=server.env_vars,
        is_active=server.is_active,
        tools=server.tools,
        created_at=server.created_at,
    )

@router.get("/mcp-servers", response_model=list[MCPServerResponse])
def list_mcp_servers(
    session: SessionDep,
    current_user: CurrentUser,
    skip:int = 0,
    limit: int = 100,
):
    """获取当前用户的MCP Server 列表"""
    servers = crud.list_mcp_servers(
        session,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return [
        MCPServerResponse(
            id=s.id,
            name=s.name,
            transport_type=s.transport_type,
            url=s.url,
            command=s.command,
            args=s.args,
            env_vars=s.env_vars,
            is_active=s.is_active,
            tools=s.tools,
            created_at=s.created_at,
        )
        for s in servers
    ]

@router.get("/mcp-servers/{server_id}", response_model=MCPServerResponse)
def get_mcp_server(
    server_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """获取单个MCP Server 详细"""
    server = crud.get_mcp_server(
        session,
        server_id=server_id,
        user_id=current_user.id,
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server不存在")
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        transport_type=server.transport_type,
        url=server.url,
        command=server.command,
        args=server.args,
        env_vars=server.env_vars,
        is_active=server.is_active,
        tools=server.tools,
        created_at=server.created_at,
    )

@router.patch("/mcp-servers/{server_id}", response_model=MCPServerResponse)
def update_mcp_server(
    server_id: uuid.UUID,
    server_in: MCPServerUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """更新MCP Server配置"""
    # 1. 先获取现有的 MCP Server
    server = crud.get_mcp_server(
        session,
        server_id=server_id,
        user_id=current_user.id,
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    # 2. 更新字段
    update_data = server_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(server, key, value)

    # 3. 保存到数据库
    session.commit()
    session.refresh(server)

    return MCPServerResponse(
        id=server.id,
        name=server.name,
        transport_type=server.transport_type,
        url=server.url,
        command=server.command,
        args=server.args,
        env_vars=server.env_vars,
        is_active=server.is_active,
        tools=server.tools,
        created_at=server.created_at,
    )

@router.delete("/mcp-servers/{server_id}")
def delete_mcp_server(
    server_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """删除MCP Server配置"""
    deleted = crud.delete_mcp_server(
        session,
        server_id=server_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    return {"message": "MCP Server 已删除"}

@router.post("/mcp-servers/{server_id}/connect", response_model=MCPServerConnectResponse)
async def connect_mcp_server(
    server_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """测试连接 MCP Server 并获取可用工具列表"""
    # 1. 获取 MCP Server 配置
    server = crud.get_mcp_server(
        session,
        server_id=server_id,
        user_id=current_user.id,
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    # 2. 创建 MCP 客户端
    client = MCPClient(
        transport_type=server.transport_type,
        url=server.url,
        command=server.command,
        args=server.args,
        env=server.env_vars,
    )

    try:
        # 3. 根据传输类型连接
        if server.transport_type == "sse":
            await client.connect_sse()
        elif server.transport_type == "stdio":
            await client.connect_stdio()
        elif server.transport_type == "streamable_http":
            await client.connect_streamable_http()

        # 4. 获取工具列表
        tools = await client.list_tools()

        # 5. 更新数据库中的工具缓存
        server.tools = tools
        session.commit()

        return MCPServerConnectResponse(
            success=True,
            message=f"成功连接到 {server.name}，发现 {len(tools)} 个工具",
            tools=tools,
        )

    except Exception as e:
        return MCPServerConnectResponse(
            success=False,
            message=f"连接失败: {str(e)}",
            tools=[],
        )

    finally:
        await client.close()

# ═══════════════ Skill 管理 ═══════════════
SKILLS_DIR = Path("skills")

@router.get("/skills")
async def list_skills(current_user: CurrentUser) -> list[dict]:
    """列出所有已安装的 Skill"""
    manager = SkillManager.instance()
    skills = manager.list_skills()
    return [
        {
            "name": s.name,
            "description": s.description,
            "trigger": s.trigger,
        }
        for s in skills
    ]

@router.get("/skills/{skill_name}")
async def get_skill_detail(skill_name: str, current_user: CurrentUser) -> dict:
    """获取某个Skill 的详情(含完整指令) """
    manager = SkillManager.instance()
    info = manager.get_skill(skill_name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    return {
        "name": info.name,
        "description": info.description,
        "trigger": info.trigger,
        "instructions": info.instructions,
    }

@router.delete("/skills/{skill_name}")
async def delete_skill(skill_name: str, current_user: CurrentUser) -> dict:
    """删除某个 Skill"""
    if not validate_skill_name(skill_name):
        raise HTTPException(status_code=400, detail="Skill 名称非法")
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    if not str(skill_dir.resolve()).startswith(str(SKILLS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Skill 存在路径穿越")
    shutil.rmtree(skill_dir)

    manager = SkillManager.instance()
    manager.scan()
    return {"success": True, "message": f"Skill '{skill_name}' 已删除"}

@router.post("/skills/scan")
async def scan_skills(current_user: CurrentUser) -> dict:
    """重新扫描 skills 目录"""
    manager = SkillManager.instance()
    skills = manager.scan()
    return {"success": True, "count": len(skills), "skills": list(skills.keys())}

@router.post("/skills/install")
async def install_skill(
    skill_zip: UploadFile = File(...),
    current_user: CurrentUser = CurrentUser,
) -> dict:
    """上传 ZIP 安装 Skill"""
    import os
    import shutil
    import tempfile

    # 1. 生成唯一的临时文件（避免并发上传时互相覆盖）
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip")
    tmp_path = Path(tmp_name)
    
    # 异步写入临时文件，防止大文件撑爆内存
    with open(tmp_fd, "wb") as f:
        content = await skill_zip.read()
        f.write(content)

    try:
        # 2. 安全检查（ZIP Slip / 文件数等）
        errors = check_zip_safety(str(tmp_path), str(SKILLS_DIR))
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))

        # 3. 解压到临时目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                zf.extractall(tmp_dir)
            
            tmp_path_obj = Path(tmp_dir)
            skill_md = next(tmp_path_obj.rglob("SKILL.md"), None)
            if skill_md is None:
                raise HTTPException(status_code=400, detail="ZIP 中缺少 SKILL.md")

            # 4. 解析验证
            from app.core.skills.parser import SkillParser
            parser = SkillParser()
            try:
                info = parser.parse(str(skill_md.parent))
            except (ValueError, FileNotFoundError) as e:
                raise HTTPException(status_code=400, detail=f"SKILL.md 解析失败: {e}")
            
            if not check_skill_md_size(str(skill_md)):
                raise HTTPException(status_code=400, detail="SKILL.md 超过 1MB 限制")

            # 5. 核心安全校验：防路径穿越
            target_dir = SKILLS_DIR / info.name
            if not str(target_dir.resolve()).startswith(str(SKILLS_DIR.resolve())):
                raise HTTPException(status_code=400, detail="非法的 Skill 名称，存在路径穿越风险")

            # 6. 原子性替换：先复制到临时目录，再整体替换（防断电丢失）
            temp_target = SKILLS_DIR / f".tmp_{info.name}"
            if temp_target.exists():
                shutil.rmtree(temp_target)
            shutil.copytree(skill_md.parent, temp_target)
            
            # 替换旧目录（os.replace 是原子操作，比 rmtree + copytree 更安全）
            if target_dir.exists():
                shutil.rmtree(target_dir)
            os.replace(temp_target, target_dir)

        # 7. 重新扫描
        manager = SkillManager.instance()
        manager.scan()

        return {"success": True, "name": info.name, "description": info.description}

    finally:
        # 8. 确保临时文件一定被清理
        if tmp_path.exists():
            tmp_path.unlink()







    
    













