import { useEffect, useState } from 'react'
import { firebaseAuth } from '../services/firebaseAuth'

// Only the official SDK decides validity; discard stale async validations.
export function usePasswordPolicy(password, enabled = true) {
  const [result, setResult] = useState(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    firebaseAuth.validatePassword(password).then(status => {
      if (active) setResult({ password, attempt, status, error: false })
    }).catch(() => {
      if (active) setResult({ password, attempt, status: null, error: true })
    })
    return () => { active = false }
  }, [password, enabled, attempt])
  const current = enabled && result?.password === password && result.attempt === attempt
  return {
    status: current ? result.status : result?.status?.passwordPolicy
      ? { passwordPolicy: result.status.passwordPolicy } : null,
    loading: enabled && !current,
    error: Boolean(current && result.error),
    valid: Boolean(current && password && result.status?.isValid === true),
    retry: () => setAttempt(value => value + 1),
  }
}
