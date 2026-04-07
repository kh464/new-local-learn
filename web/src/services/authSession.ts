const ACCESS_TOKEN_STORAGE_KEY = 'workbench.access_token'

function readEnvAccessToken(): string {
  const envToken = import.meta.env.VITE_ACCESS_TOKEN ?? ''
  if (envToken.trim().length > 0) {
    return envToken.trim()
  }

  const processToken = (
    globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }
  ).process?.env?.VITE_ACCESS_TOKEN
  return (processToken ?? '').trim()
}

function getStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

export function isAccessTokenManagedByEnv(): boolean {
  return readEnvAccessToken().length > 0
}

export function getAccessToken(): string {
  const envToken = readEnvAccessToken()
  if (envToken) {
    return envToken
  }

  const storage = getStorage()
  return storage?.getItem(ACCESS_TOKEN_STORAGE_KEY)?.trim() ?? ''
}

export function setAccessToken(token: string): void {
  if (isAccessTokenManagedByEnv()) {
    return
  }

  const storage = getStorage()
  if (storage === null) {
    return
  }

  const normalized = token.trim()
  if (!normalized) {
    storage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
    return
  }
  storage.setItem(ACCESS_TOKEN_STORAGE_KEY, normalized)
}

export function clearAccessToken(): void {
  if (isAccessTokenManagedByEnv()) {
    return
  }

  const storage = getStorage()
  storage?.removeItem(ACCESS_TOKEN_STORAGE_KEY)
}
