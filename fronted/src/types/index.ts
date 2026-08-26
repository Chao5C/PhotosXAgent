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
  metadata?: {
    taken_at?: string
    lat?: number
    lng?: number
    camera?: string
  }
  vision?: {
    scene_type?: string
    people_count?: number
    mood?: string
    objects?: string[]
    tags?: string[]
    caption?: string
  }
  geo?: {
    place_name?: string
    city?: string
    country?: string
    distance_from_home_km?: number
  }
  created_at?: string
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

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  created_at?: string
}
