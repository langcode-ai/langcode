"""MCPManager: runtime management of MCP servers via langchain-mcp-adapters."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import mcp_list_servers

if TYPE_CHECKING:
    from langcode.core.config import Config


def _build_adapter_config(server_config: dict) -> dict:
    cfg = {k: v for k, v in server_config.items() if not k.startswith("_")}
    if "url" in cfg:
        transport = cfg.get("type", "http")
        if transport in ("streamable-http", "http"):
            transport = "http"
        result: dict = {"url": cfg["url"], "transport": transport}
        if cfg.get("headers"):
            result["headers"] = cfg["headers"]
        return result
    if "command" in cfg:
        return {
            "command": cfg["command"],
            "args": cfg.get("args", []),
            "env": cfg.get("env"),
            "transport": "stdio",
        }
    return {}


class MCPManager:
    """Manage multiple MCP servers via langchain-mcp-adapters."""

    def __init__(self):
        self._server_configs: dict = {}
        self._client: MultiServerMCPClient | None = None
        self._tools: list = []
        self.server_status: dict[str, str] = {}
        self._loading = False
        self._thread: threading.Thread | None = None

    def load_config(self, config: Config) -> None:
        for name, server_config in mcp_list_servers(config).items():
            adapter_cfg = _build_adapter_config(server_config)
            if adapter_cfg:
                self._server_configs[name] = adapter_cfg

    def add_plugin_servers(self, servers: dict[str, dict]) -> None:
        for name, server_config in servers.items():
            adapter_cfg = _build_adapter_config(server_config)
            if adapter_cfg and name not in self._server_configs:
                self._server_configs[name] = adapter_cfg

    @property
    def server_names(self) -> list[str]:
        return list(self._server_configs.keys())

    @property
    def server_configs(self) -> dict:
        return dict(self._server_configs)

    def start_all(self) -> None:
        if not self._server_configs:
            return
        try:
            self._client = MultiServerMCPClient(self._server_configs)
            self._tools = _run_async_quiet(self._client.get_tools())
            for name in self._server_configs:
                self.server_status[name] = "ok"
            return
        except Exception:
            pass

        self._tools = []
        for name, cfg in self._server_configs.items():
            try:
                client = MultiServerMCPClient({name: cfg})
                tools = _run_async_quiet(client.get_tools())
                self._tools.extend(tools)
                self.server_status[name] = "ok"
            except Exception:
                self.server_status[name] = "error"

    def start_in_background(self) -> None:
        if not self._server_configs:
            return
        import threading

        self._loading = True
        self._thread = threading.Thread(target=self._bg_start, daemon=True)
        self._thread.start()

    def _bg_start(self) -> None:
        try:
            self.start_all()
        finally:
            self._loading = False

    @property
    def is_loading(self) -> bool:
        return self._loading

    def stop_all(self) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._client = None
        self._tools = []

    def get_tools(self) -> list:
        return self._tools


def _run_async(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


def _run_async_quiet(coro):
    import io
    import os
    import sys

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    old_fd = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    try:
        return _run_async(coro)
    finally:
        os.dup2(old_fd, 2)
        os.close(old_fd)
        os.close(devnull)
        sys.stderr = old_stderr
