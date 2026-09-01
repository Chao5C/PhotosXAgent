export interface User {
  id: string
  username: string
  email: string
  avatar?: string
  is_admin: boolean
  is_active: boolean
  created_at?: string
}

export interface LoginForm {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface Photo {
  id: string
  filename: string
  status: string
  user_description?: string
  user_long_description?: string
  parse_error?: string
  updated_at?: string
  caption?: string
  metadata?: {
    taken_at?: string
    lat?: number
    lng?: number
    camera?: string
    device_id?: string
  }
  vision?: {
    scene_type?: string
    people_count?: number
    objects?: string[]
    tags?: string[]
    caption?: string
    long_description?: string
  }
  geo?: {
    place_name?: string
    city?: string
    country?: string
    distance_from_home_km?: number
  }
  created_at?: string
}

export interface ParseQueueCounts {
  pending: number
  analyzing: number
  failed: number
  ready: number
}

export interface ParseQueueItem {
  id: string
  filename: string
  status: string
  caption?: string
  parse_error?: string
  updated_at?: string
}

export interface ParseQueue {
  counts: ParseQueueCounts
  active: number
  items: ParseQueueItem[]
}

export interface Album {
  id: string
  name: string
  kind: string
  count: number
  cover_id?: string
  photo_ids?: string[]
  photos?: Photo[]
}

export interface JourneyPoint {
  id: string
  filename?: string
  taken_at?: string
  lat: number
  lng: number
  place?: string
  city?: string
  caption?: string
  tags?: string[]
}

export interface Recommendation {
  id: string
  title: string
  body: string
  type: string
  priority?: string
  read?: boolean
  created_at?: string
  place?: string
  weather_brief?: string
}

export interface ChatPhotoCard {
  id: string
  filename?: string
  caption?: string
  brief_caption?: string
  long_description?: string
  tags?: string[]
  place?: string
  taken_at?: string
  status?: string
}

export interface ChatAlbumCard {
  id: string
  name?: string
  kind?: string
  count?: number
  photo_ids?: string[]
}

export interface ChatPoster {
  id?: string
  poster_id?: string
  title?: string
  place?: string
  image_url?: string
  image_data_url?: string
  created_at?: string
}

export interface ChatGuide {
  title?: string
  body?: string
  highlights?: string[]
  follow_up?: string
  place?: string
  weather_brief?: string
}

export interface ChatReminder {
  id?: string
  text?: string
  fire_at?: string
}

export interface ChatMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
  kind?: 'chat' | 'push' | 'reminder'
  intent?: string
  photos?: ChatPhotoCard[]
  albums?: ChatAlbumCard[]
  total?: number
  has_more?: boolean
  query_id?: string
  photo_ids?: string[]
  status?: string
  posterPreview?: string
  reminder?: ChatReminder
  poster?: ChatPoster
  guide?: ChatGuide
  created_at?: string
}

export interface ChatReply {
  reply?: string
  intent?: string
  kind?: string
  photos?: ChatPhotoCard[]
  albums?: ChatAlbumCard[]
  total?: number
  query_id?: string
  offset?: number
  has_more?: boolean
  reminder?: ChatReminder
  poster?: ChatPoster
  guide?: ChatGuide
}
