import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import App from './App.vue'
import { routes } from './router'
import * as authSession from './services/authSession'

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

    expect(wrapper.get('[data-testid="app-title"]').text()).toContain('GitHub 技术文档生成器')
    wrapper.get('.app-shell__header')
    expect(wrapper.get('.app-shell__eyebrow').text()).toContain('工程工作台')
    expect(wrapper.text()).toContain('访问令牌')

    const nav = wrapper.get('.app-shell__nav')
    expect(nav.attributes('aria-label')).toBe('主要导航')
    const links = wrapper.findAll('.app-shell__link')
    expect(links[0].text()).toBe('提交任务')
    expect(links[1].text()).toBe('管理台')

    const authControls = wrapper.get('.app-shell__auth-controls')
    const tokenInput = authControls.get('input[type="password"]')
    expect(tokenInput.attributes('placeholder')).toBe('粘贴访问令牌')
    const buttons = authControls.findAll('button')
    expect(buttons[0].text()).toBe('保存令牌')
    expect(buttons[1].text()).toBe('清除')
    wrapper.get('.app-shell__main')
    wrapper.get('[data-testid="router-view"]')
  })

  it('displays localized access token status messages', async () => {
    const mountShell = () =>
      mount(App, {
        global: {
          stubs: {
            RouterView: { template: '<div data-testid="router-view" />' },
            RouterLink: { template: '<a><slot /></a>' },
          },
        },
      })

    const wrapper = mountShell()
    const status = wrapper.get('.app-shell__auth-text')
    expect(status.text()).toBe('未保存访问令牌。')

    const input = wrapper.get('input[type="password"]')
    await input.setValue('oidc-access-token')
    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await wrapper.vm.$nextTick()
    expect(status.text()).toBe('访问令牌已保存在此浏览器会话。')

    vi.stubEnv('VITE_ACCESS_TOKEN', 'env-access-token')
    const envWrapper = mountShell()
    expect(envWrapper.get('.app-shell__auth-text').text()).toBe('访问令牌来自 VITE_ACCESS_TOKEN。')
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

  it('trims the access token before persisting', async () => {
    const setSpy = vi.spyOn(authSession, 'setAccessToken')

    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<div data-testid="router-view" />' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.get('input[type="password"]').setValue('  oauth-token  ')
    await wrapper.get('button').trigger('click')

    expect(setSpy).toHaveBeenCalledWith('oauth-token')
    setSpy.mockRestore()
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

    expect(wrapper.text()).toContain('将 GitHub 项目转化为实时技术简报。')
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

    expect(wrapper.text()).toContain('运维控制台')
  })
})
