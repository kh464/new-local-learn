import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AnalysisResult, TaskStatus, TaskStreamEvent } from '../types/contracts'
import { cancelTask, retryTask } from '../services/api'
import TaskDetailPage from './TaskDetailPage.vue'

const routerPushMock = vi.hoisted(() => vi.fn())
const cancelTaskMock = vi.hoisted(() => vi.fn())
const retryTaskMock = vi.hoisted(() => vi.fn())

const taskStatusMock = vi.hoisted(() => ({
  status: {
    value: {
      task_id: 'task-1',
      state: 'succeeded',
      stage: 'finalize',
      progress: 100,
      message: null,
      error: null,
      created_at: '2026-04-06T10:00:00Z',
      updated_at: '2026-04-06T10:10:00Z',
    } as TaskStatus,
  },
  loading: { value: false },
  refresh: vi.fn().mockResolvedValue(undefined),
  startPolling: vi.fn(),
  stopPolling: vi.fn(),
}))

const taskStreamMock = vi.hoisted(() => ({
  events: { value: [{ stage: 'scan_tree', progress: 20 }] as TaskStreamEvent[] },
  connected: { value: true },
  connect: vi.fn(),
  disconnect: vi.fn(),
}))

const analysisResultMock = vi.hoisted(() => ({
  result: {
    value: {
      github_url: 'https://github.com/octocat/Hello-World',
      repo_path: 'artifacts/task-1/repo',
      markdown_path: 'artifacts/task-1/result.md',
      html_path: 'artifacts/task-1/result.html',
      pdf_path: 'artifacts/task-1/result.pdf',
      repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
      detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
      backend_summary: { routes: [] },
      frontend_summary: {
        framework: 'react',
        bundler: 'vite',
        state_manager: 'zustand',
        routing: [],
        api_calls: [],
        state_units: [],
        components: [{ name: 'App', source_file: 'web/App.tsx', imports: [] }],
      },
      deploy_summary: {
        services: [{ name: 'redis', source_file: 'docker-compose.yml', ports: ['6379:6379'] }],
        environment_files: ['.env.example'],
        manifests: [],
      },
      logic_summary: { flows: [] },
      tutorial_summary: {
        mental_model: 'Simple flow',
        request_lifecycle: [],
        run_steps: [],
        pitfalls: [],
        next_steps: [],
        self_check_questions: [],
        faq_entries: [],
        code_walkthroughs: [],
      },
      critique_summary: {
        coverage_notes: ['Observed 1 deploy services.'],
        inferred_sections: [],
        missing_areas: ['No Kubernetes manifests detected.'],
      },
      mermaid_sections: { system: 'graph TD\nA-->B' },
    } as AnalysisResult | null,
  },
  pending: { value: false },
  terminalError: { value: '' },
  notFound: { value: false },
  load: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../composables/useTaskStatus', () => ({
  useTaskStatus: () => taskStatusMock,
}))

vi.mock('../composables/useTaskStream', () => ({
  useTaskStream: () => taskStreamMock,
}))

vi.mock('../composables/useAnalysisResult', () => ({
  useAnalysisResult: () => analysisResultMock,
}))

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    cancelTask: cancelTaskMock,
    retryTask: retryTaskMock,
  }
})

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return {
    ...actual,
    useRouter: () => ({
      push: routerPushMock,
    }),
  }
})

const cancelTaskServiceMock = vi.mocked(cancelTask)
const retryTaskServiceMock = vi.mocked(retryTask)

