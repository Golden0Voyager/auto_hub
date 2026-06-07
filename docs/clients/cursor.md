# Cursor 配置

在 Cursor 设置中添加 MCP 服务器：

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

配置路径：Cursor Settings → Features → MCP Servers → Add New。
