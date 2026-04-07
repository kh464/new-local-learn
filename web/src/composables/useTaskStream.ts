import { getCurrentInstance, onBeforeUnmount, ref } from 'vue'

import { openTaskStream } from '../services/stream'
import type { TaskEventSource } from '../services/stream'
import type { TaskStreamEvent } from '../types/contracts'

type StreamSource = Pick<TaskEventSource, 'close' | 'onerror'>
export type TaskStreamOpener = (url: string, onEvent: (event: TaskStreamEvent) => void) => StreamSource

export function useTaskStream(url: string, opener: TaskStreamOpener = openTaskStream) {
  const events = ref<TaskStreamEvent[]>([])
  const connected = ref(false)
  let source: StreamSource | null = null

  function disconnect() {
    source?.close()
    source = null
    connected.value = false
  }

  function connect() {
    disconnect()
    source = opener(url, (event) => {
      events.value.push(event)
    })
    connected.value = true
    source.onerror = () => {
      connected.value = false
    }
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(disconnect)
  }

  return {
    events,
    connected,
    connect,
    disconnect,
  }
}
