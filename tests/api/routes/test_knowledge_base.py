"""Task 7.4 API 测试 — 知识库路由

建库/列表/详情/删除等操作只碰测试数据库，可真实执行；
上传/检索涉及 Milvus + SiliconFlow 外部依赖，mock 掉 KBManager 只测 HTTP 层。
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.knowledge_base import manager as kb_manager_mod


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