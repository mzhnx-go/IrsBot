# ── 标准库 ──
import uuid
from pathlib import Path

# ── 第三方库 ──
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

# ── 项目内部 ──
from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.db.models import Document as DocumentRecord
from app.core.db.models import KnowledgeBase as KBRecord
from app.core.knowledge_base.manager import KBManager, invalidate_kb_cache
from app.core.knowledge_base.vec_store import VectorStore

import shutil
router = APIRouter(prefix="/kb", tags=["knowledge-base"])

UPLOAD_ROOT = Path(settings.KB_FILE_STORAGE_DIR)  # 上传文件落盘目录（按环境隔离）


class KBCreate(BaseModel):
    name: str
    description: str | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    chunks_count: int
    file_size: int


class KBOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    document_count: int


class KBQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索问题，不能为空")
    top_k: int = Field(4, le=20, ge=1)


class ChunkOut(BaseModel):
    content: str
    source: str | None = None


class KBQueryResponse(BaseModel):
    results: list[ChunkOut]
    context: str


# --内部工具 --
def _get_owned_kb(kb_id: uuid.UUID, session: Session, current_user) -> KBRecord:
    """取知识库并校验归属——不是你的库一律 404"""
    kb = session.get(KBRecord, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


# ── 知识库 CRUD ──
@router.post("", response_model=KBOut, status_code=201)
def create_kb(kb_in: KBCreate, session: SessionDep, current_user: CurrentUser):
    kb = KBRecord(
        user_id=current_user.id,
        name=kb_in.name,
        description=kb_in.description
    )
    session.add(kb)
    session.commit()
    session.refresh(kb)
    return KBOut(id=kb.id, name=kb.name, description=kb.description, document_count=0)


@router.get("", response_model=list[KBOut])
def list_kbs(session: SessionDep, current_user: CurrentUser):
    kbs = session.scalars(
        select(KBRecord).where(KBRecord.user_id == current_user.id)
    ).all()
    return [
        KBOut(id=k.id, name=k.name, description=k.description, document_count=len(k.documents))
        for k in kbs
    ]


@router.get("/{kb_id}", response_model=KBOut)
def get_kb(kb_id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """知识库详情"""
    kb = _get_owned_kb(kb_id, session, current_user)
    return KBOut(
        id=kb.id, name=kb.name, description=kb.description,
        document_count=len(kb.documents),
    )


@router.delete("/{kb_id}")
def delete_kb(kb_id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """删除知识库：向量集合 + 缓存 + 数据库记录，三处都要清"""
    kb = _get_owned_kb(kb_id, session, current_user)
    # 1. 删 Milvus collection（向量数据）
    VectorStore(kb_id=str(kb_id)).delete_collection()
    # 2. 清 BM25 检索缓存
    invalidate_kb_cache(str(kb_id))
    shutil.rmtree(UPLOAD_ROOT / str(kb_id), ignore_errors=True) 
    # 3. 删 DB 记录（documents 外键级联删除）
    session.delete(kb)
    session.commit()
    return {"message": "知识库已删除"}


# ── 文档管理 ──
@router.post("/{kb_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_kb_document(
    session: SessionDep,
    current_user: CurrentUser,
    kb_id: uuid.UUID,
    file: UploadFile = File(...),
):
    """上传文档 → 解析 → 分块 → 向量化（完整 RAG 写入流水线）"""
    kb = _get_owned_kb(kb_id, session, current_user)
    safe_name = Path(file.filename or "unnamed.txt").name
    
    dest_dir = UPLOAD_ROOT / str(kb_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest = dest_dir / stored_name
    
    content = await file.read()
    dest.write_bytes(content)

    mgr = KBManager(session=session)
    try:
        record = await mgr.upload_document(kb_id=kb_id, file_path=str(dest), filename=stored_name, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档处理失败: {e}")

    return record

@router.get("/{kb_id}/documents", response_model=list[DocumentOut])
def list_kb_documents(kb_id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """查看知识库内文档及处理状态"""
    kb = _get_owned_kb(kb_id, session, current_user)
    docs = session.scalars(
        select(DocumentRecord).where(DocumentRecord.kb_id == kb_id)
    ).all()
    return [
        DocumentOut(id=d.id, filename=d.filename, status=d.status, chunks_count=d.chunks_count, file_size=d.file_size)
        for d in docs
    ]

# ── 检索 ──
@router.post("/{kb_id}/query", response_model=KBQueryResponse)
def query_kb(
    kb_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    body: KBQueryRequest,
):
    """知识库检索：返回命中的块 + 拼好的上下文"""
    kb = _get_owned_kb(kb_id, session, current_user)
    mgr = KBManager(session=session)
    results = mgr.query(kb_id=kb.id, query=body.query, top_k=body.top_k)
    context = mgr.get_retrieval_context(results)
    return KBQueryResponse(
        results=[
            ChunkOut(content=d.page_content, source=d.metadata.get("source"))
            for d in results
        ],
        context=context
    )




    

  