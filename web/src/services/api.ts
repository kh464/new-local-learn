import type {
  AuditEventQuery,
  AuditEventsPage,
  AnalysisTaskResponse,
  AnalysisResult,
  MetricsSnapshot,
  TaskChatExchange,
  TaskChatHistory,
  TaskListPage,
  TaskListQuery,
  TaskResultResponse,
  TaskStatus,
} from '../types/contracts'
import {
  isAuditEventsPage,
  isAnalysisResult,
  isAnalysisTaskResponse,
  isFailedTaskState,
  isMetricsSnapshot,
  isTaskChatExchange,
  isTaskChatHistory,
  isPendingTaskState,
  isTaskListPage,
  isTaskStatus,
} from '../types/contracts'
import { getAccessToken } from './authSession'
import { getTaskToken, registerTaskToken } from './taskAccess'

export type TaskArtifactKind = keyof Pick<AnalysisResult, 'markdown_path' | 'html_path' | 'pdf_path'>

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function createRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }

  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function getApiKey(): string {
  const envApiKey = import.meta.env.VITE_API_KEY ?? ''
  if (envApiKey.trim().length > 0) {
    return envApiKey.trim()
  }

  const processApiKey = (
    globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }
  ).process?.env?.VITE_API_KEY
  return (processApiKey ?? '').trim()
}

function getBearerToken(): string {
  return getAccessToken()
}

function getApiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? ''
}

export function buildTaskArtifactUrl(taskId: string, artifactKind: 'markdown' | 'html' | 'pdf'): string {
  const apiKey = getApiKey()
  const taskToken = getTaskToken(taskId)
  const query = new URLSearchParams()

  if (apiKey) {
    query.set('api_key', apiKey)
  } else if (taskToken) {
    query.set('task_token', taskToken)
  }

  const basePath = `${getApiBase()}/api/v1/tasks/${taskId}/artifacts/${artifactKind}`
  const suffix = query.size > 0 ? `?${query.toString()}` : ''
  return `${basePath}${suffix}`
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<{ status: number; payload: T }> {
  const apiKey = getApiKey()
  const taskToken = getTaskTokenFromPath(path)
  const accessToken = getBearerToken()
  const defaultHeaders = {
    'Content-Type': 'application/json',
    'X-Request-ID': createRequestId(),
    ...(apiKey ? { 'X-API-Key': apiKey } : {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...(taskToken ? { 'X-Task-Token': taskToken } : {}),
  }

  const response = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: {
      ...defaultHeaders,
      ...(init?.headers ?? {}),
    },
  })

  if (typeof response.text === 'function') {
    const body = await response.text()

    if (!response.ok && response.status !== 202) {
      if (body) {
        try {
          const payload = JSON.parse(body) as unknown
          if (isRecord(payload) && typeof payload.detail === 'string') {
            throw new Error(payload.detail)
          }
        } catch (error) {
          if (error instanceof Error && error.message !== 'Unexpected end of JSON input') {
            throw error
          }
        }
      }

      throw new Error(`Request failed with status ${response.status}`)
    }

    if (!body) {
      throw new Error(`Invalid JSON response with status ${response.status}`)
    }

    return {
      status: response.status,
      payload: JSON.parse(body) as T,
    }
  }

  if (!response.ok && response.status !== 202) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  if (typeof response.json === 'function') {
    return {
      status: response.status,
      payload: (await response.json()) as T,
    }
  }

  throw new Error(`Invalid JSON response with status ${response.status}`)
}

async function requestText(path: string, init?: RequestInit): Promise<{ status: number; body: string }> {
  const apiKey = getApiKey()
  const taskToken = getTaskTokenFromPath(path)
  const accessToken = getBearerToken()
  const response = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: {
      'X-Request-ID': createRequestId(),
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(taskToken ? { 'X-Task-Token': taskToken } : {}),
      ...(init?.headers ?? {}),
    },
  })

  const body = await response.text()
  if (!response.ok) {
    if (body) {
      try {
        const payload = JSON.parse(body) as unknown
        if (isRecord(payload) && typeof payload.detail === 'string') {
          throw new Error(payload.detail)
        }
      } catch (error) {
        if (error instanceof Error && error.message !== 'Unexpected end of JSON input') {
          throw error
        }
      }
    }

    throw new Error(`Request failed with status ${response.status}`)
  }

  return { status: response.status, body }
}

export async function createAnalysisTask(githubUrl: string): Promise<AnalysisTaskResponse> {
  const { payload } = await requestJson<unknown>('/api/v1/analyze', {
    method: 'POST',
    body: JSON.stringify({ github_url: githubUrl }),
  })

  if (!isAnalysisTaskResponse(payload)) {
    throw new Error('Invalid analysis task response.')
  }

  registerTaskToken(payload.task_id, payload.task_token)

  return payload
}

function getTaskTokenFromPath(path: string): string {
  const match = /^\/api\/v1\/tasks\/([^/]+)(?:$|\/)/.exec(path)
  if (!match) {
    return ''
  }
  return getTaskToken(match[1] ?? '')
}

export async function fetchTaskStatus(taskId: string): Promise<TaskStatus> {
  const { payload } = await requestJson<unknown>(`/api/v1/tasks/${taskId}`)

  if (!isTaskStatus(payload)) {
    throw new Error('Invalid task status payload.')
  }

  return payload
}

export async function cancelTask(taskId: string): Promise<TaskStatus> {
  const { payload } = await requestJson<unknown>(`/api/v1/tasks/${taskId}/cancel`, {
    method: 'POST',
  })

  if (!isTaskStatus(payload)) {
    throw new Error('Invalid task status payload.')
  }

  return payload
}

