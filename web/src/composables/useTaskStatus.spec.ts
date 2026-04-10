import { afterEach, describe, expect, it, vi } from 'vitest'

import { useTaskStatus } from './useTaskStatus'

describe('useTaskStatus', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads the current task status', async () => {
    const fetchStatus = vi.fn().mockResolvedValue({
      task_id: 'task-1',
      state: 'running',
      stage: 'scan_tree',
      progress: 20,
      message: null,
      error: null,
      created_at: '2026-04-06T10:00:00Z',
      updated_at: '2026-04-06T10:01:00Z',
    })

    const model = useTaskStatus('task-1', fetchStatus)
    await model.refresh()

    expect(model.status.value?.stage).toBe('scan_tree')
  })

  it('swallows polling refresh errors and keeps polling active', async () => {
    vi.useFakeTimers()

    const fetchStatus = vi.fn().mockRejectedValue(new Error('network down'))
    const model = useTaskStatus('task-1', fetchStatus, 100)

    model.startPolling()
    await vi.advanceTimersByTimeAsync(100)

    expect(fetchStatus).toHaveBeenCalledTimes(1)

    model.stopPolling()
  })
})