describe('TaskDetailPage', () => {
  beforeEach(() => {
    cancelTaskServiceMock.mockReset()
    retryTaskServiceMock.mockReset()
    routerPushMock.mockReset()
    taskStatusMock.status.value = {
      task_id: 'task-1',
      state: 'succeeded',
      stage: 'finalize',
      progress: 100,
      message: null,
      error: null,
      created_at: '2026-04-06T10:00:00Z',
      updated_at: '2026-04-06T10:10:00Z',
    } satisfies TaskStatus
    taskStreamMock.events.value = [{ stage: 'scan_tree', progress: 20 }] satisfies TaskStreamEvent[]
    analysisResultMock.result.value = {
      github_url: 'https://github.com/octocat/Hello-World',
      repo_path: 'artifacts/task-1/repo',
      markdown_path: 'artifacts/task-1/result.md',
      html_path: 'artifacts/task-1/result.html',
      pdf_path: 'artifacts/task-1/result.pdf',
      repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
      detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
      backend_summary: { routes: [] },
      frontend_summary: {
        framework: 'react',
        bundler: 'vite',
        state_manager: 'zustand',
        routing: [],
        api_calls: [],
        state_units: [],
        components: [{ name: 'App', source_file: 'web/App.tsx', imports: [] }],
      },
      deploy_summary: {
        services: [{ name: 'redis', source_file: 'docker-compose.yml', ports: ['6379:6379'] }],
        environment_files: ['.env.example'],
        manifests: [],
      },
      logic_summary: { flows: [] },
      tutorial_summary: {
        mental_model: 'Simple flow',
        request_lifecycle: [],
        run_steps: [],
        pitfalls: [],
        next_steps: [],
        self_check_questions: [],
        faq_entries: [],
        code_walkthroughs: [],
      },
      critique_summary: {
        coverage_notes: ['Observed 1 deploy services.'],
        inferred_sections: [],
        missing_areas: ['No Kubernetes manifests detected.'],
      },
      mermaid_sections: { system: 'graph TD\nA-->B' },
    } satisfies AnalysisResult
    analysisResultMock.pending.value = false
    analysisResultMock.terminalError.value = ''
    analysisResultMock.notFound.value = false
  })

  it('renders status, timeline, and result sections', async () => {
    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-1',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('task-1')
    expect(wrapper.text()).toContain('scan_tree')
    expect(wrapper.text()).toContain('Hello-World')
  })

  it('renders a terminal failure message', async () => {
    taskStatusMock.status.value = {
      task_id: 'task-2',
      state: 'failed',
      stage: 'finalize',
      progress: 100,
      message: null,
      error: null,
      created_at: '2026-04-06T10:00:00Z',
      updated_at: '2026-04-06T10:10:00Z',
    } satisfies TaskStatus
    taskStreamMock.events.value = [
      { stage: 'fetch_repo', progress: 5, error: 'clone failed' },
    ] satisfies TaskStreamEvent[]
    analysisResultMock.result.value = null
    analysisResultMock.terminalError.value = 'clone failed'

    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-2',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Task failed')
    expect(wrapper.text()).toContain('clone failed')
  })

  it('cancels a running task and refreshes the status', async () => {
    taskStatusMock.status.value = {
      task_id: 'task-3',
      state: 'running',
      stage: 'scan_tree',
      progress: 55,
      message: null,
      error: null,
      created_at: '2026-04-06T10:00:00Z',
      updated_at: '2026-04-06T10:10:00Z',
    } satisfies TaskStatus
    cancelTaskServiceMock.mockResolvedValue({
      ...taskStatusMock.status.value,
      message: 'Cancellation requested.',
    })

    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-3',
      },
    })

    await flushPromises()
    await wrapper.get('button[data-testid="cancel-task"]').trigger('click')
    await flushPromises()

    expect(cancelTaskServiceMock).toHaveBeenCalledWith('task-3')
    expect(taskStatusMock.refresh).toHaveBeenCalled()
  })

  it('retries a cancelled task and navigates to the new task id', async () => {
    taskStatusMock.status.value = {
      task_id: 'task-4',
      state: 'cancelled',
      stage: 'finalize',
      progress: 60,
      message: 'Cancellation requested.',
      error: null,
      created_at: '2026-04-06T10:00:00Z',
      updated_at: '2026-04-06T10:10:00Z',
    } satisfies TaskStatus
    analysisResultMock.result.value = null
    retryTaskServiceMock.mockResolvedValue({
      task_id: 'task-4-retry',
      status_url: '/api/v1/tasks/task-4-retry',
      result_url: '/api/v1/tasks/task-4-retry/result',
      stream_url: '/api/v1/tasks/task-4-retry/stream',
      task_token: 'retry-token-4',
    })

    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-4',
      },
    })

    await flushPromises()
    await wrapper.get('button[data-testid="retry-task"]').trigger('click')
    await flushPromises()

    expect(retryTaskServiceMock).toHaveBeenCalledWith('task-4')
    expect(routerPushMock).toHaveBeenCalledWith('/tasks/task-4-retry')
  })
})
