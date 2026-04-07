import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { createAnalysisTask } from '../services/api'
import { routes } from '../router'
import HomePage from './HomePage.vue'

vi.mock('../services/api', () => ({
  createAnalysisTask: vi.fn(),
}))

const createAnalysisTaskMock = vi.mocked(createAnalysisTask)

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes,
  })
}

describe('HomePage', () => {
  beforeEach(() => {
    createAnalysisTaskMock.mockReset()
  })

  it('submits the url and navigates to the task detail page', async () => {
    createAnalysisTaskMock.mockResolvedValue({
      task_id: 'task-123',
      status_url: '/status/task-123',
      result_url: '/result/task-123',
      stream_url: '/stream/task-123',
      task_token: 'task-token-123',
    })

    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(HomePage, {
      global: {
        plugins: [router],
      },
    })

    await wrapper.get('input').setValue('https://github.com/octocat/Hello-World')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(createAnalysisTaskMock).toHaveBeenCalledWith('https://github.com/octocat/Hello-World')
    expect(router.currentRoute.value.name).toBe('task-detail')
    expect(router.currentRoute.value.params.taskId).toBe('task-123')
  })

  it('shows an error when submission fails', async () => {
    createAnalysisTaskMock.mockRejectedValue(new Error('Request failed'))

    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(HomePage, {
      global: {
        plugins: [router],
      },
    })

    await wrapper.get('input').setValue('https://github.com/octocat/Hello-World')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Request failed')
  })
})
