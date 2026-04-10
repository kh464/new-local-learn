import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AnalysisResult, TaskStatus, TaskStreamEvent } from '../types/contracts'
import { retryTask, stopTask } from '../services/api'
import TaskDetailPage from './TaskDetailPage.vue'

const routerPushMock = vi.hoisted(() => vi.fn())
const stopTaskMock = vi.hoisted(() => vi.fn())
const retryTaskMock = vi.hoisted(() => vi.fn())

function createStatus(overrides: Partial<TaskStatus> = {}): TaskStatus {
  return {
    task_id: 'task-1',
    state: 'succeeded',
    stage: 'finalize',
    progress: 100,
    message: null,
    error: null,
    knowledge_state: 'ready',
    knowledge_error: null,
    created_at: '2026-04-06T10:00:00Z',
    updated_at: '2026-04-06T10:10:00Z',
    ...overrides,
  }
}

function createResult(): AnalysisResult {
  return {
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
      mental_model: '这是一个简单的调用链路。',
      request_lifecycle: [],
      run_steps: [],
      pitfalls: [],
      next_steps: [],
      self_check_questions: [],
      faq_entries: [],
      code_walkthroughs: [],
    },
    critique_summary: {
      coverage_notes: ['观察到 1 个部署服务。'],
      inferred_sections: [],
      missing_areas: ['没有检测到 Kubernetes 清单。'],
    },
    mermaid_sections: { system: 'graph TD\nA-->B' },
  }
}

const taskStatusMock = vi.hoisted(() => ({
  status: { value: createStatus() as TaskStatus | null },
  loading: { value: false },
  loadError: { value: '' },
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
  result: { value: createResult() as AnalysisResult | null },
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

vi.mock('../components/TaskChatPanel.vue', () => ({
  default: {
    props: ['taskId', 'status'],
    template: '<section data-testid="task-chat-panel">chat panel {{ taskId }} {{ status?.knowledge_state }}</section>',
  },
}))

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    stopTask: stopTaskMock,
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

const stopTaskServiceMock = vi.mocked(stopTask)
const retryTaskServiceMock = vi.mocked(retryTask)

describe('TaskDetailPage', () => {
  beforeEach(() => {
    stopTaskServiceMock.mockReset()
    retryTaskServiceMock.mockReset()
    routerPushMock.mockReset()
    taskStatusMock.refresh.mockReset()
    taskStatusMock.refresh.mockResolvedValue(undefined)
    taskStatusMock.startPolling.mockReset()
    taskStatusMock.stopPolling.mockReset()
    taskStreamMock.connect.mockReset()
    taskStreamMock.disconnect.mockReset()
    analysisResultMock.load.mockReset()
    analysisResultMock.load.mockResolvedValue(undefined)

    taskStatusMock.status.value = createStatus()
    taskStreamMock.events.value = [{ stage: 'scan_tree', progress: 20 }] satisfies TaskStreamEvent[]
    taskStatusMock.loadError.value = ''
    analysisResultMock.result.value = createResult()
    analysisResultMock.pending.value = false
    analysisResultMock.terminalError.value = ''
    analysisResultMock.notFound.value = false
  })

  it('renders result sections and passes knowledge-ready status to the chat panel', async () => {
    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-1',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('task-1')
    expect(wrapper.text()).toContain('Hello-World')
    expect(wrapper.text()).toContain('chat panel task-1 ready')
  })

  it('keeps the chat panel visible while the knowledge base is still building', async () => {
    taskStatusMock.status.value = createStatus({
      stage: 'build_knowledge',
      progress: 95,
      knowledge_state: 'running',
    })

    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-1',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('chat panel task-1 running')
  })

  it('renders a terminal failure message without the chat panel', async () => {
    taskStatusMock.status.value = createStatus({
      task_id: 'task-2',
      state: 'failed',
      stage: 'finalize',
      knowledge_state: 'failed',
      knowledge_error: 'knowledge sqlite locked',
    })
    taskStreamMock.events.value = [{ stage: 'fetch_repo', progress: 5, error: 'clone failed' }] satisfies TaskStreamEvent[]
    analysisResultMock.result.value = null
    analysisResultMock.terminalError.value = 'clone failed'

    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-2',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('clone failed')
    expect(wrapper.find('[data-testid="task-chat-panel"]').exists()).toBe(false)
  })

  it('stops a running task and refreshes the status', async () => {
    taskStatusMock.status.value = createStatus({
      task_id: 'task-3',
      state: 'running',
      stage: 'scan_tree',
      progress: 55,
      knowledge_state: 'pending',
    })
    stopTaskServiceMock.mockResolvedValue({
      ...taskStatusMock.status.value,
      message: 'Cancellation requested.',
    })

    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-3',
      },
    })

    await flushPromises()
    taskStatusMock.refresh.mockClear()
    await wrapper.get('button[data-testid="stop-task"]').trigger('click')
    await flushPromises()

    expect(stopTaskServiceMock).toHaveBeenCalledWith('task-3')
    expect(taskStatusMock.refresh).toHaveBeenCalledTimes(1)
  })

  it('retries a cancelled task and navigates to the new task id', async () => {
    taskStatusMock.status.value = createStatus({
      task_id: 'task-4',
      state: 'cancelled',
      stage: 'finalize',
      progress: 60,
      message: 'Cancellation requested.',
      knowledge_state: 'failed',
    })
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
