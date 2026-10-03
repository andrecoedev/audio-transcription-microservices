import { create } from 'zustand'
import { persist } from 'zustand/middleware'

function sessionUser(user) {
  const name = user?.display_name || user?.username || 'Usuário'
  return {
    id: user?.id, name, email: user?.email || '',
    initials: name.slice(0, 2).toUpperCase(), avatar: null,
    roles: user?.roles || [], scopes: user?.scopes || [],
    registration_source: user?.registration_source || 'local',
    google_connected: Boolean(user?.google_connected),
  }
}

export const useAuthStore = create(
  persist(
    (set) => ({
      user: null,
      token: null,
      authProvider: 'local',
      authMode: 'strict',
      isAuthenticated: false,
      
      setAuthMode: (authMode) => set({ authMode }),
      setUser: (user) => set({ user, isAuthenticated: true }),
      setSession: (user, token) => {
        localStorage.setItem('token', token)
        set({
          token,
          authProvider: 'local',
          user: sessionUser(user),
          isAuthenticated: true,
        })
      },
      setFirebaseSession: (user) => {
        // Firebase owns token persistence/refresh. Never copy its credentials here.
        localStorage.removeItem('token')
        set({ token: null, authProvider: 'firebase', user: sessionUser(user), isAuthenticated: true })
      },
      logout: () => {
        localStorage.removeItem('token')
        set({ user: null, token: null, authProvider: 'local', isAuthenticated: false })
      },
      updateProfile: (updates) => set((state) => ({
        user: { ...state.user, ...updates }
      })),
    }),
    {
      name: 'auth-storage',
    }
  )
)
