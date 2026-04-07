import { afterEach, describe, expect, it, vi } from 'vitest'

import { clearTaskTokens, registerTaskToken } from './taskAccess'
import { openTaskStream } from './stream'
import type { TaskEventSource } from './stream'

describe('stream service', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    clearTaskTokens()
  })

  it('parses incoming SSE payloads', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn((name: string, handler: (event: MessageEvent) => void) => {
        listeners[name] = handler
      }),
      close: vi.fn(),
      onerror: null,
    }

    const eventFactory = vi.fn(() => fakeSource)
    const onEvent = vi.fn()

    openTaskStream('/api/v1/tasks/task-1/stream', onEvent, eventFactory)

    listeners.message!(new MessageEvent('message', { data: '{"state":"running","progress":35}' }))

    expect(onEvent).toHaveBeenCalledWith({ state: 'running', progress: 35 })
  })

  it('parses orchestrated SSE payloads with node metadata', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn((name: string, handler: (event: MessageEvent) => void) => {
        listeners[name] = handler
      }),
      close: vi.fn(),
      onerror: null,
    }

    const onEvent = vi.fn()

    openTaskStream('/api/v1/tasks/task-1/stream', onEvent, () => fakeSource)

    listeners.message!(
      new MessageEvent('message', {
        data: '{"stage":"analyze_frontend","progress":65,"node":"deploy_analysis"}',
      }),
    )

    expect(onEvent).toHaveBeenCalledWith({
      stage: 'analyze_frontend',
      progress: 65,
      node: 'deploy_analysis',
    })
  })

  it('ignores malformed SSE payloads', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn((name: string, handler: (event: MessageEvent) => void) => {
        listeners[name] = handler
      }),
      close: vi.fn(),
      onerror: null,
    }

    const onEvent = vi.fn()

    openTaskStream('/api/v1/tasks/task-1/stream', onEvent, () => fakeSource)

    listeners.message!(new MessageEvent('message', { data: 'not-json' }))

    expect(onEvent).not.toHaveBeenCalled()
  })

  it('ignores contract-invalid SSE payloads', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn((name: string, handler: (event: MessageEvent) => void) => {
        listeners[name] = handler
      }),
      close: vi.fn(),
      onerror: null,
    }

    const onEvent = vi.fn()

    openTaskStream('/api/v1/tasks/task-1/stream', onEvent, () => fakeSource)

    listeners.message!(new MessageEvent('message', { data: '{"stage":"typo","progress":"35"}' }))

    expect(onEvent).not.toHaveBeenCalled()
  })

  it('ignores empty SSE payload objects', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn((name: string, handler: (event: MessageEvent) => void) => {
        listeners[name] = handler
      }),
      close: vi.fn(),
      onerror: null,
    }

    const onEvent = vi.fn()

    openTaskStream('/api/v1/tasks/task-1/stream', onEvent, () => fakeSource)

    listeners.message!(new MessageEvent('message', { data: '{}' }))

    expect(onEvent).not.toHaveBeenCalled()
  })

  it('ignores unknown-only SSE payload objects', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn((name: string, handler: (event: MessageEvent) => void) => {
        listeners[name] = handler
      }),
      close: vi.fn(),
      onerror: null,
    }

    const onEvent = vi.fn()

    openTaskStream('/api/v1/tasks/task-1/stream', onEvent, () => fakeSource)

    listeners.message!(new MessageEvent('message', { data: '{"unexpected":"value"}' }))

    expect(onEvent).not.toHaveBeenCalled()
  })

  it('appends the configured API key to the SSE url', () => {
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn(),
      close: vi.fn(),
      onerror: null,
    }

    const eventFactory = vi.fn(() => fakeSource)
    vi.stubEnv('VITE_API_KEY', 'stream-secret')

    openTaskStream('/api/v1/tasks/task-1/stream', vi.fn(), eventFactory)

    expect(eventFactory).toHaveBeenCalledWith('/api/v1/tasks/task-1/stream?api_key=stream-secret')
  })

  it('appends the issued task token to the SSE url', () => {
    const fakeSource: TaskEventSource = {
      addEventListener: vi.fn(),
      close: vi.fn(),
      onerror: null,
    }

    const eventFactory = vi.fn(() => fakeSource)
    registerTaskToken('task-1', 'task-token-1')

    openTaskStream('/api/v1/tasks/task-1/stream', vi.fn(), eventFactory)

    expect(eventFactory).toHaveBeenCalledWith('/api/v1/tasks/task-1/stream?task_token=task-token-1')
  })
})
