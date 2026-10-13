import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, renderHook, waitFor, act } from '@testing-library/react'
import { usePasswordPolicy } from './usePasswordPolicy'
import { firebaseAuth } from '../services/firebaseAuth'

vi.mock('../services/firebaseAuth', () => ({ firebaseAuth: { validatePassword: vi.fn() } }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('never accepts an earlier valid password after the input changes', async () => {
  let resolveFirst
  let resolveSecond
  firebaseAuth.validatePassword.mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))
  const hook = renderHook(({ password }) => usePasswordPolicy(password), { initialProps: { password: 'password' } })
  hook.rerender({ password: 'short' })
  await act(async () => { resolveFirst({ isValid: true }) })
  expect(hook.result.current.valid).toBe(false)
  await act(async () => { resolveSecond({ isValid: false }) })
  expect(hook.result.current.loading).toBe(false)
  expect(hook.result.current.valid).toBe(false)
})

it('fails closed on a policy outage and does not expose provider details', async () => {
  firebaseAuth.validatePassword.mockRejectedValue(new Error('private provider detail'))
  const hook = renderHook(() => usePasswordPolicy('password'))
  await waitFor(() => expect(hook.result.current.error).toBe(true))
  expect(hook.result.current.valid).toBe(false)
  expect(hook.result.current.status).toBeNull()
})
