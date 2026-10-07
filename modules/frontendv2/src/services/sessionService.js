import { authService } from './authService'
import { firebaseAuth } from './firebaseAuth'
import { useAuthStore } from '../stores/authStore'

export async function restoreSession() {
  const store = useAuthStore.getState()
  const firebase = store.authProvider === 'firebase'
  let token
  try {
    token = firebase ? await firebaseAuth.getToken() : localStorage.getItem('token')
  } catch (error) {
    if (['auth/user-token-expired', 'auth/invalid-user-token', 'auth/user-disabled', 'auth/user-not-found'].includes(error.code)) {
      await endSession()
      return
    }
    throw error
  }
  if (!token) { store.logout(); return }
  let response
  try { response = await authService.me() } catch (error) {
    const current = useAuthStore.getState()
    if (current.authProvider !== store.authProvider || current.user?.id !== store.user?.id) return
    if (error.status === 401) { store.logout(); return }
    throw error
  }
  // An in-flight restoration cannot undo an explicit logout/account change.
  const current = useAuthStore.getState()
  if (current.authProvider !== store.authProvider || current.user?.id !== store.user?.id) return
  if (!response.authenticated) { store.logout(); return }
  if (firebase) store.setFirebaseSession(response.user)
  else store.setSession(response.user, token)
}

export async function endSession() {
  // Clear domain access even if the external sign-out fails; caller shows failure.
  const firebase = useAuthStore.getState().authProvider === 'firebase'
  useAuthStore.getState().logout()
  if (firebase) await firebaseAuth.signOut()
}
