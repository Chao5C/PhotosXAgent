from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.mcp_gateway_service import McpGatewayService

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpServerConfig(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    enabled: bool = True
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    cwd: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    test_tool: str = ""
    test_arguments: dict = Field(default_factory=dict)


class McpGatewayUpdate(BaseModel):
    enabled: bool | None = None
    servers: list[McpServerConfig] | None = None


class McpTestRequest(BaseModel):
    server_id: str


def _svc() -> McpGatewayService:
    return McpGatewayService(get_db())


@router.get("/gateway")
async def get_gateway(_user=Depends(get_current_user)):
    return ok(await _svc().get_config())


@router.put("/gateway")
async def update_gateway(payload: McpGatewayUpdate, _user=Depends(get_current_user)):
    current = await _svc().get_config()
    data = current.copy()
    if payload.enabled is not None:
        data["enabled"] = payload.enabled
    if payload.servers is not None:
        data["servers"] = [item.model_dump() for item in payload.servers]
    saved = await _svc().save_config(data)
    return ok(saved, "MCP 网关配置已保存")


@router.post("/gateway/test")
async def test_gateway(payload: McpTestRequest, _user=Depends(get_current_user)):
    if not payload.server_id.strip():
        raise HTTPException(status_code=400, detail="server_id 不能为空")
    result = await _svc().test_server(payload.server_id.strip())
    return ok(result)
