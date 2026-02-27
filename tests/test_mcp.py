"""Tests for MCP: config loading, management, mcpServers key, HTTP transport."""

import json

from langcode.core.config import Config
from langcode.mcp import (
    MCPManager,
    _read_mcp_file,
    _write_mcp_file,
    mcp_add_server,
    mcp_get_server,
    mcp_list_servers,
    mcp_remove_server,
)

# ── config file reading ─────────────────────────────────────────────


class TestReadMcpFile:
    def test_servers_key(self, tmp_path):
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps({"servers": {"a": {"command": "x"}}}))
        assert "a" in _read_mcp_file(path)

    def test_mcpServers_key(self, tmp_path):
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps({"mcpServers": {"b": {"command": "y"}}}))
        assert "b" in _read_mcp_file(path)

    def test_mcpServers_takes_priority(self, tmp_path):
        """When both keys present, mcpServers wins."""
        path = tmp_path / "mcp.json"
        path.write_text(
            json.dumps(
                {
                    "mcpServers": {"new": {"command": "n"}},
                    "servers": {"old": {"command": "o"}},
                }
            )
        )
        result = _read_mcp_file(path)
        assert "new" in result
        assert "old" not in result

    def test_nonexistent_file(self, tmp_path):
        assert _read_mcp_file(tmp_path / "nope.json") == {}

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")
        assert _read_mcp_file(path) == {}


class TestWriteMcpFile:
    def test_writes_mcpServers_key(self, tmp_path):
        path = tmp_path / ".mcp.json"
        _write_mcp_file(path, {"gh": {"command": "npx"}})
        data = json.loads(path.read_text())
        assert "mcpServers" in data
        assert data["mcpServers"]["gh"]["command"] == "npx"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "mcp.json"
        _write_mcp_file(path, {"a": {}})
        assert path.exists()


# ── management functions ────────────────────────────────────────────


class TestMcpListServers:
    def test_lists_from_mcp_json(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"gh": {"command": "npx"}}}))
        config = Config(cwd=tmp_path)
        result = mcp_list_servers(config)
        assert "gh" in result
        assert "_source" in result["gh"]

    def test_lists_from_project_dir(self, tmp_path):
        pdir = tmp_path / ".langcode"
        pdir.mkdir()
        (pdir / "mcp.json").write_text(
            json.dumps({"mcpServers": {"sentry": {"type": "http", "url": "https://x"}}})
        )
        config = Config(cwd=tmp_path)
        result = mcp_list_servers(config)
        assert "sentry" in result

    def test_lists_from_both_project_dirs(self, tmp_path):
        lc = tmp_path / ".langcode"
        lc.mkdir()
        (lc / "mcp.json").write_text(json.dumps({"mcpServers": {"a": {"command": "x"}}}))
        cl = tmp_path / ".claude"
        cl.mkdir()
        (cl / "mcp.json").write_text(json.dumps({"mcpServers": {"b": {"command": "y"}}}))
        config = Config(cwd=tmp_path)
        result = mcp_list_servers(config)
        assert "a" in result
        assert "b" in result

    def test_project_mcp_json_overrides_project_dir(self, tmp_path):
        """cwd/.mcp.json takes priority over project_dir/mcp.json."""
        pdir = tmp_path / ".langcode"
        pdir.mkdir()
        (pdir / "mcp.json").write_text(json.dumps({"mcpServers": {"x": {"command": "old"}}}))
        (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"x": {"command": "new"}}}))
        config = Config(cwd=tmp_path)
        result = mcp_list_servers(config)
        assert result["x"]["command"] == "new"

    def test_empty_when_no_configs(self, tmp_path):
        config = Config(cwd=tmp_path)
        assert mcp_list_servers(config) == {}


class TestMcpAddServer:
    def test_add_to_project(self, tmp_path):
        config = Config(cwd=tmp_path)
        path = mcp_add_server(config, "gh", {"type": "http", "url": "https://x"}, "project")
        assert path == tmp_path / ".mcp.json"
        data = json.loads(path.read_text())
        assert data["mcpServers"]["gh"]["url"] == "https://x"

    def test_add_to_user(self, tmp_path):
        config = Config(cwd=tmp_path, global_dir=tmp_path / ".langcode")
        path = mcp_add_server(config, "mem", {"command": "memory-mcp"}, "user")
        assert path == tmp_path / ".langcode" / "mcp.json"
        data = json.loads(path.read_text())
        assert "mem" in data["mcpServers"]

    def test_add_preserves_existing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"existing": {"command": "x"}}})
        )
        config = Config(cwd=tmp_path)
        mcp_add_server(config, "new", {"command": "y"}, "project")
        data = json.loads((tmp_path / ".mcp.json").read_text())
        assert "existing" in data["mcpServers"]
        assert "new" in data["mcpServers"]


