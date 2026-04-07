import { getCurrentInstance, onBeforeUnmount, ref } from 'vue'

import { fetchTaskStatus } from '../services/api'
import type { TaskStatus } from '../types/contracts'

export function useTaskStatus(
  taskId: string,
  loader: typeof fetchTaskStatus = fetchTaskStatus,
  pollMs = 4000,
) {
  const status = ref<TaskStatus | null>(null)
  const loading = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  async function refresh() {
    loading.value = true
    try {
      status.value = await loader(taskId)
    } finally {
      loading.value = false
    }
  }

  function stopPolling() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function startPolling() {
    stopPolling()
    timer = setInterval(() => {
      void refresh()
    }, pollMs)
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(stopPolling)
  }

  return {
    status,
    loading,
    refresh,
    startPolling,
    stopPolling,
  }
}
