import axios from 'axios'
import { clearAuth, getAccessToken } from '../utils/authStorage'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 15000,
})

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && getAccessToken()) {
      clearAuth()
      window.location.assign('/login')
    }
    return Promise.reject(error)
  },
)
