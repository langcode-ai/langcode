"""MCP: server management and runtime client."""

from .config import (
    mcp_add_server,
    mcp_config_path,
    mcp_get_server,
    mcp_list_servers,
    mcp_remove_server,
    read_mcp_file,
    write_mcp_file,
)
from .manager import MCPManager

# Compat aliases used by tests
_read_mcp_file = read_mcp_file
_write_mcp_file = write_mcp_file

__all__ = [
    "MCPManager",
    "mcp_add_server",
    "mcp_config_path",
    "mcp_get_server",
    "mcp_list_servers",
    "mcp_remove_server",
    "read_mcp_file",
    "write_mcp_file",
]
