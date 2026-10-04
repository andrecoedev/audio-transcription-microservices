import { authService } from './authService'
import { firebaseAuth } from './firebaseAuth'
import { useAuthStore } from '../stores/authStore'

export async function restoreSession() {
  const store = useAuthStore.getState()
  const firebase = store.authProvider === 'firebase'
  const token = firebase ? await firebaseAuth.getToken() : localStorage.getItem('token')
  if (!token) { store.logout(); return }
  const response = await authService.me()
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
