import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchTaskChatMessages, submitTaskQuestion } from '../services/api'
import type { TaskStatus } from '../types/contracts'
import TaskChatPanel from './TaskChatPanel.vue'

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    fetchTaskChatMessages: vi.fn(),
    submitTaskQuestion: vi.fn(),
  }
})

const fetchTaskChatMessagesMock = vi.mocked(fetchTaskChatMessages)
const submitTaskQuestionMock = vi.mocked(submitTaskQuestion)

function createStatus(overrides: Partial<TaskStatus> = {}): TaskStatus {
  return {
    task_id: 'task-chat-1',
    state: 'succeeded',
    stage: 'finalize',
    progress: 100,
    message: null,
    error: null,
    knowledge_state: 'ready',
    knowledge_error: null,
    created_at: '2026-04-08T10:00:00Z',
    updated_at: '2026-04-08T10:00:00Z',
    ...overrides,
  }
}

describe('TaskChatPanel', () => {
  beforeEach(() => {
    fetchTaskChatMessagesMock.mockReset()
    submitTaskQuestionMock.mockReset()
    fetchTaskChatMessagesMock.mockResolvedValue({
      task_id: 'task-chat-1',
      messages: [
        {
          message_id: 'assistant-history-1',
          role: 'assistant',
          content: '页面入口是 web/src/main.ts，组件挂载链是 web/src/App.vue -> web/src/components/TaskList.vue，前端入口函数是 web/src/components/TaskList.vue:loadTasks，由 click 交互触发。',
          citations: [
            {
              path: 'web/src/components/TaskList.vue',
              start_line: 12,
              end_line: 28,
              reason: '这里定义了前端点击后触发的 loadTasks。', 
              snippet: '<button @click="loadTasks">刷新</button>',
            },
            {
              path: 'app/api/routes/tasks.py',
              start_line: 1,
              end_line: 8,
              reason: '这里定义了后端处理路由。',
              snippet: '@router.get("/tasks")',
            },
          ],
          graph_evidence: [
            {
              kind: 'entrypoint',
              label: 'backend入口: app/main.py',
              detail: '语言: python',
              path: 'app/main.py',
            },
            {
              kind: 'call_chain',
              label: 'web/src/main.ts -> web/src/App.vue -> web/src/components/TaskList.vue:loadTasks [click] -> GET /api/v1/tasks -> app/api/routes/tasks.py:list_tasks',
              detail: 'GET /api/v1/tasks',
              path: 'app/api/routes/tasks.py',
            },
            {
              kind: 'symbol',
              label: 'list_tasks',
              detail: 'function @ line 4',
              path: 'app/api/routes/tasks.py',
            },
          ],
          supplemental_notes: [],
          confidence: 'high',
          answer_source: 'llm',
          planner_metadata: {
            planning_source: 'llm',
            loop_count: 2,
            used_tools: ['trace_call_chain', 'open_file'],
            fallback_used: false,
          },
          created_at: '2026-04-08T10:00:00Z',
        },
      ],
    })
  })

  it('shows building state without requesting chat history while knowledge is still building', async () => {
    const wrapper = mount(TaskChatPanel, {
      props: {
        taskId: 'task-chat-1',
        status: createStatus({
          stage: 'build_knowledge',
          progress: 95,
          knowledge_state: 'running',
        }),
      },
    })

    await flushPromises()

    expect(fetchTaskChatMessagesMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('知识库构建中')
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
  })

  it('shows failure state when knowledge build failed', async () => {
    const wrapper = mount(TaskChatPanel, {
      props: {
        taskId: 'task-chat-1',
        status: createStatus({
          knowledge_state: 'failed',
          knowledge_error: 'knowledge sqlite locked',
        }),
      },
    })

    await flushPromises()

    expect(fetchTaskChatMessagesMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('知识库构建失败')
    expect(wrapper.text()).toContain('knowledge sqlite locked')
  })

  it('groups graph evidence and renders a structured chain card', async () => {
    const wrapper = mount(TaskChatPanel, {
      props: {
        taskId: 'task-chat-1',
        status: createStatus(),
      },
    })

    await flushPromises()

    expect(fetchTaskChatMessagesMock).toHaveBeenCalledWith('task-chat-1')
    expect(wrapper.text()).toContain('认知图线索')
    expect(wrapper.text()).toContain('入口定位')
    expect(wrapper.text()).toContain('调用链')
    expect(wrapper.text()).toContain('关键符号')
    expect(wrapper.text()).toContain('结构化链路')
    expect(wrapper.text()).toContain('页面入口')
    expect(wrapper.text()).toContain('组件链')
    expect(wrapper.text()).toContain('交互函数')
    expect(wrapper.text()).toContain('接口路由')
    expect(wrapper.text()).toContain('后端处理')
    expect(wrapper.text()).toContain('web/src/main.ts')
    expect(wrapper.text()).toContain('web/src/App.vue')
    expect(wrapper.text()).toContain('web/src/components/TaskList.vue:loadTasks')
    expect(wrapper.text()).toContain('click')
    expect(wrapper.text()).toContain('GET /api/v1/tasks')
    expect(wrapper.text()).toContain('app/api/routes/tasks.py:list_tasks')
    expect(wrapper.text()).not.toContain('代码证据')
    expect(wrapper.text()).toContain('LLM')
    expect(wrapper.text()).toContain('LLM 规划')
  })

  it('submits a new question and appends the exchange', async () => {
    submitTaskQuestionMock.mockResolvedValue({
      task_id: 'task-chat-1',
      user_message: {
        message_id: 'user-1',
        role: 'user',
        content: '前端请求如何到后端？',
        citations: [],
        graph_evidence: [],
        supplemental_notes: [],
        confidence: null,
        answer_source: null,
        created_at: '2026-04-08T10:01:00Z',
      },
      assistant_message: {
        message_id: 'assistant-1',
        role: 'assistant',
        content: '前端会在 web/App.tsx 里通过 fetch 调用 /health，然后进入 app/main.py。',
        citations: [
          {
            path: 'web/App.tsx',
            start_line: 1,
            end_line: 5,
            reason: '这里直接发起了 fetch 请求。',
            snippet: "fetch('/health')",
          },
        ],
        graph_evidence: [
          {
            kind: 'entrypoint',
            label: 'frontend入口: web/App.tsx',
            detail: '语言: typescript',
            path: 'web/App.tsx',
          },
          {
            kind: 'call_chain',
            label: 'web/App.tsx -> GET /health -> app/main.py:health',
            detail: 'GET /health',
            path: 'app/main.py',
          },
        ],
        supplemental_notes: ['如果你要继续追调用链，可以再看 app/main.py。'],
        confidence: 'high',
        answer_source: 'local',
        planner_metadata: {
          planning_source: 'rule',
          loop_count: 1,
          used_tools: ['load_repo_map'],
          fallback_used: true,
        },
        created_at: '2026-04-08T10:01:01Z',
      },
    })

    const wrapper = mount(TaskChatPanel, {
      props: {
        taskId: 'task-chat-1',
        status: createStatus(),
      },
    })

    await flushPromises()
    await wrapper.get('textarea[name="task-question"]').setValue('前端请求如何到后端？')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(submitTaskQuestionMock).toHaveBeenCalledWith('task-chat-1', '前端请求如何到后端？')
    expect(wrapper.text()).toContain('前端会在 web/App.tsx 里通过 fetch 调用 /health，然后进入 app/main.py。')
    expect(wrapper.text()).toContain('如果你要继续追调用链，可以再看 app/main.py。')
    expect(wrapper.text()).toContain('本地知识库')
    expect(wrapper.text()).toContain('规则规划')
  })
})
