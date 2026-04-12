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
          content:
            'frontend request starts from web/src/main.ts and eventually reaches app/api/routes/tasks.py:list_tasks',
          citations: [
            {
              path: 'web/src/components/TaskList.vue',
              start_line: 12,
              end_line: 28,
              reason: 'loadTasks is triggered here',
              snippet: '<button @click="loadTasks">Refresh</button>',
            },
            {
              path: 'app/api/routes/tasks.py',
              start_line: 1,
              end_line: 8,
              reason: 'backend route definition',
              snippet: '@router.get("/tasks")',
            },
          ],
          graph_evidence: [
            {
              kind: 'entrypoint',
              label: 'backend entrypoint: app/main.py',
              detail: 'language: python',
              path: 'app/main.py',
            },
            {
              kind: 'call_chain',
              label:
                'web/src/main.ts -> web/src/App.vue -> web/src/components/TaskList.vue:loadTasks [click] -> GET /api/v1/tasks -> app/api/routes/tasks.py:list_tasks',
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
            search_queries: [],
          },
          answer_debug: {
            confirmed_facts: [],
            evidence_gaps: [],
            validation_issues: [],
            retry_attempted: false,
            retry_succeeded: false,
            answer_attempts: 1,
            related_node_ids: ['function:python:app/api/routes/tasks.py:list_tasks'],
          },
          created_at: '2026-04-08T10:00:00Z',
        },
      ],
    } as any)
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
        content: 'frontend calls /health from web/App.tsx and reaches app/main.py',
        citations: [
          {
            path: 'web/App.tsx',
            start_line: 1,
            end_line: 5,
            reason: 'fetch is called here',
            snippet: "fetch('/health')",
          },
        ],
        graph_evidence: [
          {
            kind: 'entrypoint',
            label: 'frontend entrypoint: web/App.tsx',
            detail: 'language: typescript',
            path: 'web/App.tsx',
          },
          {
            kind: 'call_chain',
            label: 'web/App.tsx -> GET /health -> app/main.py:health',
            detail: 'GET /health',
            path: 'app/main.py',
          },
        ],
        supplemental_notes: ['continue tracing app/main.py for the next hop'],
        confidence: 'high',
        answer_source: 'local',
        planner_metadata: {
          planning_source: 'rule',
          loop_count: 1,
          used_tools: ['load_repo_map'],
          fallback_used: true,
          search_queries: [],
        },
        answer_debug: {
          confirmed_facts: [],
          evidence_gaps: [],
          validation_issues: [],
          retry_attempted: false,
          retry_succeeded: false,
          answer_attempts: 1,
          related_node_ids: ['function:python:app/main.py:health'],
        },
        created_at: '2026-04-08T10:01:01Z',
      },
    } as any)

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
    expect(wrapper.text()).toContain('frontend calls /health from web/App.tsx and reaches app/main.py')
    expect(wrapper.text()).toContain('continue tracing app/main.py for the next hop')
    expect(wrapper.text()).toContain('本地知识库')
    expect(wrapper.text()).toContain('规则规划')
  })

  it('highlights assistant answers related to the selected graph node ids', async () => {
    fetchTaskChatMessagesMock.mockResolvedValue({
      task_id: 'task-chat-1',
      messages: [
        {
          message_id: 'assistant-related',
          role: 'assistant',
          content: 'health route reaches app.main.health',
          citations: [],
          graph_evidence: [],
          supplemental_notes: [],
          confidence: 'high',
          answer_source: 'llm',
          answer_debug: {
            confirmed_facts: [],
            evidence_gaps: [],
            validation_issues: [],
            retry_attempted: false,
            retry_succeeded: false,
            answer_attempts: 1,
            related_node_ids: ['function:python:app/main.py:app.main.health'],
          },
          planner_metadata: null,
          created_at: '2026-04-08T10:02:00Z',
        },
        {
          message_id: 'assistant-unrelated',
          role: 'assistant',
          content: 'this answer is unrelated to the selected node',
          citations: [],
          graph_evidence: [],
          supplemental_notes: [],
          confidence: 'medium',
          answer_source: 'local',
          answer_debug: {
            confirmed_facts: [],
            evidence_gaps: [],
            validation_issues: [],
            retry_attempted: false,
            retry_succeeded: false,
            answer_attempts: 1,
            related_node_ids: ['file:web/src/App.vue'],
          },
          planner_metadata: null,
          created_at: '2026-04-08T10:02:01Z',
        },
      ],
    } as any)

    const wrapper = mount(TaskChatPanel, {
      props: {
        taskId: 'task-chat-1',
        status: createStatus(),
        selectedNodeIds: ['function:python:app/main.py:app.main.health'],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('当前图谱定位')
    expect(wrapper.text()).toContain('function:python:app/main.py:app.main.health')
    expect(wrapper.text()).toContain('已关联 1 条回答')
    expect(wrapper.get('[data-testid="chat-message-assistant-related"]').classes()).toContain(
      'task-chat__message--linked',
    )
    expect(wrapper.get('[data-testid="chat-message-assistant-unrelated"]').classes()).not.toContain(
      'task-chat__message--linked',
    )
  })
})
