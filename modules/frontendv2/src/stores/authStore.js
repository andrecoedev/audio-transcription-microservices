import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      user: null,
      token: null,
      authMode: 'strict',
      isAuthenticated: false,
      
      setAuthMode: (authMode) => set({ authMode }),
      setUser: (user) => set({ user, isAuthenticated: true }),
      setSession: (user, token) => {
        localStorage.setItem('token', token)
        set({
          token,
          user: {
            id: user?.id,
            name: user?.username || 'Usuário',
            email: user?.email || '',
            initials: (user?.username || 'U').slice(0, 2).toUpperCase(),
            avatar: null,
            roles: user?.roles || [],
            scopes: user?.scopes || [],
          },
          isAuthenticated: true,
        })
      },
      logout: () => {
        localStorage.removeItem('token')
        set({ user: null, token: null, isAuthenticated: false })
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
