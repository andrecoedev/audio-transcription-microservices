import axios from 'axios'
import { useAuthStore } from '../stores/authStore'
import { firebaseAuth } from './firebaseAuth'
import { requestErrorMessage } from './requestError'

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
  const sessionUserId = useAuthStore.getState().user?.id
  const context = firebase ? await firebaseAuth.getTokenContext() : null
  const token = firebase ? context?.token : localStorage.getItem('token')
  if (firebase && !token) throw new Error('Sua sessão expirou. Entre novamente.')
  if (firebase && (useAuthStore.getState().authProvider !== 'firebase'
      || useAuthStore.getState().user?.id !== sessionUserId)) {
    throw new Error('Sua sessão mudou. Tente novamente.')
  }
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
    if (firebase) {
      config._firebaseUserId = sessionUserId
      config._firebaseUid = context.uid
    }
  }
  return config
})

// Interceptor para tratamento de erros
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const url = error.config?.url || ''
    if (useAuthStore.getState().authProvider === 'firebase'
        && ['auth/user-token-expired', 'auth/invalid-user-token', 'auth/user-disabled', 'auth/user-not-found'].includes(error.code)) {
      useAuthStore.getState().logout()
      try { await firebaseAuth.signOut() } catch {
        return Promise.reject(new Error('Sua sessão não é mais válida. Tente sair novamente e entre para continuar.'))
      }
      return Promise.reject(new Error('Sua sessão não é mais válida. Entre novamente para continuar.'))
    }
    if (error.response?.status === 401 && !url.startsWith('/guest/') && !['/auth/login', '/auth/firebase', '/auth/firebase/link'].includes(url)) {
      const firebase = useAuthStore.getState().authProvider === 'firebase'
      if (firebase && !error.config?._firebaseUid) {
        return Promise.reject(new Error('Não foi possível autenticar esta solicitação.'))
      }
      // Only replay requests authenticated by this interceptor, once, and only
      // while the same internal account remains active. Never replay Guest proof.
      if (firebase && error.config?._firebaseUserId !== undefined
          && error.config._firebaseUserId === useAuthStore.getState().user?.id
          && !error.config._firebaseRetried) {
        error.config._firebaseRetried = true
        try {
          const context = await firebaseAuth.getTokenContext(true)
          const current = useAuthStore.getState()
          if (context?.token && context.uid === error.config._firebaseUid && current.authProvider === 'firebase'
              && current.user?.id === error.config._firebaseUserId && current.isAuthenticated) {
            error.config.headers.Authorization = `Bearer ${context.token}`
            return api.request(error.config)
          }
          if (context && context.uid !== error.config._firebaseUid) {
            return Promise.reject(new Error('A conta mudou. Recarregue a página antes de continuar.'))
          }
        } catch (refreshError) {
          // A network outage is not proof that authentication was revoked.
          if (!['auth/user-token-expired', 'auth/invalid-user-token', 'auth/user-disabled', 'auth/user-not-found'].includes(refreshError.code)) {
            return Promise.reject(new Error('Não foi possível renovar sua sessão. Verifique sua conexão e tente novamente.'))
          }
        }
      }
      // An old request must not terminate a newly authenticated account.
      if (error.config?._firebaseUserId !== undefined
          && (useAuthStore.getState().authProvider !== 'firebase'
              || error.config._firebaseUserId !== useAuthStore.getState().user?.id)) {
        return Promise.reject(new Error('Sua sessão mudou. Tente novamente.'))
      }
      useAuthStore.getState().logout()
      if (firebase) {
        try { await firebaseAuth.signOut() } catch {
          return Promise.reject(new Error('Não foi possível encerrar a sessão Google. Tente sair novamente.'))
        }
      }
    }
    const detail = error.response?.data?.detail
    const failure = new Error(requestErrorMessage(error.response?.status, detail))
    failure.status = error.response?.status
    return Promise.reject(failure)
  }
)

export default api
