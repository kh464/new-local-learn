import { describe, expect, it, vi } from 'vitest'

import type { TaskStreamEvent } from '../types/contracts'
import { useTaskStream } from './useTaskStream'

describe('useTaskStream', () => {
  it('appends incoming stream events', () => {
    let emit: ((event: TaskStreamEvent) => void) | undefined

    const open = vi.fn((_url: string, onEvent: (event: TaskStreamEvent) => void) => {
      emit = onEvent
      return { close: vi.fn(), onerror: null }
    })

    const model = useTaskStream('/api/v1/tasks/task-1/stream', open)
    model.connect()
    emit?.({ stage: 'detect_stack' })

    expect(model.events.value).toHaveLength(1)
    expect(model.events.value[0].stage).toBe('detect_stack')
  })
})
