import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskEventTimeline from './TaskEventTimeline.vue'

describe('TaskEventTimeline', () => {
  it('renders a fixed stage timeline with the current progress state', () => {
    const wrapper = mount(TaskEventTimeline, {
      props: {
        status: {
          task_id: 'task-1',
          state: 'running',
          stage: 'analyze_backend',
          progress: 50,
          message: null,
          error: null,
          created_at: '2026-04-08T10:00:00Z',
          updated_at: '2026-04-08T10:00:00Z',
        },
        events: [
          { stage: 'fetch_repo', progress: 5 },
          { stage: 'scan_tree', progress: 20 },
          { stage: 'analyze_backend', progress: 50 },
        ],
      },
    })

    expect(wrapper.text()).toContain('任务时间线')
    expect(wrapper.text()).toContain('拉取代码')
    expect(wrapper.text()).toContain('扫描目录')
    expect(wrapper.text()).toContain('识别栈')
    expect(wrapper.text()).toContain('分析后端')
    expect(wrapper.text()).toContain('生成文档')
    expect(wrapper.text()).toContain('50%')
    expect(wrapper.text()).toContain('进行中')
    expect(wrapper.text()).not.toContain('5%')
    expect(wrapper.text()).not.toContain('20%')
  })

  it('surfaces only the latest failure detail instead of dumping every event', () => {
    const wrapper = mount(TaskEventTimeline, {
      props: {
        status: {
          task_id: 'task-2',
          state: 'failed',
          stage: 'finalize',
          progress: 100,
          message: null,
          error: 'deploy analysis failed',
          created_at: '2026-04-08T10:00:00Z',
          updated_at: '2026-04-08T10:00:00Z',
        },
        events: [
          { stage: 'fetch_repo', progress: 5 },
          { stage: 'analyze_frontend', progress: 65, error: 'deploy analysis failed' },
        ],
      },
    })

    expect(wrapper.text()).toContain('deploy analysis failed')
    expect(wrapper.text()).not.toContain('fetch_repo')
  })

  it('does not mark untouched stages as completed when a task is cancelled early', () => {
    const wrapper = mount(TaskEventTimeline, {
      props: {
        status: {
          task_id: 'task-3',
          state: 'cancelled',
          stage: 'fetch_repo',
          progress: 5,
          message: 'Cancellation requested.',
          error: null,
          created_at: '2026-04-08T10:00:00Z',
          updated_at: '2026-04-08T10:00:00Z',
        },
        events: [
          { state: 'running', stage: 'fetch_repo', progress: 5 },
          { state: 'cancelled', stage: 'fetch_repo', progress: 5, message: 'Cancellation requested.' },
        ],
      },
    })

    const items = wrapper.findAll('.timeline__item')
    expect(items[0]?.attributes('data-state')).toBe('failed')
    expect(items[1]?.attributes('data-state')).toBe('upcoming')
    expect(items[2]?.attributes('data-state')).toBe('upcoming')
    expect(wrapper.text()).toContain('Cancellation requested.')
  })
})
