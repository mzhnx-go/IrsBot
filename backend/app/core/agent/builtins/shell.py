"""Shell execution tool with safety restrictions."""

import asyncio
import shlex

from app.core.agent.tools import register_tool

# Commands allowed in shell_execute
ALLOWED_COMMANDS = {"echo", "cat", "ls", "pwd", "whoami", "date", "head", "tail", "wc", "grep", "find", "sort", "uniq", "du", "df", "uname", "env", "printenv"}
BLOCKED_PATTERNS = {"rm ", "rm -", "sudo", "mkfs", "dd ", ": >", ">/dev/sd", "chmod 777", "wget ", "curl ", "nc ", "ncat", "bash -c", "sh -c", "python -c", "node -e"}


@register_tool("shell_execute", "Execute a safe shell command", category="system")
async def shell_execute(command: str, timeout: float = 30.0) -> str:
    """Execute a shell command with safety restrictions.

    Args:
        command: The shell command to execute.
        timeout: Maximum execution time in seconds.
    """
    # Security checks
    cmd_lower = command.lower().strip()

    # Block dangerous patterns
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return f"Error: Command blocked for security: contains '{pattern}'"

    # Check for shell metacharacters that could bypass restrictions
    dangerous_chars = ["&&", "||", ";", "`", "$(", "$((", "${"]
    for char in dangerous_chars:
        if char in command:
            return f"Error: Shell metacharacter '{char}' not allowed"

    # Extract the base command
    parts = shlex.split(command)
    if not parts:
        return "Error: Empty command"

    base_cmd = parts[0].split("/")[-1]  # Get basename

    # Allow built-in commands and whitelisted commands
    if base_cmd in ALLOWED_COMMANDS or base_cmd in {"true", "false", "test", "yes", "no"}:
        pass  # Allowed
    elif base_cmd in {"python", "python3", "node", "npx"}:
        # Script execution allowed but limited
        if len(parts) > 2:
            return f"Error: Too many arguments for {base_cmd}"
    else:
        return f"Error: Command '{base_cmd}' not in allowed list"

    try:
        # create_subprocess_shell 没有 timeout 参数（任何平台都没有）；
        # 超时控制统一用 asyncio.wait_for 包住 communicate()。
        # 之前 Linux 分支传 timeout= 会抛 TypeError —— 宿主机 win32 分支掩盖了它。
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace").strip()
        if stderr:
            output += f"\n[stderr] {stderr.decode('utf-8', errors='replace').strip()}"
        return output or "(no output)"
    except asyncio.TimeoutError:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error executing command: {e}"
