import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskErrorState from './TaskErrorState.vue'

describe('TaskErrorState', () => {
  it('renders the provided title and message', () => {
    const wrapper = mount(TaskErrorState, {
      props: {
        title: 'Task failed',
        message: 'Repository clone failed.',
      },
    })

    expect(wrapper.text()).toContain('Task failed')
    expect(wrapper.text()).toContain('Repository clone failed.')
  })
})
