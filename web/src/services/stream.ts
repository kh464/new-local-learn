import type { TaskStreamEvent } from '../types/contracts'
import { isTaskStreamEvent } from '../types/contracts'
import { getTaskToken } from './taskAccess'

export interface TaskEventSource {
  addEventListener(type: 'message', listener: (event: MessageEvent) => void): void
  close(): void
  onerror: ((event: Event) => void) | null
}

export type EventSourceFactory = (url: string) => TaskEventSource

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

function buildStreamUrl(url: string): string {
  const taskToken = getTaskTokenFromUrl(url)
  if (taskToken) {
    const separator = url.includes('?') ? '&' : '?'
    return `${url}${separator}task_token=${encodeURIComponent(taskToken)}`
  }

  const apiKey = getApiKey()
  if (!apiKey) {
    return url
  }

  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}api_key=${encodeURIComponent(apiKey)}`
}

function getTaskTokenFromUrl(url: string): string {
  const match = /\/tasks\/([^/?]+)/.exec(url)
  if (!match) {
    return ''
  }
  return getTaskToken(match[1] ?? '')
}

export function openTaskStream(
  url: string,
  onEvent: (event: TaskStreamEvent) => void,
  factory: EventSourceFactory = (value) => new EventSource(value),
) {
  const source = factory(buildStreamUrl(url))

  source.addEventListener('message', (event: MessageEvent) => {
    try {
      const payload = JSON.parse(event.data) as unknown
      if (isTaskStreamEvent(payload)) {
        onEvent(payload)
      }
    } catch {
      return
    }
  })

  return source
}
