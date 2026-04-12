import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchTaskGraph } from '../services/graphApi'
import CodeGraphPanel from './CodeGraphPanel.vue'

vi.mock('../services/graphApi', () => ({
  fetchTaskGraph: vi.fn(),
}))

const fetchTaskGraphMock = vi.mocked(fetchTaskGraph)

describe('CodeGraphPanel linkage', () => {
  beforeEach(() => {
    fetchTaskGraphMock.mockReset()
  })

  it('highlights graph nodes referenced by the selected answer', async () => {
    fetchTaskGraphMock.mockResolvedValue({
      task_id: 'task-graph-linkage',
      view: 'repository',
      focus_node_id: null,
      nodes: [
        {
          node_id: 'function:python:app/main.py:app.main.health',
          kind: 'symbol',
          label: 'app.main.health',
          path: 'app/main.py',
          summary: '健康检查入口。',
          language: 'python',
          symbol_kind: 'function',
          qualified_name: 'app.main.health',
          is_focus: false,
        },
        {
          node_id: 'function:python:app/services/health.py:app.services.health.build_payload',
          kind: 'symbol',
          label: 'app.services.health.build_payload',
          path: 'app/services/health.py',
          summary: '构建健康检查输出。',
          language: 'python',
          symbol_kind: 'function',
          qualified_name: 'app.services.health.build_payload',
          is_focus: false,
        },
      ],
      edges: [],
    } as any)

    const wrapper = mount(CodeGraphPanel, {
      props: {
        taskId: 'task-graph-linkage',
        highlightedNodeIds: ['function:python:app/main.py:app.main.health'],
      },
    })

    await flushPromises()

    expect(wrapper.get('[data-testid="graph-node-function:python:app/main.py:app.main.health"]').classes()).toContain(
      'code-graph-panel__node--linked',
    )
    expect(
      wrapper.get('[data-testid="graph-node-function:python:app/services/health.py:app.services.health.build_payload"]').classes(),
    ).not.toContain('code-graph-panel__node--linked')
  })
})