export async function stopTask(taskId: string): Promise<TaskStatus> {
  const { payload } = await requestJson<unknown>(`/api/v1/tasks/${taskId}/stop`, {
    method: 'POST',
  })

  if (!isTaskStatus(payload)) {
    throw new Error('Invalid task status payload.')
  }

  return payload
}

export async function fetchTaskChatMessages(taskId: string): Promise<TaskChatHistory> {
  const { payload } = await requestJson<unknown>(`/api/v1/tasks/${taskId}/chat/messages`)

  if (!isTaskChatHistory(payload)) {
    throw new Error('Invalid task chat payload.')
  }

  return payload
}

export async function submitTaskQuestion(taskId: string, question: string): Promise<TaskChatExchange> {
  const { payload } = await requestJson<unknown>(`/api/v1/tasks/${taskId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ question }),
  })

  if (!isTaskChatExchange(payload)) {
    throw new Error('Invalid task chat payload.')
  }

  return payload
}

export async function fetchTaskList(query: TaskListQuery = {}): Promise<TaskListPage> {
  const params = new URLSearchParams()
  const entries: Array<[keyof TaskListQuery, string | number | undefined]> = [
    ['limit', query.limit ?? 8],
    ['offset', query.offset ?? 0],
    ['state', query.state],
  ]

  for (const [key, value] of entries) {
    if (value === undefined) {
      continue
    }

    const serialized = String(value).trim()
    if (!serialized) {
      continue
    }
    params.set(key, serialized)
  }

  const { payload } = await requestJson<unknown>(`/api/v1/tasks?${params.toString()}`)

  if (!isTaskListPage(payload)) {
    throw new Error('Invalid task list payload.')
  }

  return payload
}

export async function retryTask(taskId: string): Promise<AnalysisTaskResponse> {
  const { payload } = await requestJson<unknown>(`/api/v1/tasks/${taskId}/retry`, {
    method: 'POST',
  })

  if (!isAnalysisTaskResponse(payload)) {
    throw new Error('Invalid analysis task response.')
  }

  registerTaskToken(payload.task_id, payload.task_token)

  return payload
}

export async function downloadTaskArtifact(taskId: string, artifactKind: 'markdown' | 'html' | 'pdf'): Promise<void> {
  const apiKey = getApiKey()
  const taskToken = getTaskToken(taskId)
  const accessToken = getBearerToken()
  const response = await fetch(`${getApiBase()}/api/v1/tasks/${taskId}/artifacts/${artifactKind}`, {
    headers: {
      'X-Request-ID': createRequestId(),
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(taskToken ? { 'X-Task-Token': taskToken } : {}),
    },
  })

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  const blob = typeof response.blob === 'function'
    ? await response.blob()
    : new Blob([await response.text()], { type: response.headers.get('Content-Type') ?? 'application/octet-stream' })

  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = `result.${artifactKind === 'markdown' ? 'md' : artifactKind}`
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(href)
}

export async function fetchTaskResult(taskId: string): Promise<TaskResultResponse> {
  const { status, payload } = await requestJson<unknown>(`/api/v1/tasks/${taskId}/result`)

  if (!isRecord(payload)) {
    throw new Error('Invalid result payload.')
  }

  if (status === 202) {
    if (typeof payload.task_id !== 'string' || !isPendingTaskState(payload.state)) {
      throw new Error('Invalid result payload.')
    }

    return {
      kind: 'pending',
      task_id: payload.task_id,
      state: payload.state,
    }
  }

  if (isAnalysisResult(payload)) {
    return {
      kind: 'success',
      data: payload,
    }
  }

  if (
    typeof payload.task_id !== 'string' ||
    !isFailedTaskState(payload.state) ||
    (payload.error !== undefined && typeof payload.error !== 'string')
  ) {
    throw new Error('Invalid result payload.')
  }

  return {
    kind: 'failed',
    task_id: payload.task_id,
    state: payload.state,
    error: payload.error as string | undefined,
  }
}

export async function fetchAuditEvents(query: AuditEventQuery = {}): Promise<AuditEventsPage> {
  const params = new URLSearchParams()
  const entries: Array<[keyof AuditEventQuery, string | number | undefined]> = [
    ['limit', query.limit ?? 25],
    ['offset', query.offset ?? 0],
    ['action', query.action],
    ['outcome', query.outcome],
    ['task_id', query.task_id],
    ['request_id', query.request_id],
    ['subject', query.subject],
    ['method', query.method],
    ['path', query.path],
  ]

  for (const [key, value] of entries) {
    if (value === undefined) {
      continue
    }

    const serialized = String(value).trim()
    if (!serialized) {
      continue
    }
    params.set(key, serialized)
  }

  const { payload } = await requestJson<unknown>(`/api/v1/audit/events?${params.toString()}`)

  if (!isAuditEventsPage(payload)) {
    throw new Error('Invalid audit events payload.')
  }

  return payload
}

export async function fetchMetricsSnapshot(): Promise<MetricsSnapshot> {
  const { body } = await requestText('/metrics')
  const snapshot: MetricsSnapshot = {}

  for (const line of body.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) {
      continue
    }

    const [name, rawValue] = trimmed.split(/\s+/, 2)
    const value = Number(rawValue)
    if (!name || !Number.isFinite(value)) {
      throw new Error('Invalid metrics payload.')
    }
    snapshot[name] = value
  }

  if (!isMetricsSnapshot(snapshot)) {
    throw new Error('Invalid metrics payload.')
  }

  return snapshot
}
