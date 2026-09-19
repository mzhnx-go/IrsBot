"""Task 7.4 API 测试 — 知识库路由

建库/列表/详情/删除等操作只碰测试数据库，可真实执行；
上传/检索涉及 Milvus + SiliconFlow 外部依赖，mock 掉 KBManager 只测 HTTP 层。
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import settings
from app.core.db.models import Document as DocumentRecord
from app.core.knowledge_base import manager as kb_manager_mod
from fastapi.testclient import TestClient
from langchain_core.documents import Document as LcDocument
from sqlmodel import select


def _create_kb(client: TestClient, headers: dict[str, str], name: str = "测试库") -> dict:
    r = client.post(
        f"{settings.API_V1_STR}/kb",
        headers=headers,
        json={"name": name, "description": "测试"},
    )
    assert r.status_code == 201
    return r.json()


class TestCreateKB:
    def test_create_success(self, client: TestClient, superuser_token_headers):
        """建库成功 → 201 + id + document_count=0"""
        body = _create_kb(client, superuser_token_headers, "A的库")
        assert "id" in body
        assert body["name"] == "A的库"
        assert body["document_count"] == 0

    def test_create_requires_auth(self, client: TestClient):
        """未登录建库 → 401"""
        r = client.post(
            f"{settings.API_V1_STR}/kb", json={"name": "x"}
        )
        assert r.status_code == 401

    def test_create_missing_name_422(self, client: TestClient, superuser_token_headers):
        """缺必填 name → 422"""
        r = client.post(
            f"{settings.API_V1_STR}/kb", headers=superuser_token_headers, json={}
        )
        assert r.status_code == 422


class TestListKB:
    def test_list_isolates_users(
        self,
        client: TestClient,
        superuser_token_headers,
        normal_user_token_headers,
    ):
        """列表只返回自己的库：A建库，B的列表看不到"""
        _create_kb(client, superuser_token_headers, "A专属库")
        r = client.get(
            f"{settings.API_V1_STR}/kb", headers=normal_user_token_headers
        )
        assert r.status_code == 200
        names = [kb["name"] for kb in r.json()]
        assert "A专属库" not in names


class TestGetDeleteKB:
    def test_get_other_user_404(
        self,
        client: TestClient,
        superuser_token_headers,
        normal_user_token_headers,
    ):
        """越权访问别人的库 → 404（不泄露资源存在性）"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}", headers=normal_user_token_headers
        )
        assert r.status_code == 404

    def test_get_nonexistent_404(
        self, client: TestClient, superuser_token_headers
    ):
        """访问不存在的 kb_id → 404"""
        r = client.get(
            f"{settings.API_V1_STR}/kb/{uuid.uuid4()}",
            headers=superuser_token_headers,
        )
        assert r.status_code == 404

    def test_delete_other_user_404(
        self,
        client: TestClient,
        superuser_token_headers,
        normal_user_token_headers,
    ):
        """越权删除别人的库 → 404"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}", headers=normal_user_token_headers
        )
        assert r.status_code == 404

    def test_delete_own_success(
        self, client: TestClient, superuser_token_headers
    ):
        """删除自己的库 → 200 + message，再查 404"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}", headers=superuser_token_headers
        )
        assert r.status_code == 200
        assert "删除" in r.json()["message"]
        # 删除后再查 → 404
        r2 = client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}", headers=superuser_token_headers
        )
        assert r2.status_code == 404


class _FakeDocument:
    """模拟 upload_document 返回的记录，包含 DocumentOut 需要的全部字段"""
    id = uuid.uuid4()
    filename = "真实文件名.md"
    status = "done"
    chunks_count = 3
    file_size = 100


class TestUploadDocument:
    def test_upload_success(
        self,
        client: TestClient,
        superuser_token_headers,
        monkeypatch,
    ):
        """上传（mock 流水线）→ 201 + done"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        fake = _FakeDocument()
        monkeypatch.setattr(
            kb_manager_mod.KBManager,
            "upload_document",
            AsyncMock(return_value=fake),
        )
        r = client.post(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents",
            headers=superuser_token_headers,
            files={"file": ("原文件.md", "# 退货政策\n七日无理由".encode("utf-8"), "text/markdown")},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "done"
        assert body["chunks_count"] == 3
        assert body["filename"] == "真实文件名.md"

    def test_upload_to_other_user_404(
        self,
        client: TestClient,
        superuser_token_headers,
        normal_user_token_headers,
    ):
        """往别人的库上传 → 404"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.post(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents",
            headers=normal_user_token_headers,
            files={"file": ("x.md", b"data", "text/markdown")},
        )
        assert r.status_code == 404


