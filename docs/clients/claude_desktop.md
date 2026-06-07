# Claude Desktop 配置

将以下配置添加到 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "auto-hub": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/hainingyu/Code/auto_hub",
        "run",
        "auto-hub",
        "mcp"
      ]
    }
  }
}
```

验证：重启 Claude Desktop 后，应能看到 `list_projects`、`show_project`、`registry_status`、`llm_chat`、`llm_stats`、`reset_llm_stats`、`provider_chain` 等工具。
