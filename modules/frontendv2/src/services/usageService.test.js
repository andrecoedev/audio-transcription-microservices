import { beforeEach, expect, it, vi } from 'vitest'

import api from './api'
import { usageService } from './usageService'

vi.mock('./api', () => ({ default: { get: vi.fn() } }))

beforeEach(() => vi.clearAllMocks())

it('reads the overview from the safe aggregate endpoint without user or filter parameters', async () => {
  const overview = { after: null, before: null, metrics: [] }
  api.get.mockResolvedValue({ data: overview })

  await expect(usageService.getOverview()).resolves.toEqual(overview)
  expect(api.get).toHaveBeenCalledTimes(1)
  expect(api.get).toHaveBeenCalledWith('/usage/overview')
})

it('reads the authenticated account plan from its own endpoint', async () => {
  const plan = { plan: 'free', quota: { limit_seconds: 0 } }
  api.get.mockResolvedValue({ data: plan })

  await expect(usageService.getPlan()).resolves.toEqual(plan)
  expect(api.get).toHaveBeenCalledTimes(1)
  expect(api.get).toHaveBeenCalledWith('/account/plan')
})
