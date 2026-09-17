"""MCP Server API 测试
这个文件测试 MCP Server 管理接口的CRUD功能。
"""

from app.core.config import settings
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

def test_create_mcp_server(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """测试创建MCP Server
    测试步骤：
    1. 准备测试数据 (MCP Server 配置)
    2. 发送POST请求创建
    3. 验证返回状态码和数据
    """

    data = {
        "name": "测试服务",
        "transport_type": "sse",
        "url": "http://localhost:8080/sse",
    }
    response = client.post(
        f"{settings.API_V1_STR}/agent/mcp-servers",
        headers=superuser_token_headers,
        json=data,
    )

    assert response.status_code == 201
    result = response.json()
    assert result["name"] == "测试服务"
    assert result["transport_type"] == "sse"
    assert result["url"] == "http://localhost:8080/sse"
    assert result["is_active"] is True

def test_list_mcp_servers(
        client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """测试 MCP Server 列表"""
        create_data = {
            "name": "列表测试服务",
            "transport_type": "sse",
            "url": "http://localhost:8081/sse",
        }
        client.post(
            f"{settings.API_V1_STR}/agent/mcp-servers",
            headers=superuser_token_headers,
            json=create_data,
        )

        response = client.get(
            f"{settings.API_V1_STR}/agent/mcp-servers",
            headers=superuser_token_headers,
        )
    
        assert response.status_code == 200
        result = response.json()
        assert isinstance(result, list)
        assert len(result) >= 1

def test_get_mcp_server(
    client: TestClient,
    superuser_token_headers: dict[str, str]
) -> None:
    """测试获取单个MCP Server"""
    create_data = {
        "name": "获取测试服务",
        "transport_type": "stdio",
        "command": "python",
        "args": ["-m", "mcp_server"],
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/agent/mcp-servers",
        headers=superuser_token_headers,
        json=create_data,
    )
    server_id = create_response.json()["id"]

    response = client.get(
        f"{settings.API_V1_STR}/agent/mcp-servers/{server_id}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "获取测试服务"
    assert result["transport_type"] == "stdio"

def test_update_mcp_server(
    client: TestClient,
    superuser_token_headers: dict[str, str]
) -> None:
    """测试更新 MCP Server"""
    create_data = {
        "name": "更新前名称",
        "transport_type": "sse",
        "url": "http://localhost:8080/sse",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/agent/mcp-servers",
        headers=superuser_token_headers,
        json=create_data,
    )
    server_id = create_response.json()["id"]

    update_data = {
        "name": "更新后名称",
        "is_active": False,
    }
    response = client.patch(
        f"{settings.API_V1_STR}/agent/mcp-servers/{server_id}",
        headers=superuser_token_headers,
        json=update_data,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "更新后名称"
    assert result["is_active"] is False

def test_delete_mcp_server(
    client: TestClient,
    superuser_token_headers: dict[str, str]
) -> None:
    """测试删除 MCP Server """
    create_data = {
        "name": "待删除服务", 
        "transport_type": "sse",
        "url": "http://localhost:8080/sse",
    }

    create_response = client.post(
        f"{settings.API_V1_STR}/agent/mcp-servers",
        headers=superuser_token_headers,
        json=create_data,
    )
    server_id = create_response.json()["id"]

    delete_response = client.delete(
        f"{settings.API_V1_STR}/agent/mcp-servers/{server_id}",
        headers=superuser_token_headers,
    )

    assert delete_response.status_code == 200

    get_response = client.get(
        f"{settings.API_V1_STR}/agent/mcp-servers/{server_id}",
        headers=superuser_token_headers,
    )

    assert get_response.status_code == 404


def test_connect_mcp_server(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """测试连接 MCP Server 并获取可用工具列表"""
    from tests.utils.utils import random_lower_string

    name = random_lower_string()

    res = client.post(
        f"{settings.API_V1_STR}/agent/mcp-servers",
        headers=superuser_token_headers,
        json={
            "name": name,
            "transport_type": "sse",
            "url": "http://localhost:8080/sse",
        },
    )
    assert res.status_code == 201
    server_id = res.json()["id"]

    with patch("app.api.routes.agent.MCPClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.list_tools = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "A test tool",
                    "inputSchema": {},
                }
            ]
        )
        MockClient.return_value = mock_instance

        res = client.post(
            f"{settings.API_V1_STR}/agent/mcp-servers/{server_id}/connect",
            headers=superuser_token_headers,
        )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "test_tool"
        mock_instance.connect_sse.assert_awaited_once()
        mock_instance.list_tools.assert_awaited_once()
        mock_instance.close.assert_awaited_once()




