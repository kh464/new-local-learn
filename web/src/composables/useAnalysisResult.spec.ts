import { describe, expect, it, vi } from 'vitest'

import { useAnalysisResult } from './useAnalysisResult'

describe('useAnalysisResult', () => {
  it('stores a successful result payload', async () => {
    const fetchResult = vi.fn().mockResolvedValue({
      kind: 'success',
      data: { github_url: 'https://github.com/octocat/Hello-World' },
    })

    const model = useAnalysisResult('task-1', fetchResult as never)
    await model.load()

    expect(model.result.value?.github_url).toContain('github.com')
  })

  it('formats failed terminal states in Chinese when the API omits an error message', async () => {
    const fetchResult = vi.fn().mockResolvedValue({
      kind: 'failed',
      task_id: 'task-1',
      state: 'cancelled',
    })

    const model = useAnalysisResult('task-1', fetchResult as never)
    await model.load()

    expect(model.result.value).toBeNull()
    expect(model.terminalError.value).toBe('任务已结束，当前状态：已取消。')
  })

  it('uses a Chinese fallback message for unexpected result loading failures', async () => {
    const fetchResult = vi.fn().mockRejectedValue('network down')

    const model = useAnalysisResult('task-1', fetchResult as never)
    await model.load()

    expect(model.notFound.value).toBe(false)
    expect(model.terminalError.value).toBe('结果加载失败。')
  })
})
