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

  it('renders the localized hero copy', async () => {
    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(HomePage, {
      global: {
        plugins: [router],
      },
    })

    expect(wrapper.get('.home-hero__eyebrow').text()).toBe('提交仓库以启动分析')
    expect(wrapper.get('.home-hero__title').text()).toBe('将 GitHub 项目转化为实时技术简报。')
    expect(wrapper.get('.home-hero__subtitle').text()).toBe(
      '粘贴仓库 URL，工作台会生成架构、流程以及实现细节的结构化概览。'
    )
  })

  it('trims url input before submission', async () => {
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

    const input = wrapper.get('input')
    await input.setValue('  https://github.com/octocat/Hello-World  ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(createAnalysisTaskMock).toHaveBeenCalledWith('https://github.com/octocat/Hello-World')
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

  it('shows fallback error when submission rejects with a non-error', async () => {
    createAnalysisTaskMock.mockRejectedValue('unexpected failure')

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

    expect(wrapper.text()).toContain('出现问题，请重试。')
  })
})
