import axios from 'axios'
import { useAuthStore } from '../stores/authStore'
import { firebaseAuth } from './firebaseAuth'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:2020'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Interceptor para adicionar token se necessário
api.interceptors.request.use(async (config) => {
  if (config.headers.Authorization) return config
  const firebase = useAuthStore.getState().authProvider === 'firebase'
  const token = firebase ? await firebaseAuth.getToken() : localStorage.getItem('token')
  if (firebase && !token) throw new Error('Sua sessão expirou. Entre novamente.')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Interceptor para tratamento de erros
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const url = error.config?.url || ''
    if (error.response?.status === 401 && !url.startsWith('/guest/') && !['/auth/login', '/auth/firebase', '/auth/firebase/link'].includes(url)) {
      const firebase = useAuthStore.getState().authProvider === 'firebase'
      useAuthStore.getState().logout()
      if (firebase) {
        try { await firebaseAuth.signOut() } catch {
          return Promise.reject(new Error('Não foi possível encerrar a sessão Google. Tente sair novamente.'))
        }
      }
    }
    const detail = error.response?.data?.detail
    const failure = new Error(typeof detail === 'string' ? detail : 'Não foi possível concluir a solicitação')
    failure.status = error.response?.status
    return Promise.reject(failure)
  }
)

export default api
