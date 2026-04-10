import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskStatusCard from './TaskStatusCard.vue'

describe('TaskStatusCard', () => {
  it('renders state, stage, and progress', () => {
    const wrapper = mount(TaskStatusCard, {
      props: {
        status: {
          task_id: 'task-1',
          state: 'running',
          stage: 'detect_stack',
          progress: 35,
          message: null,
          error: null,
          created_at: '2026-04-06T10:00:00Z',
          updated_at: '2026-04-06T10:01:00Z',
        },
      },
    })

    expect(wrapper.text()).toContain('执行中')
    expect(wrapper.text()).toContain('识别技术栈')
    expect(wrapper.text()).toContain('35%')
  })
})