class TestQueryKB:
    def test_query_calls_manager(
        self,
        client: TestClient,
        superuser_token_headers,
        monkeypatch,
    ):
        """检索（mock manager）→ 200 + results + context"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]

        fake_doc = MagicMock()
        fake_doc.page_content = "命中内容"
        fake_doc.metadata = {"source": "a.md"}

        monkeypatch.setattr(
            kb_manager_mod.KBManager, "query", MagicMock(return_value=[fake_doc])
        )
        monkeypatch.setattr(
            kb_manager_mod.KBManager,
            "get_retrieval_context",
            MagicMock(return_value="[1] 来源: a.md\n命中内容"),
        )

        r = client.post(
            f"{settings.API_V1_STR}/kb/{kb_id}/query",
            headers=superuser_token_headers,
            json={"query": "退货怎么弄", "top_k": 1},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == 1
        assert body["context"]  # 非空

    def test_query_other_user_404(
        self,
        client: TestClient,
        superuser_token_headers,
        normal_user_token_headers,
    ):
        """对别人的库检索 → 404（在调用 manager 之前就拦截）"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.post(
            f"{settings.API_V1_STR}/kb/{kb_id}/query",
            headers=normal_user_token_headers,
            json={"query": "x"},
        )
        assert r.status_code == 404

    def test_query_missing_query_422(
        self, client: TestClient, superuser_token_headers
    ):
        """检索 body 缺 query 字段 → 422（FastAPI 校验拦截）"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.post(
            f"{settings.API_V1_STR}/kb/{kb_id}/query",
            headers=superuser_token_headers,
            json={},
        )
        assert r.status_code == 422

    def test_query_blank_query_422(
        self, client: TestClient, superuser_token_headers
    ):
        """检索 query 为空字符串 → 422"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.post(
            f"{settings.API_V1_STR}/kb/{kb_id}/query",
            headers=superuser_token_headers,
            json={"query": ""},
        )
        assert r.status_code == 422


