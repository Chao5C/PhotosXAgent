import { ApiClient } from './request'

export interface PosterItem {
  id: string
  title?: string
  place?: string
  body_preview?: string
  highlights?: string[]
  weather_brief?: string
  image_url?: string
  image_data_url?: string
  created_at?: string
}

export const posterApi = {
  list: () => ApiClient.get<{ items: PosterItem[]; total: number }>('/api/posters'),
  remove: (id: string) => ApiClient.delete(`/api/posters/${id}`)
}

export function posterFileUrl(id: string) {
  return `/api/posters/${id}/file`
}
