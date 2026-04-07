import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAuditEvents, fetchMetricsSnapshot, fetchTaskList } from '../services/api'
import AdminPage from './AdminPage.vue'

vi.mock('../services/api', () => ({
  fetchAuditEvents: vi.fn(),
  fetchMetricsSnapshot: vi.fn(),
  fetchTaskList: vi.fn(),
}))

const fetchAuditEventsMock = vi.mocked(fetchAuditEvents)
const fetchMetricsSnapshotMock = vi.mocked(fetchMetricsSnapshot)
const fetchTaskListMock = vi.mocked(fetchTaskList)

describe('AdminPage', () => {
  beforeEach(() => {
    fetchAuditEventsMock.mockReset()
    fetchMetricsSnapshotMock.mockReset()
    fetchTaskListMock.mockReset()
  })

  it('renders audit events and metrics panels', async () => {
    fetchAuditEventsMock.mockResolvedValue({
      total: 1,
      limit: 25,
      offset: 0,
      events: [
        {
          action: 'analyze_submit',
          outcome: 'accepted',
          request_id: 'audit-1',
          method: 'POST',
          path: '/api/v1/analyze',
        },
      ],
    })
    fetchMetricsSnapshotMock.mockResolvedValue({
      analyze_requests_total: 8,
      analysis_jobs_succeeded_total: 5,
    })
    fetchTaskListMock.mockResolvedValue({
      total: 1,
      limit: 8,
      offset: 0,
      tasks: [
        {
          task_id: 'task-ops-1',
          state: 'running',
          stage: 'scan_tree',
          progress: 45,
          message: 'Scanning tree',
          error: null,
          created_at: '2026-04-06T10:00:00Z',
          updated_at: '2026-04-06T10:01:00Z',
          github_url: 'https://github.com/octocat/Hello-World',
        },
      ],
    })

    const wrapper = mount(AdminPage)
    await flushPromises()

    expect(fetchAuditEventsMock).toHaveBeenCalledWith({ limit: 25, offset: 0 })
    expect(fetchTaskListMock).toHaveBeenCalledWith({ limit: 8, offset: 0 })
    expect(wrapper.text()).toContain('Operations Console')
    expect(wrapper.text()).toContain('analyze_requests_total')
    expect(wrapper.text()).toContain('8')
    expect(wrapper.text()).toContain('analyze_submit')
    expect(wrapper.text()).toContain('/api/v1/analyze')
    expect(wrapper.text()).toContain('Recent Tasks')
    expect(wrapper.text()).toContain('task-ops-1')
  })

  it('applies audit filters and reloads the first page', async () => {
    fetchAuditEventsMock.mockResolvedValue({
      total: 0,
      limit: 25,
      offset: 0,
      events: [],
    })
    fetchMetricsSnapshotMock.mockResolvedValue({})
    fetchTaskListMock.mockResolvedValue({
      total: 0,
      limit: 8,
      offset: 0,
      tasks: [],
    })

    const wrapper = mount(AdminPage)
    await flushPromises()

    await wrapper.get('input[name="action"]').setValue('task_artifact_download')
    await wrapper.get('select[name="outcome"]').setValue('success')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(fetchAuditEventsMock).toHaveBeenLastCalledWith({
      limit: 25,
      offset: 0,
      action: 'task_artifact_download',
      outcome: 'success',
    })
  })

  it('loads the next page of audit events', async () => {
    fetchAuditEventsMock
      .mockResolvedValueOnce({
        total: 30,
        limit: 25,
        offset: 0,
        events: [{ action: 'first_page', outcome: 'accepted' }],
      })
      .mockResolvedValueOnce({
        total: 30,
        limit: 25,
        offset: 25,
        events: [{ action: 'second_page', outcome: 'accepted' }],
      })
    fetchMetricsSnapshotMock.mockResolvedValue({})
    fetchTaskListMock.mockResolvedValue({
      total: 0,
      limit: 8,
      offset: 0,
      tasks: [],
    })

    const wrapper = mount(AdminPage)
    await flushPromises()
    await wrapper.get('button[data-testid="audit-next-page"]').trigger('click')
    await flushPromises()

    expect(fetchAuditEventsMock).toHaveBeenLastCalledWith({ limit: 25, offset: 25 })
    expect(wrapper.text()).toContain('second_page')
  })

  it('filters the recent task panel by task state', async () => {
    fetchAuditEventsMock.mockResolvedValue({
      total: 0,
      limit: 25,
      offset: 0,
      events: [],
    })
    fetchMetricsSnapshotMock.mockResolvedValue({})
    fetchTaskListMock.mockResolvedValue({
      total: 0,
      limit: 8,
      offset: 0,
      tasks: [],
    })

    const wrapper = mount(AdminPage)
    await flushPromises()

    await wrapper.get('select[name="task-state"]').setValue('running')
    await wrapper.get('button[data-testid="task-filter-submit"]').trigger('click')
    await flushPromises()

    expect(fetchTaskListMock).toHaveBeenLastCalledWith({
      limit: 8,
      offset: 0,
      state: 'running',
    })
  })

  it('shows an error state when admin data loading fails', async () => {
    fetchAuditEventsMock.mockRejectedValue(new Error('forbidden'))
    fetchMetricsSnapshotMock.mockResolvedValue({})
    fetchTaskListMock.mockResolvedValue({
      total: 0,
      limit: 8,
      offset: 0,
      tasks: [],
    })

    const wrapper = mount(AdminPage)
    await flushPromises()

    expect(wrapper.text()).toContain('forbidden')
  })
})
