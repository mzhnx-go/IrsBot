# ── 标准库 ──
import shutil
import uuid
from datetime import datetime, timedelta
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
from app.core.db.sqlmodel_models import get_datetime_utc
from app.core.knowledge_base.manager import KBManager, invalidate_kb_cache
from app.core.knowledge_base.vec_store import VectorStore

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


class TrashDocumentOut(BaseModel):
    """回收站条目：DocumentOut 的字段 + 归属库 + 生命周期时间点。

    带 kb_name 是因为回收站是跨库的扁平列表，用户需要知道「这是哪个库的文件」。
    expires_at 由后端算好下发，前端不必再复制一遍保留期规则。
    """
    id: uuid.UUID
    kb_id: uuid.UUID
    kb_name: str
    filename: str
    status: str
    chunks_count: int
    file_size: int
    deleted_at: datetime
    expires_at: datetime


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


def _active_docs(kb: KBRecord) -> list[DocumentRecord]:
    """库内「未进回收站」的文档。

    走关系属性而不是再查一次库：调用方（列表、详情）本来就要取 kb，
    顺带过滤比多开一条 SELECT 划算；Document 数量在单库量级下不成问题。
    """
    return [d for d in kb.documents if d.deleted_at is None]


def _get_trashed_doc(
    doc_id: uuid.UUID, session: Session, current_user
) -> DocumentRecord:
    """取「自己回收站里」的文档——不在回收站（含已彻底删除）一律 404"""
    doc = session.get(DocumentRecord, doc_id)
    if not doc or doc.user_id != current_user.id or doc.deleted_at is None:
        raise HTTPException(status_code=404, detail="回收站中不存在该文档")
    return doc


def _purge_expired_trash(session: Session) -> None:
    """惰性清理：把超过保留期的回收站文档真正删掉（磁盘文件 + DB 记录）。

    没有常驻定时任务，改成「打开回收站时顺手扫一遍」——本地单机应用
    没有 7x24 的调度器，惰性清理既不增加运维面，又能保证用户看到的
    回收站列表永远只有尚未过期的条目。

    Milvus 向量不需要在这里删：软删除那一刻就已经摘掉了。
    """
    deadline = get_datetime_utc() - timedelta(days=settings.KB_TRASH_RETENTION_DAYS)
    expired = session.scalars(
        select(DocumentRecord).where(
            DocumentRecord.deleted_at.is_not(None),
            DocumentRecord.deleted_at < deadline,
        )
    ).all()
    if not expired:
        return
    for doc in expired:
        Path(doc.file_path).unlink(missing_ok=True)
        session.delete(doc)
    session.commit()


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
        KBOut(
            id=k.id, name=k.name, description=k.description,
            document_count=len(_active_docs(k)),
        )
        for k in kbs
    ]


# ── 回收站 ──
# ⚠️ 必须声明在 GET /{kb_id} 之前：FastAPI 按注册顺序匹配，否则 "/kb/trash"
#    会被当成 kb_id="trash" 去解析 UUID，直接 422。
@router.get("/trash", response_model=list[TrashDocumentOut])
def list_trash(session: SessionDep, current_user: CurrentUser):
    """回收站列表：当前用户跨知识库的已删文档（顺手清理过期条目）"""
    _purge_expired_trash(session)
    docs = session.scalars(
        select(DocumentRecord)
        .where(
            DocumentRecord.user_id == current_user.id,
            DocumentRecord.deleted_at.is_not(None),
        )
        .order_by(DocumentRecord.deleted_at.desc())
    ).all()
    if not docs:
        return []

    kb_ids = {d.kb_id for d in docs}
    kb_names = {
        k.id: k.name
        for k in session.scalars(select(KBRecord).where(KBRecord.id.in_(kb_ids))).all()
    }
    retention = timedelta(days=settings.KB_TRASH_RETENTION_DAYS)
    return [
        TrashDocumentOut(
            id=d.id, kb_id=d.kb_id, kb_name=kb_names.get(d.kb_id, "已删除的知识库"),
            filename=d.filename, status=d.status, chunks_count=d.chunks_count,
            file_size=d.file_size, deleted_at=d.deleted_at,
            expires_at=d.deleted_at + retention,
        )
        for d in docs
    ]


