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
})