class TestMcpRemoveServer:
    def test_remove_existing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"gh": {"command": "x"}, "other": {"command": "y"}}})
        )
        config = Config(cwd=tmp_path)
        assert mcp_remove_server(config, "gh") is True
        data = json.loads((tmp_path / ".mcp.json").read_text())
        assert "gh" not in data["mcpServers"]
        assert "other" in data["mcpServers"]

    def test_remove_nonexistent(self, tmp_path):
        config = Config(cwd=tmp_path)
        assert mcp_remove_server(config, "nope") is False


class TestMcpGetServer:
    def test_get_existing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"gh": {"command": "npx", "args": ["-y"]}}})
        )
        config = Config(cwd=tmp_path)
        info = mcp_get_server(config, "gh")
        assert info is not None
        assert info["command"] == "npx"

    def test_get_nonexistent(self, tmp_path):
        config = Config(cwd=tmp_path)
        assert mcp_get_server(config, "nope") is None


# ── MCPManager loading ──────────────────────────────────────────────


class TestMCPConfigLoading:
    def test_load_stdio_from_servers_key(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "servers": {
                        "github": {
                            "command": "npx",
                            "args": ["-y", "@modelcontextprotocol/server-github"],
                            "env": {"GITHUB_TOKEN": "xxx"},
                        }
                    }
                }
            )
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert "github" in mgr._server_configs
        assert mgr._server_configs["github"]["command"] == "npx"
        assert mgr._server_configs["github"]["transport"] == "stdio"

    def test_load_stdio_from_mcpServers_key(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"gh": {"command": "npx", "args": ["-y", "pkg"]}}})
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert "gh" in mgr._server_configs
        assert mgr._server_configs["gh"]["transport"] == "stdio"

    def test_load_http_server(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {"mcpServers": {"sentry": {"type": "http", "url": "https://mcp.sentry.dev/mcp"}}}
            )
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert "sentry" in mgr._server_configs
        assert mgr._server_configs["sentry"]["transport"] == "http"
        assert mgr._server_configs["sentry"]["url"] == "https://mcp.sentry.dev/mcp"

    def test_load_sse_server(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {"mcpServers": {"asana": {"type": "sse", "url": "https://mcp.asana.com/sse"}}}
            )
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert mgr._server_configs["asana"]["transport"] == "sse"

    def test_load_from_project_dir(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        project_dir.mkdir()
        (project_dir / "mcp.json").write_text(
            json.dumps({"servers": {"sentry": {"command": "node", "args": ["sentry-server.js"]}}})
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert "sentry" in mgr._server_configs

    def test_merge_both_locations(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        project_dir.mkdir()
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"github": {"command": "gh"}}})
        )
        (project_dir / "mcp.json").write_text(
            json.dumps({"servers": {"slack": {"command": "slack-mcp"}}})
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert "github" in mgr._server_configs
        assert "slack" in mgr._server_configs

    def test_no_config_files(self, tmp_path):
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert mgr._server_configs == {}

    def test_get_tools_empty_without_start(self):
        mgr = MCPManager()
        assert mgr.get_tools() == []

    def test_stop_all_clears(self):
        mgr = MCPManager()
        mgr._tools = ["fake_tool"]
        mgr.stop_all()
        assert mgr.get_tools() == []
        assert mgr._client is None

    def test_server_names_property(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"a": {"command": "x"}, "b": {"command": "y"}}})
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert set(mgr.server_names) == {"a", "b"}

    def test_multiple_servers(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "jira": {"command": "jira-mcp", "args": []},
                        "github": {"command": "gh-mcp", "args": ["--token", "xxx"]},
                        "linear": {"command": "linear-mcp"},
                        "sentry": {"type": "http", "url": "https://mcp.sentry.dev/mcp"},
                        "postgres": {"command": "pg-mcp", "env": {"PG_URL": "postgres://..."}},
                    }
                }
            )
        )
        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)
        assert len(mgr._server_configs) == 5
        assert mgr._server_configs["sentry"]["transport"] == "http"
        assert mgr._server_configs["jira"]["transport"] == "stdio"


# ── /mcp command ────────────────────────────────────────────────────


class TestMcpCommand:
    def test_mcp_no_servers(self, tmp_path):
        config = Config(cwd=tmp_path)
        from langcode.commands import CommandHandler

        handler = CommandHandler(config)
        result = handler.handle("/mcp")
        assert "no mcp servers" in result.lower()

    def test_mcp_shows_configured_servers(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "github": {"type": "http", "url": "https://api.github.com/mcp"},
                        "local": {"command": "npx", "args": ["-y", "pkg"]},
                    }
                }
            )
        )
        config = Config(cwd=tmp_path)
        from langcode.commands import CommandHandler

        handler = CommandHandler(config)
        result = handler.handle("/mcp")
        assert "github" in result
        assert "local" in result
        assert "0/2 connected" in result
