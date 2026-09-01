"""PhotosXAgent MCP — 联网搜索服务。"""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from photosx.studio.research import web_search

server = MCPServer("photosx-search")


@server.tool(description="联网检索资料，返回 JSON 列表 [{title,url,snippet}]")
async def web_search_tool(query: str, limit: int = 6) -> str:
    items = await web_search(query, limit=max(1, min(int(limit or 6), 10)))
    return json.dumps(items, ensure_ascii=False)


if __name__ == "__main__":
    server.run(transport="stdio")