class TestDeleteDocument:
    """删除文档端点：DB 记录真实操作，VectorStore/磁盘 mock 或容错处理"""

    @pytest.fixture()
    def superuser_id(self, db) -> uuid.UUID:
        from app.models import User
        from sqlmodel import select

        user = db.exec(
            select(User).where(User.email == settings.FIRST_SUPERUSER)
        ).first()
        assert user is not None
        return user.id

    @pytest.fixture()
    def mock_vec_delete(self, monkeypatch):
        """mock 掉 Milvus 删除（测试环境不依赖 Milvus），返回 MagicMock 便于断言调用"""
        from app.api.routes import knowledge_base as kb_routes_mod

        fake = MagicMock(return_value={"delete_count": 3})
        monkeypatch.setattr(
            kb_routes_mod.VectorStore, "delete_by_doc_id", fake
        )
        return fake

    def _create_doc(self, db, user_id, kb_id) -> "DocumentRecord":
        from app.core.db.models import Document as DocumentRecord

        record = DocumentRecord(
            kb_id=kb_id,
            user_id=user_id,
            filename="test_doc.md",
            # 指向不存在的路径：unlink(missing_ok=True) 应容错
            file_path="./uploads/kb_test/__no_such_file__.md",
            status="done",
            chunks_count=3,
            file_size=100,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def test_delete_success(
        self,
        client: TestClient,
        db,
        superuser_token_headers,
        superuser_id,
        mock_vec_delete,
    ):
        """删除自己的文档 → 200 + Milvus 删了 + 列表里消失"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._create_doc(db, superuser_id, kb_id)

        r = client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}",
            headers=superuser_token_headers,
        )
        assert r.status_code == 200
        # Milvus 删除按 doc_id 调用了一次
        mock_vec_delete.assert_called_once_with(str(doc.id))
        # 列表里没了
        docs = client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents",
            headers=superuser_token_headers,
        ).json()
        assert all(d["id"] != str(doc.id) for d in docs)

    def test_delete_doc_of_another_kb_404(
        self,
        client: TestClient,
        db,
        superuser_token_headers,
        superuser_id,
        mock_vec_delete,
    ):
        """用 B 库的 URL 删 A 库的文档 → 404（跨库越权防线）"""
        kb_a = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        kb_b = uuid.UUID(_create_kb(client, superuser_token_headers, "B库")["id"])
        doc = self._create_doc(db, superuser_id, kb_a)

        r = client.delete(
            f"{settings.API_V1_STR}/kb/{kb_b}/documents/{doc.id}",
            headers=superuser_token_headers,
        )
        assert r.status_code == 404
        mock_vec_delete.assert_not_called()

    def test_delete_other_user_404(
        self,
        client: TestClient,
        db,
        superuser_token_headers,
        normal_user_token_headers,
        superuser_id,
        mock_vec_delete,
    ):
        """删别人的库里的文档 → 404"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._create_doc(db, superuser_id, kb_id)

        r = client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}",
            headers=normal_user_token_headers,
        )
        assert r.status_code == 404
        mock_vec_delete.assert_not_called()

    def test_delete_nonexistent_doc_404(
        self,
        client: TestClient,
        superuser_token_headers,
        mock_vec_delete,
    ):
        """随机 doc_id → 404"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{uuid.uuid4()}",
            headers=superuser_token_headers,
        )
        assert r.status_code == 404
        mock_vec_delete.assert_not_called()


class TestListDocuments:
    def test_list_documents_empty(
        self, client: TestClient, superuser_token_headers
    ):
        """刚建的空库，列文档 → 200 + 空列表"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents",
            headers=superuser_token_headers,
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_list_documents_other_user_404(
        self,
        client: TestClient,
        superuser_token_headers,
        normal_user_token_headers,
    ):
        """看别人库的文档 → 404"""
        kb_id = _create_kb(client, superuser_token_headers)["id"]
        r = client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents",
            headers=normal_user_token_headers,
        )
        assert r.status_code == 404


