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
  const loadError = ref('')
  let timer: ReturnType<typeof setInterval> | null = null

  async function refresh() {
    loading.value = true
    loadError.value = ''
    try {
      status.value = await loader(taskId)
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : '任务状态加载失败。'
      throw error
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
      void refresh().catch(() => undefined)
    }, pollMs)
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(stopPolling)
  }

  return {
    status,
    loading,
    loadError,
    refresh,
    startPolling,
    stopPolling,
  }
}
