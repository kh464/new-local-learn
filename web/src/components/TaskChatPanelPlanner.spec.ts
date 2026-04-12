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

  it('shows planner and answer debug metadata for assistant messages', async () => {
    fetchTaskChatMessagesMock.mockResolvedValue({
      task_id: 'task-chat-planner',
      messages: [
        {
          message_id: 'assistant-1',
          role: 'assistant',
          content: '这是基于真实代码证据的保守回答。',
          citations: [],
          graph_evidence: [],
          supplemental_notes: [],
          confidence: 'medium',
          answer_source: 'llm',
          answer_debug: {
            confirmed_facts: ['已确认命中 KnowledgeRetriever', '已确认仓库存在检索实现'],
            evidence_gaps: ['尚未定位向量检索入口'],
            validation_issues: ['missing_must_include_entity'],
            retry_attempted: true,
            retry_succeeded: true,
            answer_attempts: 2,
          },
          planner_metadata: {
            planning_source: 'rule',
            loop_count: 1,
            used_tools: ['load_repo_map'],
            fallback_used: true,
            search_queries: ['知识库', 'knowledge', 'retriever'],
            question_type: 'capability_check',
            retrieval_objective: '确认仓库是否实现知识库能力并定位核心实现',
            must_include_entities: ['KnowledgeRetriever', 'repo_map'],
            preferred_evidence_kinds: ['capability_fact', 'symbol'],
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
    expect(wrapper.text()).toContain('知识库')
    expect(wrapper.text()).toContain('knowledge')
    expect(wrapper.text()).toContain('retriever')
    expect(wrapper.text()).toContain('确认仓库是否实现知识库能力并定位核心实现')
    expect(wrapper.text()).toContain('KnowledgeRetriever')
    expect(wrapper.text()).toContain('repo_map')
    expect(wrapper.text()).toContain('capability_fact')
    expect(wrapper.text()).toContain('已确认命中 KnowledgeRetriever')
    expect(wrapper.text()).toContain('尚未定位向量检索入口')
    expect(wrapper.text()).toContain('回答校验')
    expect(wrapper.text()).toContain('missing_must_include_entity')
    expect(wrapper.text()).toContain('已触发')
    expect(wrapper.text()).toContain('已修复')
    expect(wrapper.text()).toContain('2')
  })
})