class TestTrash:
    """回收站全链路：软删除 → 列表 → 恢复（重新向量化） → 彻底删除 → 过期惰性清理。

    生命周期约定（对应 routes/knowledge_base.py 的实现）：
    - 软删除：Milvus 向量立刻删、磁盘文件保留、DB 打 deleted_at
    - 恢复：抹掉 deleted_at 并按磁盘文件重新向量化
    - 彻底删除：磁盘文件 + DB 记录一起清（向量早在软删除时就没了）
    - 过期：超过 KB_TRASH_RETENTION_DAYS 的条目在列表时被惰性清理
    """

    @pytest.fixture()
    def superuser_id(self, db) -> uuid.UUID:
        from app.models import User

        user = db.exec(
            select(User).where(User.email == settings.FIRST_SUPERUSER)
        ).first()
        assert user is not None
        return user.id

    @pytest.fixture()
    def mock_vec_delete(self, monkeypatch):
        """mock Milvus 删除（测试环境不连 Milvus），便于断言调用"""
        from app.api.routes import knowledge_base as kb_routes_mod

        fake = MagicMock(return_value={"delete_count": 1})
        monkeypatch.setattr(kb_routes_mod.VectorStore, "delete_by_doc_id", fake)
        return fake

    @pytest.fixture()
    def mock_reindex(self, monkeypatch):
        """mock 恢复时的解析/分块/向量化，返回向量库 mock 以便断言重新写入"""
        async def fake_parse(file_path):
            return [LcDocument("原文")]

        monkeypatch.setattr(kb_manager_mod.DocumentParser, "parse", fake_parse)
        monkeypatch.setattr(
            kb_manager_mod.Chunkers,
            "recursive_character",
            lambda docs: [LcDocument("块1"), LcDocument("块2")],
        )
        store = MagicMock()
        monkeypatch.setattr(
            kb_manager_mod, "VectorStore", MagicMock(return_value=store)
        )
        return store

    @pytest.fixture()
    def doc_file(self, tmp_path):
        """真实落盘文件：软删除要保留它，恢复要读它"""
        f = tmp_path / "trash_me.txt"
        f.write_text("待删除内容", encoding="utf-8")
        return f

    def _make_doc(self, db, user_id, kb_id, file_path, filename="trash_me.txt"):
        record = DocumentRecord(
            kb_id=kb_id,
            user_id=user_id,
            filename=filename,
            file_path=str(file_path),
            status="done",
            chunks_count=2,
            file_size=18,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def _trash(self, client, headers):
        return client.get(f"{settings.API_V1_STR}/kb/trash", headers=headers).json()

    def _active_docs(self, client, headers, kb_id):
        return client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents", headers=headers
        ).json()

    def test_soft_delete_keeps_file_and_enters_trash(
        self,
        client: TestClient,
        db,
        superuser_token_headers,
        superuser_id,
        mock_vec_delete,
        doc_file,
    ):
        """软删除：向量删了、文件还在、活跃列表消失、回收站出现（含库名与到期时间）"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)

        r = client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}",
            headers=superuser_token_headers,
        )
        assert r.status_code == 200
        assert "回收站" in r.json()["message"]
        mock_vec_delete.assert_called_once_with(str(doc.id))

        assert doc_file.exists()  # 磁盘文件必须保留，否则恢复不了
        assert all(
            d["id"] != str(doc.id)
            for d in self._active_docs(client, superuser_token_headers, kb_id)
        )

        item = next(
            t for t in self._trash(client, superuser_token_headers)
            if t["id"] == str(doc.id)
        )
        assert item["kb_name"] == "测试库"
        assert item["filename"] == "trash_me.txt"
        assert item["kb_id"] == str(kb_id)
        expected = datetime.fromisoformat(item["deleted_at"]) + timedelta(
            days=settings.KB_TRASH_RETENTION_DAYS
        )
        assert datetime.fromisoformat(item["expires_at"]) == expected

    def test_soft_delete_excludes_from_document_count(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, doc_file,
    ):
        """软删除后库详情/列表的 document_count 不再把它算进去"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)
        assert client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}", headers=superuser_token_headers
        ).json()["document_count"] == 1

        client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}",
            headers=superuser_token_headers,
        )

        assert client.get(
            f"{settings.API_V1_STR}/kb/{kb_id}", headers=superuser_token_headers
        ).json()["document_count"] == 0
        listed = client.get(
            f"{settings.API_V1_STR}/kb", headers=superuser_token_headers
        ).json()
        assert next(k for k in listed if k["id"] == str(kb_id))["document_count"] == 0

    def test_delete_already_trashed_404(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, doc_file,
    ):
        """重复删除同一文档 → 404，且不会二次调用 Milvus 删除"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)
        url = f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}"

        assert client.delete(url, headers=superuser_token_headers).status_code == 200
        assert client.delete(url, headers=superuser_token_headers).status_code == 404
        assert mock_vec_delete.call_count == 1

    def test_restore_reindexes_and_returns_to_kb(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, mock_reindex, doc_file,
    ):
        """恢复：重新向量化 + 回到活跃列表 + 退出回收站"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)
        client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}",
            headers=superuser_token_headers,
        )

        r = client.post(
            f"{settings.API_V1_STR}/kb/trash/{doc.id}/restore",
            headers=superuser_token_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "done"
        assert r.json()["chunks_count"] == 2  # 取自重新分块的结果
        mock_reindex.add_documents.assert_called_once()

        assert any(
            d["id"] == str(doc.id)
            for d in self._active_docs(client, superuser_token_headers, kb_id)
        )
        assert all(
            t["id"] != str(doc.id)
            for t in self._trash(client, superuser_token_headers)
        )

    def test_restore_missing_file_409(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, mock_reindex,
    ):
        """文件在保留期内被外力清掉 → 409，不造「done 但检索不到」的假记录"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, "./uploads/kb_test/__gone__.txt")
        client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}",
            headers=superuser_token_headers,
        )

        r = client.post(
            f"{settings.API_V1_STR}/kb/trash/{doc.id}/restore",
            headers=superuser_token_headers,
        )
        assert r.status_code == 409
        mock_reindex.add_documents.assert_not_called()  # 没白跑一遍向量化
        # 仍然待在回收站里，没有变成活跃文档
        assert any(
            t["id"] == str(doc.id)
            for t in self._trash(client, superuser_token_headers)
        )

    def test_restore_active_document_404(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, doc_file,
    ):
        """不在回收站的文档（还活着）不能走恢复端点 → 404"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)

        r = client.post(
            f"{settings.API_V1_STR}/kb/trash/{doc.id}/restore",
            headers=superuser_token_headers,
        )
        assert r.status_code == 404

    def test_restore_nonexistent_404(
        self, client: TestClient, superuser_token_headers, mock_vec_delete
    ):
        """随机 doc_id → 404"""
        r = client.post(
            f"{settings.API_V1_STR}/kb/trash/{uuid.uuid4()}/restore",
            headers=superuser_token_headers,
        )
        assert r.status_code == 404

    def test_purge_removes_file_and_row(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, doc_file,
    ):
        """彻底删除：磁盘文件与 DB 记录一起消失，再操作 → 404"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)
        doc_id = doc.id  # 先取出来：记录被删后，ORM 实例的属性会取不到
        client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc_id}",
            headers=superuser_token_headers,
        )

        r = client.delete(
            f"{settings.API_V1_STR}/kb/trash/{doc_id}",
            headers=superuser_token_headers,
        )
        assert r.status_code == 200
        assert "彻底删除" in r.json()["message"]
        assert not doc_file.exists()

        db.expire_all()
        assert db.exec(
            select(DocumentRecord).where(DocumentRecord.id == doc_id)
        ).first() is None
        # 记录没了，再删/再恢复都 404
        assert client.delete(
            f"{settings.API_V1_STR}/kb/trash/{doc_id}",
            headers=superuser_token_headers,
        ).status_code == 404
        assert client.post(
            f"{settings.API_V1_STR}/kb/trash/{doc_id}/restore",
            headers=superuser_token_headers,
        ).status_code == 404

    def test_purge_active_document_404(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, doc_file,
    ):
        """没进回收站的文档不能走彻底删除 → 404（否则会被绕过软删直接抹掉）"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)

        r = client.delete(
            f"{settings.API_V1_STR}/kb/trash/{doc.id}",
            headers=superuser_token_headers,
        )
        assert r.status_code == 404
        assert doc_file.exists()

    def test_trash_isolates_users(
        self, client: TestClient, db, superuser_token_headers,
        normal_user_token_headers, superuser_id, mock_vec_delete, doc_file,
    ):
        """回收站是每人一份：B 看不到 A 的条目，也不能恢复/彻底删除"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)
        client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc.id}",
            headers=superuser_token_headers,
        )

        assert all(
            t["id"] != str(doc.id)
            for t in self._trash(client, normal_user_token_headers)
        )
        assert client.post(
            f"{settings.API_V1_STR}/kb/trash/{doc.id}/restore",
            headers=normal_user_token_headers,
        ).status_code == 404
        assert client.delete(
            f"{settings.API_V1_STR}/kb/trash/{doc.id}",
            headers=normal_user_token_headers,
        ).status_code == 404
        assert doc_file.exists()  # 别人的 404 不该顺手把文件删了

    def test_list_trash_purges_expired(
        self, client: TestClient, db, superuser_token_headers, superuser_id,
        mock_vec_delete, doc_file,
    ):
        """超过保留期的条目在「打开回收站」时被惰性清理（文件 + 记录都清）"""
        kb_id = uuid.UUID(_create_kb(client, superuser_token_headers)["id"])
        doc = self._make_doc(db, superuser_id, kb_id, doc_file)
        doc_id = doc.id  # 先取出来：记录被清理后，ORM 实例的属性会取不到
        client.delete(
            f"{settings.API_V1_STR}/kb/{kb_id}/documents/{doc_id}",
            headers=superuser_token_headers,
        )

        # 把进回收站的时间手动挪到保留期之外
        db.expire_all()
        record = db.get(DocumentRecord, doc_id)
        record.deleted_at = datetime.now(timezone.utc) - timedelta(
            days=settings.KB_TRASH_RETENTION_DAYS + 1
        )
        db.add(record)
        db.commit()

        assert all(
            t["id"] != str(doc_id)
            for t in self._trash(client, superuser_token_headers)
        )
        assert not doc_file.exists()
        db.expire_all()
        assert db.exec(
            select(DocumentRecord).where(DocumentRecord.id == doc_id)
        ).first() is None

    def test_trash_requires_auth(self, client: TestClient):
        """未登录看回收站 → 401"""
        assert client.get(f"{settings.API_V1_STR}/kb/trash").status_code == 401