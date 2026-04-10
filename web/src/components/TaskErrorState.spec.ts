import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskErrorState from './TaskErrorState.vue'

describe('TaskErrorState', () => {
  it('renders the provided title and message', () => {
    const wrapper = mount(TaskErrorState, {
      props: {
        title: '任务失败',
        message: '仓库克隆失败。',
      },
    })

    expect(wrapper.text()).toContain('任务失败')
    expect(wrapper.text()).toContain('仓库克隆失败。')
  })
})
