export interface User {
  id: string
  email: string
  display_name: string | null
  status: string
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  user: User
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest extends LoginRequest {
  display_name: string
  account_type: 'PERSONAL' | 'ORGANIZATION'
  organization_name?: string
}
