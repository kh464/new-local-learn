import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildTaskArtifactUrl,
  cancelTask,
  createAnalysisTask,
  downloadTaskArtifact,
  fetchAuditEvents,
  fetchMetricsSnapshot,
  fetchTaskList,
  fetchTaskResult,
  fetchTaskStatus,
  retryTask,
} from './api'
import { clearTaskTokens } from './taskAccess'

describe('api service', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    clearTaskTokens()
  })

  it('creates an analysis task from the backend response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({
        task_id: 'task-1',
        status_url: '/api/v1/tasks/task-1',
        result_url: '/api/v1/tasks/task-1/result',
        stream_url: '/api/v1/tasks/task-1/stream',
        task_token: 'task-token-1',
      }),
    })
    vi.stubGlobal(
      'fetch',
      fetchMock,
    )
    vi.stubGlobal('crypto', { randomUUID: () => 'req-123' })

    const result = await createAnalysisTask('https://github.com/octocat/Hello-World')

    expect(result.task_id).toBe('task-1')
    expect(result.result_url).toBe('/api/v1/tasks/task-1/result')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/analyze',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-123',
        }),
      }),
    )
  })

  it('sends the configured API key header when present', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({
        task_id: 'task-1',
        status_url: '/api/v1/tasks/task-1',
        result_url: '/api/v1/tasks/task-1/result',
        stream_url: '/api/v1/tasks/task-1/stream',
        task_token: 'task-token-1',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'req-456' })
    vi.stubEnv('VITE_API_KEY', 'frontend-secret')

    await createAnalysisTask('https://github.com/octocat/Hello-World')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/analyze',
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-API-Key': 'frontend-secret',
        }),
      }),
    )
  })

  it('sends the configured bearer token when present', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({
        task_id: 'task-1',
        status_url: '/api/v1/tasks/task-1',
        result_url: '/api/v1/tasks/task-1/result',
        stream_url: '/api/v1/tasks/task-1/stream',
        task_token: 'task-token-1',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'req-oidc-1' })
    vi.stubEnv('VITE_ACCESS_TOKEN', 'oidc-access-token')

    await createAnalysisTask('https://github.com/octocat/Hello-World')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/analyze',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer oidc-access-token',
        }),
      }),
    )
  })

  it('returns a pending result union for HTTP 202', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({ task_id: 'task-1', state: 'running' }),
      }),
    )

    const result = await fetchTaskResult('task-1')

    expect(result.kind).toBe('pending')
    if (result.kind !== 'pending') {
      throw new Error('Expected a pending task result.')
    }
    expect(result.state).toBe('running')
  })

  it('reuses the issued task token for later task reads', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 202,
        text: async () =>
          JSON.stringify({
            task_id: 'task-1',
            status_url: '/api/v1/tasks/task-1',
            result_url: '/api/v1/tasks/task-1/result',
            stream_url: '/api/v1/tasks/task-1/stream',
            task_token: 'task-token-1',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify({
            task_id: 'task-1',
            state: 'running',
            stage: null,
            progress: 25,
            message: null,
            error: null,
            created_at: '2026-04-06T10:00:00Z',
            updated_at: '2026-04-06T10:01:00Z',
          }),
      })
    vi.stubGlobal('fetch', fetchMock)

    await createAnalysisTask('https://github.com/octocat/Hello-World')
    await fetchTaskStatus('task-1')

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/tasks/task-1',
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Task-Token': 'task-token-1',
        }),
      }),
    )
  })

  it('cancels an in-flight task', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        text: async () =>
          JSON.stringify({
            task_id: 'task-1',
            state: 'running',
            stage: 'scan_tree',
            progress: 35,
            message: 'Cancellation requested.',
            error: null,
            created_at: '2026-04-06T10:00:00Z',
            updated_at: '2026-04-06T10:01:00Z',
          }),
      }),
    )

    const result = await cancelTask('task-1')

    expect(result.task_id).toBe('task-1')
    expect(result.message).toBe('Cancellation requested.')
  })

  it('retries a failed task and stores the new task token', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 202,
        text: async () =>
          JSON.stringify({
            task_id: 'task-2',
            status_url: '/api/v1/tasks/task-2',
            result_url: '/api/v1/tasks/task-2/result',
            stream_url: '/api/v1/tasks/task-2/stream',
            task_token: 'retry-token-2',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify({
            task_id: 'task-2',
            state: 'queued',
            stage: null,
            progress: 0,
            message: null,
            error: null,
            created_at: '2026-04-06T10:02:00Z',
            updated_at: '2026-04-06T10:02:00Z',
          }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const result = await retryTask('task-1')
    await fetchTaskStatus(result.task_id)

    expect(result.task_id).toBe('task-2')
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/tasks/task-2',
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Task-Token': 'retry-token-2',
        }),
      }),
    )
  })

  it('builds an artifact download url with the stored task token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      text: async () =>
        JSON.stringify({
          task_id: 'task-1',
          status_url: '/api/v1/tasks/task-1',
          result_url: '/api/v1/tasks/task-1/result',
          stream_url: '/api/v1/tasks/task-1/stream',
          task_token: 'task-token-1',
        }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await createAnalysisTask('https://github.com/octocat/Hello-World')

    expect(buildTaskArtifactUrl('task-1', 'pdf')).toBe('/api/v1/tasks/task-1/artifacts/pdf?task_token=task-token-1')
  })

  it('prefers the configured api key when building artifact download urls', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test')
    vi.stubEnv('VITE_API_KEY', 'frontend-secret')

    expect(buildTaskArtifactUrl('task-77', 'html')).toBe(
      'https://api.example.test/api/v1/tasks/task-77/artifacts/html?api_key=frontend-secret',
    )
  })

  it('fetches audit events from the admin endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify({
            total: 1,
            limit: 20,
            offset: 5,
            events: [
              { action: 'task_artifact_download', outcome: 'success', request_id: 'req-1' },
            ],
          }),
      }),
    )

    const result = await fetchAuditEvents({ limit: 20, offset: 5, action: 'task_artifact_download' })

    expect(result).toEqual({
      total: 1,
      limit: 20,
      offset: 5,
      events: [{ action: 'task_artifact_download', outcome: 'success', request_id: 'req-1' }],
    })
  })

  it('parses prometheus metrics text into a snapshot', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => 'analyze_requests_total 2\nanalysis_jobs_succeeded_total 1\n',
      }),
    )

    const result = await fetchMetricsSnapshot()

    expect(result).toEqual({
      analyze_requests_total: 2,
      analysis_jobs_succeeded_total: 1,
    })
  })

  it('fetches the recent task list for admin views', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify({
            total: 1,
            limit: 8,
            offset: 0,
            tasks: [
              {
                task_id: 'task-2',
                state: 'running',
                stage: 'scan_tree',
                progress: 40,
                message: 'Scanning files',
                error: null,
                created_at: '2026-04-06T10:00:00Z',
                updated_at: '2026-04-06T10:01:00Z',
                github_url: 'https://github.com/octocat/Hello-World',
              },
            ],
          }),
      }),
    )

    const result = await fetchTaskList({ limit: 8, offset: 0, state: 'running' })

    expect(result.total).toBe(1)
    expect(result.tasks[0]?.task_id).toBe('task-2')
    expect(result.tasks[0]?.github_url).toBe('https://github.com/octocat/Hello-World')
  })

  it('downloads artifacts with the bearer token when direct links cannot carry auth', async () => {
    const appendMock = vi.fn()
    const removeMock = vi.fn()
    const clickMock = vi.fn()
    const createElementMock = vi.fn().mockReturnValue({
      click: clickMock,
      remove: removeMock,
      href: '',
      download: '',
    })
    vi.stubGlobal(
      'document',
      {
        body: { append: appendMock },
        createElement: createElementMock,
      } as unknown as Document,
    )
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:artifact'),
      revokeObjectURL: vi.fn(),
    })
    vi.stubEnv('VITE_ACCESS_TOKEN', 'oidc-access-token')
    vi.stubGlobal('crypto', { randomUUID: () => 'req-download-1' })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        blob: async () => new Blob(['artifact']),
        headers: { get: () => 'application/pdf' },
      }),
    )

    await downloadTaskArtifact('task-77', 'pdf')

    expect(createElementMock).toHaveBeenCalledWith('a')
    expect(clickMock).toHaveBeenCalled()
  })

  it('throws for malformed analysis task responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({
          task_id: 'task-1',
          status_url: '/api/v1/tasks/task-1',
          result_url: '/api/v1/tasks/task-1/result',
        }),
      }),
    )

    await expect(createAnalysisTask('https://github.com/octocat/Hello-World')).rejects.toThrow(
      'Invalid analysis task response.',
    )
  })

  it('throws for malformed task status responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          task_id: 'task-1',
          state: 'running',
          stage: 'ship_it',
          progress: 25,
          message: null,
          error: null,
          created_at: '2026-04-06T10:00:00Z',
          updated_at: '2026-04-06T10:01:00Z',
        }),
      }),
    )

    await expect(fetchTaskStatus('task-1')).rejects.toThrow('Invalid task status payload.')
  })

  it('throws a request error for non-json failing responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => '',
      }),
    )

    await expect(createAnalysisTask('https://github.com/octocat/Hello-World')).rejects.toThrow(
      'Request failed with status 500',
    )
  })

  it('surfaces backend error detail for rate limiting responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        text: async () => JSON.stringify({ detail: 'Rate limit exceeded.' }),
      }),
    )

    await expect(createAnalysisTask('https://github.com/octocat/Hello-World')).rejects.toThrow(
      'Rate limit exceeded.',
    )
  })

  it('throws for malformed successful result payloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ state: 'succeeded' }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws for malformed pending result payloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({ task_id: 7 }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws when a pending result payload uses a terminal state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({ task_id: 'task-1', state: 'failed' }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws for incomplete successful result payloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ github_url: 'https://github.com/octocat/Hello-World' }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws for malformed nested successful result payloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          html_path: 'artifacts/task-1/result.html',
          pdf_path: 'artifacts/task-1/result.pdf',
          repo_summary: {
            name: 'Hello-World',
            files: [],
            key_files: [],
            file_count: 1,
          },
          detected_stack: {
            frameworks: 'vue',
            languages: ['typescript'],
          },
          backend_summary: { routes: [] },
          frontend_summary: {
            framework: 'vue',
            bundler: 'vite',
            state_manager: 'pinia',
            routing: [],
            api_calls: [],
            components: [],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: 'Simple flow',
            run_steps: [],
            pitfalls: [],
            self_check_questions: [],
          },
          mermaid_sections: { system: 'graph TD\\nA-->B' },
        }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws for successful results missing frontend metadata', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          html_path: 'artifacts/task-1/result.html',
          pdf_path: 'artifacts/task-1/result.pdf',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 1 },
          detected_stack: { frameworks: ['react'], languages: ['typescript'] },
          backend_summary: { routes: [] },
          frontend_summary: { routing: [], api_calls: [] },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: 'Simple flow',
            run_steps: [],
            pitfalls: [],
            self_check_questions: [],
          },
          mermaid_sections: { system: 'graph TD\\nA-->B' },
        }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws for successful results missing tutorial guide sections', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          html_path: 'artifacts/task-1/result.html',
          pdf_path: 'artifacts/task-1/result.pdf',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 1 },
          detected_stack: { frameworks: ['fastapi', 'react'], languages: ['python', 'typescript'] },
          backend_summary: { routes: [] },
          frontend_summary: {
            framework: 'react',
            bundler: 'vite',
            state_manager: 'zustand',
            routing: [],
            api_calls: [],
            components: [],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: 'Simple flow',
            run_steps: [],
            pitfalls: [],
            self_check_questions: [],
          },
          mermaid_sections: { system: 'graph TD\\nA-->B' },
        }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws for successful results missing deploy and critique sections', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          html_path: 'artifacts/task-1/result.html',
          pdf_path: 'artifacts/task-1/result.pdf',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 1 },
          detected_stack: { frameworks: ['fastapi', 'vue'], languages: ['python', 'typescript'] },
          backend_summary: { routes: [] },
          frontend_summary: {
            framework: 'vue',
            bundler: 'vite',
            state_manager: 'pinia',
            routing: [],
            api_calls: [],
            components: [],
          },
          logic_summary: { flows: [] },
          tutorial_summary: {
            mental_model: 'Simple flow',
            request_lifecycle: [],
            run_steps: [],
            pitfalls: [],
            next_steps: [],
            self_check_questions: [],
            code_walkthroughs: [],
          },
          mermaid_sections: { system: 'graph TD\\nA-->B' },
        }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws when a terminal error payload uses a non-terminal state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-1', state: 'running', error: 'still processing' }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })

  it('throws when a terminal error payload has a non-string error message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-1', state: 'failed', error: { detail: 'boom' } }),
      }),
    )

    await expect(fetchTaskResult('task-1')).rejects.toThrow('Invalid result payload.')
  })
})
