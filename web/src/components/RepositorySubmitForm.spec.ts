import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RepositorySubmitForm from './RepositorySubmitForm.vue'

describe('RepositorySubmitForm', () => {
  it('disables submit until a url is present', async () => {
    const wrapper = mount(RepositorySubmitForm, {
      props: {
        pending: false,
      },
    })

    const input = wrapper.get('input')
    const button = wrapper.get('button[type="submit"]')

    expect(input.attributes('placeholder')).toBe('https://github.com/octocat/Hello-World')
    expect(button.attributes('disabled')).toBeDefined()

    await input.setValue('https://github.com/octocat/Hello-World')

    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('disables submit while pending', async () => {
    const wrapper = mount(RepositorySubmitForm, {
      props: {
        pending: true,
      },
    })

    await wrapper.get('input').setValue('https://github.com/octocat/Hello-World')

    const button = wrapper.get('button[type="submit"]')

    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toBe('Submitting...')
  })
})
