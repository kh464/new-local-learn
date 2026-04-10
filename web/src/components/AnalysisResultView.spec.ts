import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AnalysisResultView from './AnalysisResultView.vue'

describe('AnalysisResultView', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('renders stack and backend routes', () => {
    const wrapper = mount(AnalysisResultView, {
      props: {
        taskId: 'task-1',
        result: {
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          html_path: 'artifacts/task-1/result.html',
          pdf_path: 'artifacts/task-1/result.pdf',
          repo_summary: {
            name: 'Hello-World',
            files: ['app/main.py'],
            key_files: ['app/main.py'],
            file_count: 1,
          },
          detected_stack: { frameworks: ['fastapi', 'vue'], languages: ['py', 'ts'] },
          backend_summary: { routes: [{ method: 'GET', path: '/health', source_file: 'app/main.py' }] },
          frontend_summary: {
            framework: 'vue',
            bundler: 'vite',
            state_manager: 'pinia',
            routing: [],
            api_calls: [],
            state_units: [{ name: 'counter', kind: 'pinia-store', source_file: 'web/src/stores/counter.ts' }],
            components: [{ name: 'HomePage', source_file: 'web/src/pages/HomePage.vue', imports: ['RepositorySubmitForm'] }],
          },
          deploy_summary: {
            services: [
              { name: 'redis', source_file: 'docker-compose.yml', ports: ['6379:6379'], depends_on: [] },
              { name: 'api', source_file: 'docker-compose.yml', ports: ['8000:8000'], depends_on: ['redis'] },
            ],
            environment_files: ['.env.example'],
            environment_variables: [{ key: 'REDIS_URL', source_file: '.env.example' }],
            manifests: ['k8s/api.yaml'],
            kubernetes_resources: [{ kind: 'Deployment', name: 'api', source_file: 'k8s/api.yaml' }],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: '这是一条简单的调用链路。',
            request_lifecycle: ['请求从 HomePage 发起', '后端处理 POST /api/v1/analyze'],
            run_steps: ['运行 uvicorn app.main:app'],
            pitfalls: ['Redis 离线会导致任务无法继续'],
            next_steps: ['继续跟踪 POST /api/v1/analyze 在后端的实现'],
            self_check_questions: ['最先启动的模块是什么？'],
            faq_entries: [{ question: '应该从哪里开始？', answer: '先看 app/main.py。' }],
            code_walkthroughs: [
              {
                title: '后端走读：main.py',
                source_file: 'app/main.py',
                snippet: 'from fastapi import FastAPI',
                notes: ['这里创建了应用实例。'],
              },
            ],
          },
          critique_summary: {
            coverage_notes: ['观察到 1 个部署服务。'],
            inferred_sections: ['前端结构信息不足，因此这部分说明带有推断成分。'],
            missing_areas: ['没有检测到更多 Kubernetes 清单。'],
          },
          mermaid_sections: { system: 'graph TD\nA-->B' },
          agent_metadata: {
            enabled: true,
            used_roles: ['frontend', 'tutor'],
            fallbacks: ['critic'],
            execution_nodes: [
              {
                node: 'frontend_analysis',
                stage: 'analyze_frontend',
                kind: 'analysis',
                status: 'completed',
                execution_mode: 'agent',
                depends_on: ['stack_detection'],
              },
              {
                node: 'critic_review',
                stage: 'build_doc',
                kind: 'agent',
                status: 'completed',
                execution_mode: 'deterministic',
                depends_on: ['logic_mapping'],
              },
            ],
          },
        },
      },
    })

    expect(wrapper.text()).toContain('项目概览')
    expect(wrapper.text()).toContain('识别到的技术栈')
    expect(wrapper.text()).toContain('后端分析')
    expect(wrapper.text()).toContain('前端分析')
    expect(wrapper.text()).toContain('部署分析')
    expect(wrapper.text()).toContain('新手学习指南')
    expect(wrapper.text()).toContain('覆盖说明')
    expect(wrapper.text()).toContain('代理执行情况')
    expect(wrapper.text()).toContain('框架：vue')
    expect(wrapper.text()).toContain('构建工具：vite')
    expect(wrapper.text()).toContain('状态管理：pinia')
    expect(wrapper.text()).toContain('环境变量文件：.env.example')
    expect(wrapper.text()).toContain('Kubernetes 清单：k8s/api.yaml')
    expect(wrapper.text()).toContain('依赖 redis')
    expect(wrapper.text()).toContain('请求生命周期')
    expect(wrapper.text()).toContain('代码走读')
    expect(wrapper.text()).toContain('常见陷阱')
    expect(wrapper.text()).toContain('常见问题')
    expect(wrapper.text()).toContain('下一步')
    expect(wrapper.text()).toContain('自检问题')
    expect(wrapper.text()).toContain('已启用：是')
    expect(wrapper.text()).toContain('使用角色：frontend, tutor')
    expect(wrapper.text()).toContain('兜底角色：critic')
    expect(wrapper.text()).toContain('frontend_analysis')
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('助手')
    expect(wrapper.text()).toContain('确定性')
    expect(wrapper.text()).toContain('下载 HTML')
    expect(wrapper.text()).toContain('下载 PDF')
    expect(wrapper.text()).toContain('教程生成状态')
    expect(wrapper.text()).toContain('大模型生成')
  })

  it('renders the markdown artifact path and diagram source separately', () => {
    const wrapper = mount(AnalysisResultView, {
      props: {
        taskId: 'task-1',
        result: {
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          html_path: 'artifacts/task-1/result.html',
          pdf_path: 'artifacts/task-1/result.pdf',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
          detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
          backend_summary: { routes: [] },
          frontend_summary: {
            framework: 'react',
            bundler: 'vite',
            state_manager: 'zustand',
            routing: [],
            api_calls: [],
            state_units: [],
            components: [],
          },
          deploy_summary: {
            services: [],
            environment_files: [],
            environment_variables: [],
            manifests: [],
            kubernetes_resources: [],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: '这是一条简单的调用链路。',
            request_lifecycle: [],
            run_steps: [],
            pitfalls: [],
            next_steps: [],
            self_check_questions: [],
            faq_entries: [],
            code_walkthroughs: [],
          },
          critique_summary: {
            coverage_notes: [],
            inferred_sections: [],
            missing_areas: [],
          },
          mermaid_sections: { system: 'graph TD\nA-->B' },
        },
      },
    })

    expect(wrapper.text()).toContain('Markdown 产物路径')
    expect(wrapper.text()).toContain('HTML 产物路径')
    expect(wrapper.text()).toContain('PDF 产物路径')
    expect(wrapper.text()).toContain('系统图源码')
  })

  it('renders direct artifact download links', () => {
    const wrapper = mount(AnalysisResultView, {
      props: {
        taskId: 'task-88',
        result: {
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-88/repo',
          markdown_path: 'artifacts/task-88/result.md',
          html_path: 'artifacts/task-88/result.html',
          pdf_path: 'artifacts/task-88/result.pdf',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
          detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
          backend_summary: { routes: [] },
          frontend_summary: {
            framework: 'react',
            bundler: 'vite',
            state_manager: null,
            routing: [],
            api_calls: [],
            state_units: [],
            components: [],
          },
          deploy_summary: {
            services: [],
            environment_files: [],
            environment_variables: [],
            manifests: [],
            kubernetes_resources: [],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: '这是一条简单的调用链路。',
            request_lifecycle: [],
            run_steps: [],
            pitfalls: [],
            next_steps: [],
            self_check_questions: [],
            faq_entries: [],
            code_walkthroughs: [],
          },
          critique_summary: {
            coverage_notes: [],
            inferred_sections: [],
            missing_areas: [],
          },
          mermaid_sections: { system: 'graph TD\nA-->B' },
        },
      },
    })

    const links = wrapper.findAll('a[data-artifact-link]')

    expect(links).toHaveLength(3)
    expect(links[0]?.attributes('href')).toContain('/api/v1/tasks/task-88/artifacts/markdown')
    expect(links[1]?.attributes('href')).toContain('/api/v1/tasks/task-88/artifacts/html')
    expect(links[2]?.attributes('href')).toContain('/api/v1/tasks/task-88/artifacts/pdf')
  })

  it('renders authenticated download buttons when only a bearer token is available', () => {
    vi.stubEnv('VITE_ACCESS_TOKEN', 'oidc-access-token')

    const wrapper = mount(AnalysisResultView, {
      props: {
        taskId: 'task-oidc',
        result: {
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-oidc/repo',
          markdown_path: 'artifacts/task-oidc/result.md',
          html_path: 'artifacts/task-oidc/result.html',
          pdf_path: 'artifacts/task-oidc/result.pdf',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
          detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
          backend_summary: { routes: [] },
          frontend_summary: {
            framework: 'react',
            bundler: 'vite',
            state_manager: null,
            routing: [],
            api_calls: [],
            state_units: [],
            components: [],
          },
          deploy_summary: {
            services: [],
            environment_files: [],
            environment_variables: [],
            manifests: [],
            kubernetes_resources: [],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: '这是一条简单的调用链路。',
            request_lifecycle: [],
            run_steps: [],
            pitfalls: [],
            next_steps: [],
            self_check_questions: [],
            faq_entries: [],
            code_walkthroughs: [],
          },
          critique_summary: {
            coverage_notes: [],
            inferred_sections: [],
            missing_areas: [],
          },
          mermaid_sections: { system: 'graph TD\nA-->B' },
        },
      },
    })

    expect(wrapper.findAll('button[data-artifact-button]')).toHaveLength(3)
    expect(wrapper.findAll('a[data-artifact-link]')).toHaveLength(0)
  })

  it('renders tutorial fallback status and reason when llm generation falls back', () => {
    const wrapper = mount(AnalysisResultView, {
      props: {
        taskId: 'task-fallback',
        result: {
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-fallback/repo',
          markdown_path: 'artifacts/task-fallback/result.md',
          html_path: 'artifacts/task-fallback/result.html',
          pdf_path: 'artifacts/task-fallback/result.pdf',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
          detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
          backend_summary: { routes: [] },
          frontend_summary: {
            framework: 'vue',
            bundler: 'vite',
            state_manager: null,
            routing: [],
            api_calls: [],
            state_units: [],
            components: [],
          },
          deploy_summary: {
            services: [],
            environment_files: [],
            environment_variables: [],
            manifests: [],
            kubernetes_resources: [],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: '这是兜底后的中文教程。',
            request_lifecycle: [],
            run_steps: [],
            pitfalls: [],
            next_steps: [],
            self_check_questions: [],
            faq_entries: [],
            code_walkthroughs: [],
          },
          critique_summary: {
            coverage_notes: [],
            inferred_sections: [],
            missing_areas: [],
          },
          mermaid_sections: { system: 'graph TD\nA-->B' },
          agent_metadata: {
            enabled: true,
            used_roles: ['tutor'],
            fallbacks: ['tutorial_generation'],
            execution_nodes: [
              {
                node: 'tutorial_generation',
                stage: 'build_doc',
                kind: 'llm',
                status: 'fallback',
                execution_mode: 'fallback',
                depends_on: ['logic_mapping'],
                reason: 'LLM tutorial output must be Chinese.',
              },
            ],
          },
        },
      },
    })

    expect(wrapper.text()).toContain('教程生成状态')
    expect(wrapper.text()).toContain('已回退到内置生成')
    expect(wrapper.text()).toContain('LLM tutorial output must be Chinese.')
  })
})
