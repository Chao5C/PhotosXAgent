import { ApiClient } from './request'

export interface StudioTopicBrief {
  id: string
  title: string
  status?: string
  updated_at?: string
  artifacts?: string[]
}

export interface StudioTopicDetail {
  id: string
  path: string
  meta: Record<string, any>
  body: string
  content_md: string
  manifest: Record<string, any>
  files: Record<string, boolean>
  content_hash: string
}

export const studioApi = {
  list: () => ApiClient.get<StudioTopicBrief[]>('/api/studio/topics'),
  create: (title: string, seed = '') => ApiClient.post<StudioTopicDetail>('/api/studio/topics', { title, seed }),
  get: (id: string) => ApiClient.get<StudioTopicDetail>(`/api/studio/topics/${id}`),
  updateContent: (id: string, content_md: string) =>
    ApiClient.put<StudioTopicDetail>(`/api/studio/topics/${id}/content`, { content_md }),
  remove: (id: string) => ApiClient.delete(`/api/studio/topics/${id}`),
  research: (id: string, query?: string) =>
    ApiClient.post<StudioTopicDetail>(`/api/studio/topics/${id}/research`, { query }),
  derive: (id: string, force = false) =>
    ApiClient.post<StudioTopicDetail>(`/api/studio/topics/${id}/derive`, { force }),
  produce: (id: string, force = false) =>
    ApiClient.post<StudioTopicDetail>(`/api/studio/topics/${id}/produce`, { force }),
  pipeline: (id: string, stages?: string[]) =>
    ApiClient.post<StudioTopicDetail>(`/api/studio/topics/${id}/pipeline`, {
      stages: stages || ['research', 'derive', 'produce']
    }),
  readFile: (id: string, path: string) =>
    ApiClient.get<{ path: string; content: string }>(`/api/studio/topics/${id}/file`, { path })
}
