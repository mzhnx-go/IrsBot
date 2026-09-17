"""Tests for MCP security validation."""

import pytest

from app.core.mcp.security import MCPSecurity


class TestMCPSecurity:
    @pytest.fixture
    def security(self):
        return MCPSecurity()

    def test_allowed_python_command(self, security):
        assert security.validate_command("python", ["server.py"]) is True

    def test_allowed_node_command(self, security):
        assert security.validate_command("node", ["app.js"]) is True

    def test_allowed_uv_command(self, security):
        assert security.validate_command("uv", ["run", "script.py"]) is True

    def test_blocked_sh_command(self, security):
        assert security.validate_command("sh", ["-c", "ls"]) is False

    def test_blocked_bash_command(self, security):
        assert security.validate_command("bash", ["-c", "ls"]) is False

    def test_blocked_rm_command(self, security):
        assert security.validate_command("rm", ["-rf", "/tmp"]) is False

    def test_blocked_sudo_command(self, security):
        assert security.validate_command("sudo", ["apt", "update"]) is False

    def test_blocked_inline_python(self, security):
        assert security.validate_command("python", ["-c", "print(1)"]) is False

    def test_blocked_inline_node(self, security):
        assert security.validate_command("node", ["-e", "console.log(1)"]) is False

    def test_blocked_eval(self, security):
        assert security.validate_command("python", ["-c", "eval('1+1')"]) is False

    def test_blocked_dangerous_metacharacters(self, security):
        assert security.validate_command("python", ["script.py; rm -rf /"]) is False

    def test_disallowed_command_not_in_whitelist(self, security):
        assert security.validate_command("nc", ["host", "port"]) is False

    def test_validate_arguments_safe(self, security):
        assert security.validate_arguments({"query": "hello world"}) is True

    def test_validate_arguments_injection(self, security):
        assert security.validate_arguments({"query": "x; rm -rf /"}) is False

    def test_validate_arguments_pipe(self, security):
        assert security.validate_arguments({"cmd": "ls | cat"}) is False
