import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:2020'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Interceptor para adicionar token se necessário
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Interceptor para tratamento de erros
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url || ''
    if (error.response?.status === 401 && !url.startsWith('/guest/') && url !== '/auth/login') {
      useAuthStore.getState().logout()
    }
    const detail = error.response?.data?.detail
    const failure = new Error(typeof detail === 'string' ? detail : 'Não foi possível concluir a solicitação')
    failure.status = error.response?.status
    return Promise.reject(failure)
  }
)

export default api
