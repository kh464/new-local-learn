const TASK_TOKEN_STORAGE_KEY = 'workbench.task_tokens'
const taskTokens = new Map<string, string>()

function getStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

function readStoredTaskTokens(): Record<string, string> {
  const storage = getStorage()
  const raw = storage?.getItem(TASK_TOKEN_STORAGE_KEY)
  if (!raw) {
    return {}
  }

  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') {
      return {}
    }

    return Object.fromEntries(
      Object.entries(parsed).filter(
        ([taskId, token]) => typeof taskId === 'string' && typeof token === 'string' && token.trim().length > 0,
      ),
    )
  } catch {
    return {}
  }
}

function persistTaskTokens(): void {
  const storage = getStorage()
  if (storage === null) {
    return
  }

  if (taskTokens.size === 0) {
    storage.removeItem(TASK_TOKEN_STORAGE_KEY)
    return
  }

  storage.setItem(TASK_TOKEN_STORAGE_KEY, JSON.stringify(Object.fromEntries(taskTokens)))
}

function hydrateTaskTokens(): void {
  if (taskTokens.size > 0) {
    return
  }

  const storedTokens = readStoredTaskTokens()
  for (const [taskId, token] of Object.entries(storedTokens)) {
    taskTokens.set(taskId, token)
  }
}

export function registerTaskToken(taskId: string, taskToken: string) {
  const normalizedTaskId = taskId.trim()
  const normalizedToken = taskToken.trim()
  if (!normalizedTaskId || !normalizedToken) {
    return
  }

  hydrateTaskTokens()
  taskTokens.set(normalizedTaskId, normalizedToken)
  persistTaskTokens()
}

export function getTaskToken(taskId: string): string {
  hydrateTaskTokens()
  return taskTokens.get(taskId) ?? ''
}

export function clearTaskTokens() {
  taskTokens.clear()
  persistTaskTokens()
}
