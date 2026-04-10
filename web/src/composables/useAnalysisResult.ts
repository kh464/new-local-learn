import { ref } from 'vue'

import { formatTaskStateZh } from '../presentation/copy'
import { fetchTaskResult } from '../services/api'
import type { AnalysisResult, TaskResultResponse } from '../types/contracts'

export function useAnalysisResult(taskId: string, loader: typeof fetchTaskResult = fetchTaskResult) {
  const result = ref<AnalysisResult | null>(null)
  const pending = ref(false)
  const terminalError = ref('')
  const notFound = ref(false)

  async function load() {
    pending.value = true
    terminalError.value = ''
    notFound.value = false

    try {
      const payload = (await loader(taskId)) as TaskResultResponse

      if (payload.kind === 'success') {
        result.value = payload.data
        return
      }

      result.value = null

      if (payload.kind === 'failed') {
        terminalError.value = payload.error ?? `任务已结束，当前状态：${formatTaskStateZh(payload.state)}。`
      }
    } catch (cause) {
      result.value = null

      const error = cause instanceof Error ? cause.message : '结果加载失败。'
      if (error.includes('404')) {
        notFound.value = true
      } else {
        terminalError.value = error
      }
    } finally {
      pending.value = false
    }
  }

  return {
    result,
    pending,
    terminalError,
    notFound,
    load,
  }
}
