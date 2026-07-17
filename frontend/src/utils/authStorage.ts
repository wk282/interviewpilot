import type { AuthResponse, User } from '../types/auth'

const TOKEN_KEY = 'interviewpilot_access_token'
const USER_KEY = 'interviewpilot_user'

function currentStorage() {
  return localStorage.getItem(TOKEN_KEY) ? localStorage : sessionStorage
}

export function saveAuth(auth: AuthResponse, remember = true) {
  clearAuth()
  const storage = remember ? localStorage : sessionStorage
  storage.setItem(TOKEN_KEY, auth.access_token)
  storage.setItem(USER_KEY, JSON.stringify(auth.user))
}

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY)
}

export function getStoredUser(): User | null {
  const value = currentStorage().getItem(USER_KEY)
  if (!value) return null

  try {
    return JSON.parse(value) as User
  } catch {
    clearAuth()
    return null
  }
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
}

export function isAuthenticated() {
  return Boolean(getAccessToken())
}
