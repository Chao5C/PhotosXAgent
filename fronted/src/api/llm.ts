import { ApiClient } from './request'

export interface LLMProvider {
  id?: string
  name: string
  display_name: string
  description?: string
  website?: string
  default_base_url?: string
  test_model?: string
  api_key?: string
  is_active: boolean
  supported_features: string[]
  extra_config?: { has_api_key?: boolean; source?: string | null }
}

export interface CatalogModel {
  name: string
  display_name: string
}

export interface ModelCatalog {
  id?: string
  provider: string
  provider_name: string
  models: CatalogModel[]
  updated_at?: string
}

export interface LLMModel {
  id?: string
  provider: string
  model_name: string
  model_display_name?: string
  api_base?: string
  max_tokens: number
  temperature: number
  timeout: number
  enabled: boolean
  capability_level?: number
  suitable_roles?: string[]
  features?: string[]
  recommended_depths?: string[]
}

export interface EnabledLLMModel {
  id: string
  provider: string
  provider_display_name: string
  model_name: string
  model_display_name: string
  features: string[]
  suitable_roles: string[]
}

export const llmApi = {
  providers: () => ApiClient.get<LLMProvider[]>('/api/llm/providers'),
  addProvider: (data: Partial<LLMProvider>) => ApiClient.post('/api/llm/providers', data),
  updateProvider: (name: string, data: Partial<LLMProvider>) => ApiClient.put(`/api/llm/providers/${name}`, data),
  toggleProvider: (name: string, is_active: boolean) => ApiClient.post(`/api/llm/providers/${name}/toggle`, { is_active }),
  deleteProvider: (name: string) => ApiClient.delete(`/api/llm/providers/${name}`),
  testProvider: (name: string) => ApiClient.post(`/api/llm/providers/${name}/test`, {}),
  catalogs: () => ApiClient.get<ModelCatalog[]>('/api/llm/catalogs'),
  saveCatalog: (data: Partial<ModelCatalog>) => ApiClient.post('/api/llm/catalogs', data),
  deleteCatalog: (provider: string) => ApiClient.delete(`/api/llm/catalogs/${provider}`),
  models: () => ApiClient.get<LLMModel[]>('/api/llm/models'),
  saveModel: (data: Partial<LLMModel>) => ApiClient.post('/api/llm/models', data),
  toggleModel: (provider: string, model: string, enabled: boolean) =>
    ApiClient.post(`/api/llm/models/${provider}/${encodeURIComponent(model)}/toggle`, { enabled }),
  deleteModel: (provider: string, model: string) =>
    ApiClient.delete(`/api/llm/models/${provider}/${encodeURIComponent(model)}`),
  testModel: (provider: string, model: string) =>
    ApiClient.post(`/api/llm/models/${provider}/${encodeURIComponent(model)}/test`, {}),
  reload: () => ApiClient.post('/api/llm/reload', {}),
  enabledModels: () => ApiClient.get<EnabledLLMModel[]>('/api/llm/enabled-models')
}

export function parseModelId(id: string) {
  if (!id || !id.includes('::')) return { provider: '', model_name: '' }
  const idx = id.indexOf('::')
  return { provider: id.slice(0, idx), model_name: id.slice(idx + 2) }
}

export function toModelId(provider?: string, modelName?: string) {
  if (!provider || !modelName) return ''
  return `${provider}::${modelName}`
}
