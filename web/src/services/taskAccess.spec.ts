import { afterEach, describe, expect, it, vi } from 'vitest'

function createStorageMock() {
  const store = new Map<string, string>()

  return {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value)
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key)
    }),
    clear: vi.fn(() => {
      store.clear()
    }),
  }
}

describe('taskAccess service', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('persists task tokens so a page reload can still read them', async () => {
    const storage = createStorageMock()
    vi.stubGlobal('localStorage', storage)

    const firstModule = await import('./taskAccess')
    firstModule.registerTaskToken('task-1', 'task-token-1')

    vi.resetModules()

    const reloadedModule = await import('./taskAccess')

    expect(reloadedModule.getTaskToken('task-1')).toBe('task-token-1')
    expect(storage.setItem).toHaveBeenCalled()
  })
})
