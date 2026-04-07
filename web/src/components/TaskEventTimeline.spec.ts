import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskEventTimeline from './TaskEventTimeline.vue'

describe('TaskEventTimeline', () => {
  it('renders ordered event entries', () => {
    const wrapper = mount(TaskEventTimeline, {
      props: {
        events: [
          { stage: 'fetch_repo', progress: 5 },
          { stage: 'scan_tree', progress: 20 },
        ],
      },
    })

    expect(wrapper.text()).toContain('fetch_repo')
    expect(wrapper.text()).toContain('scan_tree')
  })
})
