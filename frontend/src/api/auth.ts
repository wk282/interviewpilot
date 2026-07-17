import type { AuthResponse, LoginRequest, RegisterRequest, User } from '../types/auth'
import { apiClient } from './client'

export async function login(request: LoginRequest) {
  const response = await apiClient.post<AuthResponse>('/auth/login', request)
  return response.data
}

export async function register(request: RegisterRequest) {
  const response = await apiClient.post<AuthResponse>('/auth/register', request)
  return response.data
}

export async function getCurrentUser() {
  const response = await apiClient.get<User>('/users/me')
  return response.data
}
