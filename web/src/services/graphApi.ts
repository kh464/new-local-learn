import type { TaskGraphPayload, TaskGraphView } from '../types/contracts'
import { isTaskGraphPayload } from '../types/contracts'
import { getAccessToken } from './authSession'
import { getTaskToken } from './taskAccess'

function createRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }

  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function getApiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? ''
}

export async function fetchTaskGraph(
  taskId: string,
  options: { view?: TaskGraphView; symbolId?: string; path?: string } = {},
): Promise<TaskGraphPayload> {
  const params = new URLSearchParams()
  params.set('view', options.view ?? 'repository')
  if (options.symbolId) {
    params.set('symbol_id', options.symbolId)
  }
  if (options.path) {
    params.set('path', options.path)
  }

  const taskToken = getTaskToken(taskId)
  const accessToken = getAccessToken()
  const response = await fetch(`${getApiBase()}/api/v1/tasks/${taskId}/graph?${params.toString()}`, {
    headers: {
      'X-Request-ID': createRequestId(),
      ...(taskToken ? { 'X-Task-Token': taskToken } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  })

  const payload = (await response.json()) as unknown
  if (!response.ok) {
    if (typeof payload === 'object' && payload !== null && typeof (payload as { detail?: unknown }).detail === 'string') {
      throw new Error((payload as { detail: string }).detail)
    }
    throw new Error(`Request failed with status ${response.status}`)
  }

  if (!isTaskGraphPayload(payload)) {
    throw new Error('Invalid task graph payload.')
  }

  return payload
}
