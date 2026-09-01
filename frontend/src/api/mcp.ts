import { ApiClient } from './request'

export interface McpServerConfig {
  id: string
  name?: string
  description?: string
  enabled?: boolean
  transport?: string
  command?: string
  args?: string[]
  cwd?: string
  env?: Record<string, string>
  test_tool?: string
  test_arguments?: Record<string, unknown>
}

export interface McpGatewayConfig {
  enabled?: boolean
  servers?: McpServerConfig[]
}

export interface McpTestResult {
  ok?: boolean
  message?: string
  tools?: string[]
  test_tool?: string
  preview?: string
  elapsed_ms?: number
}

export const mcpApi = {
  gateway: () => ApiClient.get<McpGatewayConfig>('/api/mcp/gateway'),
  saveGateway: (payload: McpGatewayConfig) => ApiClient.put<McpGatewayConfig>('/api/mcp/gateway', payload),
  test: (server_id: string) => ApiClient.post<McpTestResult>('/api/mcp/gateway/test', { server_id })
}
