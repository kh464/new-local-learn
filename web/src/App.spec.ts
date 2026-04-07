import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import App from './App.vue'
import { routes } from './router'

describe('App', () => {
  afterEach(() => {
    globalThis.localStorage?.clear()
    vi.unstubAllEnvs()
  })

  it('renders the shell title and router outlet', () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<div data-testid="router-view" />' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    expect(wrapper.get('[data-testid="app-title"]').text()).toContain('GitHub Tech Doc Generator')
    wrapper.get('.app-shell__header')
    expect(wrapper.get('.app-shell__eyebrow').text()).toContain('Engineering Workbench')
    expect(wrapper.text()).toContain('Access Token')
    wrapper.get('.app-shell__main')
    wrapper.get('[data-testid="router-view"]')
  })

  it('stores an access token entered in the shell', async () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<div data-testid="router-view" />' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.get('input[type="password"]').setValue('oidc-access-token')
    await wrapper.get('button').trigger('click')

    expect(globalThis.localStorage.getItem('workbench.access_token')).toBe('oidc-access-token')
  })

  it('renders the home page with the real router', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes,
    })

    router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
      },
    })

    expect(wrapper.text()).toContain('Turn a GitHub project into a living tech brief.')
  })

  it('renders the admin page with the real router', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes,
    })

    router.push('/admin')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
      },
    })

    expect(wrapper.text()).toContain('Operations Console')
  })
})
