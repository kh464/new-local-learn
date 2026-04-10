import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchTaskChatMessages } from '../services/api'
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

function createStatus(overrides: Partial<TaskStatus> = {}): TaskStatus {
  return {
    task_id: 'task-chat-planner',
    state: 'succeeded',
    stage: 'finalize',
    progress: 100,
    message: null,
    error: null,
    knowledge_state: 'ready',
    knowledge_error: null,
    created_at: '2026-04-09T10:00:00Z',
    updated_at: '2026-04-09T10:00:00Z',
    ...overrides,
  }
}

describe('TaskChatPanel planner metadata', () => {
  beforeEach(() => {
    fetchTaskChatMessagesMock.mockReset()
  })

  it('shows both answer source and planning source badges for assistant messages', async () => {
    fetchTaskChatMessagesMock.mockResolvedValue({
      task_id: 'task-chat-planner',
      messages: [
        {
          message_id: 'assistant-1',
          role: 'assistant',
          content: '这是一次基于真实代码证据的保守回答。',
          citations: [],
          graph_evidence: [],
          supplemental_notes: [],
          confidence: 'medium',
          answer_source: 'llm',
          planner_metadata: {
            planning_source: 'rule',
            loop_count: 1,
            used_tools: ['load_repo_map'],
            fallback_used: true,
          },
          created_at: '2026-04-09T10:00:01Z',
        },
      ],
    } as any)

    const wrapper = mount(TaskChatPanel, {
      props: {
        taskId: 'task-chat-planner',
        status: createStatus(),
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('LLM')
    expect(wrapper.text()).toContain('规则规划')
  })
})
