"""MCP security — validates commands and arguments for stdio transport."""

import re


class MCPSecurity:
    """Security checks for MCP stdio transport."""

    ALLOWED_COMMANDS = frozenset({
        "python", "python3", "node", "npm", "pnpm", "yarn", "bun", "deno",
        "uv", "uvx", "npx", "git", "curl", "wget",
    })

    BLOCKED_COMMANDS = frozenset({
        "bash", "sh", "zsh", "csh", "ksh", "fish",
        "sudo", "su", "chmod", "chown", "dd", "mkfs",
        "fdisk", "rm", "rmdir", "kill", "pkill",
    })

    # Patterns that indicate inline code execution
    INLINE_CODE_PATTERNS = [
        re.compile(r"python\s+-c", re.IGNORECASE),
        re.compile(r"node\s+-e", re.IGNORECASE),
        re.compile(r"ruby\s+-e", re.IGNORECASE),
        re.compile(r"perl\s+-e", re.IGNORECASE),
        re.compile(r"eval\s*\(", re.IGNORECASE),
        re.compile(r"exec\s*\(", re.IGNORECASE),
    ]

    # Shell metacharacters that could enable command injection
    DANGEROUS_METACHARACTERS = re.compile(r"[;&|`$(){}<>!]")

    def validate_command(self, command: str, args: list[str] | None = None) -> bool:
        """Validate a command for security compliance.

        Returns True if the command passes all security checks.
        """
        cmd_base = command.split("/")[-1]  # Get basename

        # Check blacklist
        if cmd_base in self.BLOCKED_COMMANDS:
            return False

        # Check whitelist (commands must be in allowed list)
        if cmd_base not in self.ALLOWED_COMMANDS:
            return False

        # Check args for inline code patterns
        all_args = " ".join(args or [])
        for pattern in self.INLINE_CODE_PATTERNS:
            if pattern.search(all_args):
                return False
        # Also check args directly for known dangerous flags
        if args:
            for arg in args:
                stripped = arg.strip().strip("'\"")
                if stripped in ("-c", "-e", "--eval", "-C"):
                    return False

        # Check for dangerous shell metacharacters in args
        if self.DANGEROUS_METACHARACTERS.search(all_args):
            return False

        return True

    def validate_arguments(self, arguments: dict) -> bool:
        """Validate tool arguments for injection attempts."""
        for key, value in arguments.items():
            if isinstance(value, str) and self.DANGEROUS_METACHARACTERS.search(value):
                return False
        return True