@router.post("/trash/{doc_id}/restore", response_model=DocumentOut)
async def restore_trashed_document(
    doc_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """恢复回收站文档：退回原知识库，并按磁盘文件重新向量化。

    软删除时向量已从 Milvus 摘掉，所以恢复不能只是把 deleted_at 抹掉——
    必须重跑一遍解析/分块/向量化，否则会出现「文档在列表里但检索不到」
    的哑记录。
    """
    doc = _get_trashed_doc(doc_id, session, current_user)
    if not Path(doc.file_path).exists():
        # 保留期内文件被外力清掉（手工删目录 / 从备份回滚）——如实报错，
        # 不造一条「done 但检索不到」的假记录
        raise HTTPException(status_code=409, detail="原文件已丢失，无法恢复")

    doc.deleted_at = None
    session.add(doc)
    session.commit()

    try:
        await KBManager(session=session).index_document(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档重新入库失败: {e}")
    return doc


@router.delete("/trash/{doc_id}")
def purge_trashed_document(
    doc_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """彻底删除回收站文档：磁盘文件 + DB 记录，不可恢复。

    向量在软删除时已清，这里不需要再动 Milvus。
    """
    doc = _get_trashed_doc(doc_id, session, current_user)
    Path(doc.file_path).unlink(missing_ok=True)
    session.delete(doc)
    session.commit()
    return {"message": "文档已彻底删除"}


@router.get("/{kb_id}", response_model=KBOut)
def get_kb(kb_id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """知识库详情"""
    kb = _get_owned_kb(kb_id, session, current_user)
    return KBOut(
        id=kb.id, name=kb.name, description=kb.description,
        document_count=len(_active_docs(kb)),
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
        # filename 存原始名（展示用），磁盘文件仍是带 UUID 的 stored_name（file_path 已记录），
        # 展示层从此看不到 UUID
        record = await mgr.upload_document(kb_id=kb_id, file_path=str(dest), filename=safe_name, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档处理失败: {e}")

    return record

@router.get("/{kb_id}/documents", response_model=list[DocumentOut])
def list_kb_documents(kb_id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """查看知识库内文档及处理状态"""
    kb = _get_owned_kb(kb_id, session, current_user)
    docs = session.scalars(
        select(DocumentRecord).where(
            DocumentRecord.kb_id == kb_id,
            DocumentRecord.deleted_at.is_(None),  # 回收站里的不算「库内文档」
        )
    ).all()
    return [
        DocumentOut(id=d.id, filename=d.filename, status=d.status, chunks_count=d.chunks_count, file_size=d.file_size)
        for d in docs
    ]

@router.delete("/{kb_id}/documents/{doc_id}")
def delete_kb_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """删除单个文档 → 移入回收站（软删除）。

    三处状态各自处理：
    - Milvus 向量：立即删。检索必须马上看不到它，这是删除的核心语义。
    - 磁盘文件：保留，回收站恢复要靠它重新向量化。
    - DB 记录：打上 deleted_at，从「库内文档」移到回收站列表。
    超过保留期（KB_TRASH_RETENTION_DAYS）由 _purge_expired_trash 真正删除。
    """
    kb = _get_owned_kb(kb_id, session, current_user)
    doc = session.get(DocumentRecord, doc_id)
    if not doc or doc.kb_id != kb.id or doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="文档不存在")

    VectorStore(kb_id=str(kb_id)).delete_by_doc_id(str(doc_id))
    invalidate_kb_cache(str(kb_id))
    doc.deleted_at = get_datetime_utc()
    session.add(doc)
    session.commit()
    return {"message": "文档已移入回收站"}

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




    

  