import { describe, expect, it } from 'vitest'
import { firebaseWebEnv } from './firebaseWebEnv'

describe('public Firebase build configuration', () => {
  it('maps only the four Web aliases without publishing administrative/provider secrets', () => {
    expect(firebaseWebEnv({
      FIREBASE_API_KEY: 'synthetic-public-web-key',
      FIREBASE_AUTH_DOMAIN: 'synthetic-project.firebaseapp.com',
      FIREBASE_PROJECT_ID: 'synthetic-project',
      FIREBASE_APP_ID: '1:123456789:web:0000000000000000000000',
      FIREBASE_PRIVATE_KEY: 'synthetic-private-canary',
      GOOGLE_APPLICATION_CREDENTIALS: '/private/synthetic.json',
      GROQ_API_KEY: 'synthetic-provider-canary',
      SECRET_KEY: 'synthetic-jwt-canary',
      FIREBASE_AUTH_ENABLED: 'true',
    })).toEqual({
      VITE_FIREBASE_API_KEY: 'synthetic-public-web-key',
      VITE_FIREBASE_AUTH_DOMAIN: 'synthetic-project.firebaseapp.com',
      VITE_FIREBASE_PROJECT_ID: 'synthetic-project',
      VITE_FIREBASE_APP_ID: '1:123456789:web:0000000000000000000000',
    })
  })
  it('prefers non-empty VITE values and falls back when the canonical field is blank', () => {
    expect(firebaseWebEnv({ FIREBASE_API_KEY: 'alias', VITE_FIREBASE_API_KEY: ' explicit ' })
      .VITE_FIREBASE_API_KEY).toBe('explicit')
    expect(firebaseWebEnv({ FIREBASE_API_KEY: 'alias', VITE_FIREBASE_API_KEY: '' })
      .VITE_FIREBASE_API_KEY).toBe('alias')
  })
  it('honors frontend/shell overrides without inventing missing fields', () => {
    expect(firebaseWebEnv({ FIREBASE_PROJECT_ID: 'backend-project' },
      { FIREBASE_PROJECT_ID: 'frontend-project' }, { FIREBASE_PROJECT_ID: 'shell-project' }))
      .toEqual({ VITE_FIREBASE_API_KEY: '', VITE_FIREBASE_AUTH_DOMAIN: '',
        VITE_FIREBASE_PROJECT_ID: 'shell-project', VITE_FIREBASE_APP_ID: '' })
  })
})
