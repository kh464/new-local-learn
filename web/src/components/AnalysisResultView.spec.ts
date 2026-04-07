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
            mental_model: 'A simple flow',
            request_lifecycle: ['Request starts in HomePage', 'Backend handles POST /api/v1/analyze'],
            run_steps: ['uvicorn app.main:app'],
            pitfalls: ['Redis offline'],
            next_steps: ['Trace POST /api/v1/analyze through the backend'],
            self_check_questions: ['What runs first?'],
            faq_entries: [{ question: 'Where do I start?', answer: 'Start with app/main.py.' }],
            code_walkthroughs: [
              {
                title: 'Backend walkthrough: main.py',
                source_file: 'app/main.py',
                snippet: 'from fastapi import FastAPI',
                notes: ['This creates the app instance.'],
              },
            ],
          },
          critique_summary: {
            coverage_notes: ['Observed 1 deploy services.'],
            inferred_sections: ['Frontend architecture was not detected; frontend notes are omitted.'],
            missing_areas: ['No Kubernetes manifests detected.'],
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

    expect(wrapper.text()).toContain('fastapi')
    expect(wrapper.text()).toContain('/health')
    expect(wrapper.text()).toContain('pinia')
    expect(wrapper.text()).toContain('counter')
    expect(wrapper.text()).toContain('HomePage')
    expect(wrapper.text()).toContain('Request Lifecycle')
    expect(wrapper.text()).toContain('Code Walkthroughs')
    expect(wrapper.text()).toContain('Pitfalls')
    expect(wrapper.text()).toContain('Redis offline')
    expect(wrapper.text()).toContain('FAQ')
    expect(wrapper.text()).toContain('Where do I start?')
    expect(wrapper.text()).toContain('Next Steps')
    expect(wrapper.text()).toContain('Self-Check')
    expect(wrapper.text()).toContain('What runs first?')
    expect(wrapper.text()).toContain('Deploy Analysis')
    expect(wrapper.text()).toContain('redis')
    expect(wrapper.text()).toContain('api')
    expect(wrapper.text()).toContain('depends on redis')
    expect(wrapper.text()).toContain('REDIS_URL')
    expect(wrapper.text()).toContain('Deployment')
    expect(wrapper.text()).toContain('api')
    expect(wrapper.text()).toContain('Coverage Notes')
    expect(wrapper.text()).toContain('No Kubernetes manifests detected.')
    expect(wrapper.text()).toContain('Agent Execution')
    expect(wrapper.text()).toContain('frontend, tutor')
    expect(wrapper.text()).toContain('critic')
    expect(wrapper.text()).toContain('frontend_analysis')
    expect(wrapper.text()).toContain('result.html')
    expect(wrapper.text()).toContain('result.pdf')
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
            mental_model: 'Simple flow',
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

    expect(wrapper.text()).toContain('Markdown Artifact Path')
    expect(wrapper.text()).toContain('HTML Artifact Path')
    expect(wrapper.text()).toContain('PDF Artifact Path')
    expect(wrapper.text()).toContain('System Diagram Source')
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
            mental_model: 'Simple flow',
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
            mental_model: 'Simple flow',
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
})
