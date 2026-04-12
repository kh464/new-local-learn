import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchTaskGraph } from '../services/graphApi'
import CodeGraphPanel from './CodeGraphPanel.vue'

vi.mock('../services/graphApi', () => ({
  fetchTaskGraph: vi.fn(),
}))

const fetchTaskGraphMock = vi.mocked(fetchTaskGraph)

describe('CodeGraphPanel', () => {
  beforeEach(() => {
    fetchTaskGraphMock.mockReset()
  })

  it('renders graph nodes and highlights the selected node details', async () => {
    fetchTaskGraphMock.mockResolvedValue({
      task_id: 'task-graph-panel',
      view: 'repository',
      focus_node_id: 'function:python:app/main.py:app.main.health',
      nodes: [
        {
          node_id: 'file:app/main.py',
          kind: 'file',
          label: 'app/main.py',
          path: 'app/main.py',
          summary: 'backend entry file',
          language: 'python',
          file_kind: 'entrypoint',
          is_focus: false,
        },
        {
          node_id: 'function:python:app/main.py:app.main.health',
          kind: 'symbol',
          label: 'app.main.health',
          path: 'app/main.py',
          summary: 'health endpoint handler',
          language: 'python',
          symbol_kind: 'function',
          qualified_name: 'app.main.health',
          parent_node_id: 'file:app/main.py',
          start_line: 6,
          end_line: 8,
          is_focus: true,
        },
      ],
      edges: [
        {
          from_node_id: 'file:app/main.py',
          to_node_id: 'function:python:app/main.py:app.main.health',
          kind: 'contains',
          path: 'app/main.py',
          confidence: 1,
        },
      ],
    } as any)

    const wrapper = mount(CodeGraphPanel, {
      props: {
        taskId: 'task-graph-panel',
      },
    })

    await flushPromises()

    expect(fetchTaskGraphMock).toHaveBeenCalledWith('task-graph-panel', { view: 'repository' })
    expect(wrapper.text()).toContain('app/main.py')
    expect(wrapper.text()).toContain('health endpoint handler')
    expect(wrapper.text()).toContain('contains')

    await wrapper.get('[data-testid="graph-node-file:app/main.py"]').trigger('click')

    expect(wrapper.text()).toContain('backend entry file')
  })

  it('emits the selected node id when a graph node is clicked', async () => {
    fetchTaskGraphMock.mockResolvedValue({
      task_id: 'task-graph-panel',
      view: 'repository',
      focus_node_id: null,
      nodes: [
        {
          node_id: 'file:app/main.py',
          kind: 'file',
          label: 'app/main.py',
          path: 'app/main.py',
          summary: 'backend entry file',
          language: 'python',
          file_kind: 'entrypoint',
          is_focus: false,
        },
      ],
      edges: [],
    } as any)

    const wrapper = mount(CodeGraphPanel, {
      props: {
        taskId: 'task-graph-panel',
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="graph-node-file:app/main.py"]').trigger('click')

    expect(wrapper.emitted('select-node')).toEqual([[['file:app/main.py']]])
  })

  it('switches between repository view and symbol subgraph view', async () => {
    fetchTaskGraphMock
      .mockResolvedValueOnce({
        task_id: 'task-graph-panel',
        view: 'repository',
        focus_node_id: null,
        nodes: [
          {
            node_id: 'file:app/main.py',
            kind: 'file',
            label: 'app/main.py',
            path: 'app/main.py',
            summary: 'backend entry file',
            language: 'python',
            file_kind: 'entrypoint',
            is_focus: false,
          },
          {
            node_id: 'function:python:app/main.py:app.main.health',
            kind: 'symbol',
            label: 'app.main.health',
            path: 'app/main.py',
            summary: 'health endpoint handler',
            language: 'python',
            symbol_kind: 'function',
            qualified_name: 'app.main.health',
            parent_node_id: 'file:app/main.py',
            start_line: 6,
            end_line: 8,
            is_focus: false,
          },
        ],
        edges: [],
      } as any)
      .mockResolvedValueOnce({
        task_id: 'task-graph-panel',
        view: 'symbol',
        focus_node_id: 'function:python:app/main.py:app.main.health',
        nodes: [
          {
            node_id: 'function:python:app/main.py:app.main.health',
            kind: 'symbol',
            label: 'app.main.health',
            path: 'app/main.py',
            summary: 'symbol subgraph',
            language: 'python',
            symbol_kind: 'function',
            qualified_name: 'app.main.health',
            is_focus: true,
          },
        ],
        edges: [],
      } as any)
      .mockResolvedValueOnce({
        task_id: 'task-graph-panel',
        view: 'repository',
        focus_node_id: null,
        nodes: [
          {
            node_id: 'file:app/main.py',
            kind: 'file',
            label: 'app/main.py',
            path: 'app/main.py',
            summary: 'repository graph again',
            language: 'python',
            file_kind: 'entrypoint',
            is_focus: false,
          },
        ],
        edges: [],
      } as any)

    const wrapper = mount(CodeGraphPanel, {
      props: {
        taskId: 'task-graph-panel',
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="graph-node-function:python:app/main.py:app.main.health"]').trigger('click')
    await wrapper.get('[data-testid="graph-open-symbol-view"]').trigger('click')
    await flushPromises()

    expect(fetchTaskGraphMock).toHaveBeenNthCalledWith(2, 'task-graph-panel', {
      view: 'symbol',
      symbolId: 'function:python:app/main.py:app.main.health',
    })
    expect(wrapper.text()).toContain('symbol subgraph')

    await wrapper.get('[data-testid="graph-back-repository"]').trigger('click')
    await flushPromises()

    expect(fetchTaskGraphMock).toHaveBeenNthCalledWith(3, 'task-graph-panel', { view: 'repository' })
    expect(wrapper.text()).toContain('repository graph again')
  })

  it('switches from repository view into module subgraph view', async () => {
    fetchTaskGraphMock
      .mockResolvedValueOnce({
        task_id: 'task-graph-panel',
        view: 'repository',
        focus_node_id: null,
        nodes: [
          {
            node_id: 'file:app/services/health.py',
            kind: 'file',
            label: 'app/services/health.py',
            path: 'app/services/health.py',
            summary: 'health module',
            language: 'python',
            file_kind: 'module',
            is_focus: false,
          },
        ],
        edges: [],
      } as any)
      .mockResolvedValueOnce({
        task_id: 'task-graph-panel',
        view: 'module',
        focus_node_id: 'file:app/services/health.py',
        nodes: [
          {
            node_id: 'file:app/services/health.py',
            kind: 'file',
            label: 'app/services/health.py',
            path: 'app/services/health.py',
            summary: 'module subgraph',
            language: 'python',
            file_kind: 'module',
            is_focus: true,
          },
        ],
        edges: [],
      } as any)

    const wrapper = mount(CodeGraphPanel, {
      props: {
        taskId: 'task-graph-panel',
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="graph-node-file:app/services/health.py"]').trigger('click')
    await wrapper.get('[data-testid="graph-open-module-view"]').trigger('click')
    await flushPromises()

    expect(fetchTaskGraphMock).toHaveBeenNthCalledWith(2, 'task-graph-panel', {
      view: 'module',
      path: 'app/services/health.py',
    })
    expect(wrapper.text()).toContain('module subgraph')
  })
})
