export type TaskState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
export type PendingTaskState = Extract<TaskState, 'queued' | 'running'>
export type FailedTaskState = Extract<TaskState, 'failed' | 'cancelled'>
export type TaskStage =
  | 'fetch_repo'
  | 'scan_tree'
  | 'detect_stack'
  | 'analyze_backend'
  | 'analyze_frontend'
  | 'build_doc'
  | 'build_knowledge'
  | 'finalize'

export type TaskKnowledgeState = 'pending' | 'running' | 'ready' | 'failed'

export interface TaskStatus {
  task_id: string
  state: TaskState
  stage: TaskStage | null
  progress: number
  message: string | null
  error: string | null
  knowledge_state?: TaskKnowledgeState | null
  knowledge_error?: string | null
  created_at: string
  updated_at: string
}

export interface TaskListItem extends TaskStatus {
  github_url?: string | null
}

export interface TaskListQuery {
  limit?: number
  offset?: number
  state?: TaskState
}

export interface TaskListPage {
  tasks: TaskListItem[]
  total: number
  limit: number
  offset: number
}

export interface AnalysisTaskResponse {
  task_id: string
  status_url: string
  result_url: string
  stream_url: string
  task_token: string
}

export interface TaskChatCitation {
  path: string
  start_line: number
  end_line: number
  reason: string
  snippet: string
}

export interface TaskGraphEvidence {
  kind: 'entrypoint' | 'symbol' | 'edge' | 'call_chain'
  label: string
  detail?: string | null
  path?: string | null
}

export interface PlannerMetadata {
  planning_source: string
  loop_count: number
  used_tools: string[]
  fallback_used: boolean
  search_queries: string[]
}

export interface TaskChatMessage {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  citations: TaskChatCitation[]
  graph_evidence?: TaskGraphEvidence[]
  supplemental_notes: string[]
  confidence?: 'high' | 'medium' | 'low' | null
  answer_source?: 'llm' | 'local' | null
  planner_metadata?: PlannerMetadata | null
  created_at: string
}

export interface TaskChatHistory {
  task_id: string
  messages: TaskChatMessage[]
}

export interface TaskChatExchange {
  task_id: string
  user_message: TaskChatMessage
  assistant_message: TaskChatMessage
}

export interface RepositorySummary {
  name: string
  files: string[]
  key_files: string[]
  file_count: number
}

export interface AnalysisResult {
  github_url: string
  repo_path: string
  markdown_path: string
  html_path: string
  pdf_path: string
  repo_summary: RepositorySummary
  detected_stack: {
    frameworks: string[]
    languages: string[]
  }
  backend_summary: {
    routes: Array<{
      method: string
      path: string
      source_file: string | null
    }>
  }
  frontend_summary: {
    framework: string | null
    bundler: string | null
    state_manager: string | null
    routing: Array<{
      path: string
      source_file: string | null
    }>
    api_calls: Array<{
      url: string
      source_file: string | null
      client: string | null
      method: string | null
    }>
    state_units: Array<{
      name: string
      kind: string
      source_file: string
    }>
    components: Array<{
      name: string
      source_file: string
      imports: string[]
    }>
  }
  deploy_summary: {
    services: Array<{
      name: string
      source_file: string
      ports: string[]
      depends_on?: string[]
    }>
    environment_files: string[]
    manifests: string[]
    environment_variables?: Array<{
      key: string
      source_file: string
    }>
    kubernetes_resources?: Array<{
      kind: string
      name: string
      source_file: string
    }>
  }
  logic_summary: {
    flows: Array<{
      frontend_call: string
      frontend_source: string
      backend_route: string
      backend_source: string
      backend_method: string
      confidence: number
    }>
  }
  tutorial_summary: {
    mental_model: string
    request_lifecycle: string[]
    run_steps: string[]
    pitfalls: string[]
    next_steps: string[]
    self_check_questions: string[]
    faq_entries: Array<{
      question: string
      answer: string
    }>
    code_walkthroughs: Array<{
      title: string
      source_file: string
      snippet: string
      notes: string[]
    }>
  }
  critique_summary: {
    coverage_notes: string[]
    inferred_sections: string[]
    missing_areas: string[]
  }
  mermaid_sections: {
    system: string
  }
  agent_metadata?: {
    enabled: boolean
    used_roles: string[]
    fallbacks: string[]
    execution_nodes: Array<{
      node: string
      stage: string
      kind: string
      status: string
      depends_on: string[]
      execution_mode?: string
      reason?: string | null
    }>
  }
}

export type TaskResultResponse =
  | {
      kind: 'pending'
      task_id: string
      state: PendingTaskState
    }
  | {
      kind: 'failed'
      task_id: string
      state: FailedTaskState
      error?: string
    }
  | {
      kind: 'success'
      data: AnalysisResult
    }

export interface TaskStreamEvent {
  state?: TaskState
  stage?: TaskStage
  progress?: number
  node?: string
  message?: string
  error?: string
  knowledge_state?: TaskKnowledgeState
  knowledge_error?: string
}

export interface AuditEvent {
  action: string
  outcome: string
  request_id?: string | null
  method?: string
  path?: string
  client_ip?: string
  task_id?: string
  subject?: string
  github_url?: string
  artifact_kind?: string
  required_scopes?: string[]
}

export interface AuditEventQuery {
  limit?: number
  offset?: number
  action?: string
  outcome?: string
  task_id?: string
  request_id?: string
  subject?: string
  method?: string
  path?: string
}

export interface AuditEventsPage {
  events: AuditEvent[]
  total: number
  limit: number
  offset: number
}

export type MetricsSnapshot = Record<string, number>

export const taskStates = ['queued', 'running', 'succeeded', 'failed', 'cancelled'] as const
export const pendingTaskStates = ['queued', 'running'] as const
export const failedTaskStates = ['failed', 'cancelled'] as const
export const taskStages = [
  'fetch_repo',
  'scan_tree',
  'detect_stack',
  'analyze_backend',
  'analyze_frontend',
  'build_doc',
  'build_knowledge',
  'finalize',
] as const
export const taskKnowledgeStates = ['pending', 'running', 'ready', 'failed'] as const
const taskStreamEventKeys = ['state', 'stage', 'progress', 'node', 'message', 'error', 'knowledge_state', 'knowledge_error'] as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isRecordArray<T>(value: unknown, predicate: (item: unknown) => item is T): value is T[] {
  return Array.isArray(value) && value.every((item) => predicate(item))
}

function isRepositorySummary(value: unknown): value is RepositorySummary {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    isStringArray(value.files) &&
    isStringArray(value.key_files) &&
    typeof value.file_count === 'number'
  )
}

function isTaskChatCitation(value: unknown): value is TaskChatCitation {
  return (
    isRecord(value) &&
    typeof value.path === 'string' &&
    isNumber(value.start_line) &&
    isNumber(value.end_line) &&
    typeof value.reason === 'string' &&
    typeof value.snippet === 'string'
  )
}

function isTaskGraphEvidence(value: unknown): value is TaskGraphEvidence {
  return (
    isRecord(value) &&
    (value.kind === 'entrypoint' || value.kind === 'symbol' || value.kind === 'edge' || value.kind === 'call_chain') &&
    typeof value.label === 'string' &&
    (value.detail === undefined || isNullableString(value.detail)) &&
    (value.path === undefined || isNullableString(value.path))
  )
}

function isPlannerMetadata(value: unknown): value is PlannerMetadata {
  return (
    isRecord(value) &&
    typeof value.planning_source === 'string' &&
    isNumber(value.loop_count) &&
    isStringArray(value.used_tools) &&
    typeof value.fallback_used === 'boolean' &&
    isStringArray(value.search_queries)
  )
}

function isTaskChatMessage(value: unknown): value is TaskChatMessage {
  return (
    isRecord(value) &&
    typeof value.message_id === 'string' &&
    (value.role === 'user' || value.role === 'assistant') &&
    typeof value.content === 'string' &&
    isRecordArray(value.citations, isTaskChatCitation) &&
    (value.graph_evidence === undefined || isRecordArray(value.graph_evidence, isTaskGraphEvidence)) &&
    isStringArray(value.supplemental_notes) &&
    (value.confidence === undefined ||
      value.confidence === null ||
      value.confidence === 'high' ||
      value.confidence === 'medium' ||
      value.confidence === 'low') &&
    (value.answer_source === undefined ||
      value.answer_source === null ||
      value.answer_source === 'llm' ||
      value.answer_source === 'local') &&
    (value.planner_metadata === undefined ||
      value.planner_metadata === null ||
      isPlannerMetadata(value.planner_metadata)) &&
    typeof value.created_at === 'string'
  )
}

function isBackendRouteSummary(
  value: unknown,
): value is AnalysisResult['backend_summary']['routes'][number] {
  return (
    isRecord(value) &&
    typeof value.method === 'string' &&
    typeof value.path === 'string' &&
    (value.source_file === null || typeof value.source_file === 'string')
  )
}

function isFrontendRouteSummary(
  value: unknown,
): value is AnalysisResult['frontend_summary']['routing'][number] {
  return (
    isRecord(value) &&
    typeof value.path === 'string' &&
    (value.source_file === null || typeof value.source_file === 'string')
  )
}

function isFrontendApiCallSummary(
  value: unknown,
): value is AnalysisResult['frontend_summary']['api_calls'][number] {
  return (
    isRecord(value) &&
    typeof value.url === 'string' &&
    (value.source_file === null || typeof value.source_file === 'string') &&
    (value.client === null || value.client === undefined || typeof value.client === 'string') &&
    (value.method === null || value.method === undefined || typeof value.method === 'string')
  )
}

function isFrontendComponentSummary(
  value: unknown,
): value is AnalysisResult['frontend_summary']['components'][number] {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    typeof value.source_file === 'string' &&
    isStringArray(value.imports)
  )
}

function isFrontendStateUnitSummary(
  value: unknown,
): value is AnalysisResult['frontend_summary']['state_units'][number] {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    typeof value.kind === 'string' &&
    typeof value.source_file === 'string'
  )
}

function isLogicFlowSummary(value: unknown): value is AnalysisResult['logic_summary']['flows'][number] {
  return (
    isRecord(value) &&
    typeof value.frontend_call === 'string' &&
    typeof value.frontend_source === 'string' &&
    typeof value.backend_route === 'string' &&
    typeof value.backend_source === 'string' &&
    typeof value.backend_method === 'string' &&
    typeof value.confidence === 'number'
  )
}

function isDeployServiceSummary(
  value: unknown,
): value is AnalysisResult['deploy_summary']['services'][number] {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    typeof value.source_file === 'string' &&
    isStringArray(value.ports) &&
    (value.depends_on === undefined || isStringArray(value.depends_on))
  )
}

function isKubernetesResourceSummary(
  value: unknown,
): value is NonNullable<AnalysisResult['deploy_summary']['kubernetes_resources']>[number] {
  return (
    isRecord(value) &&
    typeof value.kind === 'string' &&
    typeof value.name === 'string' &&
    typeof value.source_file === 'string'
  )
}

function isEnvironmentVariableSummary(
  value: unknown,
): value is NonNullable<AnalysisResult['deploy_summary']['environment_variables']>[number] {
  return isRecord(value) && typeof value.key === 'string' && typeof value.source_file === 'string'
}

function isTutorialCodeWalkthrough(
  value: unknown,
): value is AnalysisResult['tutorial_summary']['code_walkthroughs'][number] {
  return (
    isRecord(value) &&
    typeof value.title === 'string' &&
    typeof value.source_file === 'string' &&
    typeof value.snippet === 'string' &&
    isStringArray(value.notes)
  )
}

function isTutorialFaqEntry(
  value: unknown,
): value is AnalysisResult['tutorial_summary']['faq_entries'][number] {
  return isRecord(value) && typeof value.question === 'string' && typeof value.answer === 'string'
}

function isAgentExecutionNode(
  value: unknown,
): value is NonNullable<AnalysisResult['agent_metadata']>['execution_nodes'][number] {
  return (
    isRecord(value) &&
    typeof value.node === 'string' &&
    typeof value.stage === 'string' &&
    typeof value.kind === 'string' &&
    typeof value.status === 'string' &&
    isStringArray(value.depends_on) &&
    (value.execution_mode === undefined || typeof value.execution_mode === 'string') &&
    (value.reason === undefined || value.reason === null || typeof value.reason === 'string')
  )
}

function isAgentMetadata(value: unknown): value is NonNullable<AnalysisResult['agent_metadata']> {
  return (
    isRecord(value) &&
    typeof value.enabled === 'boolean' &&
    isStringArray(value.used_roles) &&
    isStringArray(value.fallbacks) &&
    isRecordArray(value.execution_nodes, isAgentExecutionNode)
  )
}

export function isTaskState(value: unknown): value is TaskState {
  return typeof value === 'string' && taskStates.includes(value as TaskState)
}

export function isPendingTaskState(value: unknown): value is PendingTaskState {
  return typeof value === 'string' && pendingTaskStates.includes(value as PendingTaskState)
}

export function isFailedTaskState(value: unknown): value is FailedTaskState {
  return typeof value === 'string' && failedTaskStates.includes(value as FailedTaskState)
}

export function isTaskStage(value: unknown): value is TaskStage {
  return typeof value === 'string' && taskStages.includes(value as TaskStage)
}

export function isTaskKnowledgeState(value: unknown): value is TaskKnowledgeState {
  return typeof value === 'string' && taskKnowledgeStates.includes(value as TaskKnowledgeState)
}

export function isAnalysisTaskResponse(value: unknown): value is AnalysisTaskResponse {
  return (
    isRecord(value) &&
    typeof value.task_id === 'string' &&
    typeof value.status_url === 'string' &&
    typeof value.result_url === 'string' &&
    typeof value.stream_url === 'string' &&
    typeof value.task_token === 'string'
  )
}

export function isTaskChatHistory(value: unknown): value is TaskChatHistory {
  return isRecord(value) && typeof value.task_id === 'string' && isRecordArray(value.messages, isTaskChatMessage)
}

export function isTaskChatExchange(value: unknown): value is TaskChatExchange {
  return (
    isRecord(value) &&
    typeof value.task_id === 'string' &&
    isTaskChatMessage(value.user_message) &&
    isTaskChatMessage(value.assistant_message)
  )
}

export function isTaskStatus(value: unknown): value is TaskStatus {
  return (
    isRecord(value) &&
    typeof value.task_id === 'string' &&
    isTaskState(value.state) &&
    (value.stage === null || isTaskStage(value.stage)) &&
    typeof value.progress === 'number' &&
    isNullableString(value.message) &&
    isNullableString(value.error) &&
    (value.knowledge_state === undefined || value.knowledge_state === null || isTaskKnowledgeState(value.knowledge_state)) &&
    (value.knowledge_error === undefined || isNullableString(value.knowledge_error)) &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string'
  )
}

export function isTaskListItem(value: unknown): value is TaskListItem {
  return (
    isTaskStatus(value) &&
    isRecord(value) &&
    (value.github_url === undefined || isNullableString(value.github_url))
  )
}

export function isTaskListPage(value: unknown): value is TaskListPage {
  return (
    isRecord(value) &&
    isRecordArray(value.tasks, isTaskListItem) &&
    isNumber(value.total) &&
    isNumber(value.limit) &&
    isNumber(value.offset)
  )
}

export function isAnalysisResult(value: unknown): value is AnalysisResult {
  return (
    isRecord(value) &&
    typeof value.github_url === 'string' &&
    typeof value.repo_path === 'string' &&
    typeof value.markdown_path === 'string' &&
    typeof value.html_path === 'string' &&
    typeof value.pdf_path === 'string' &&
    isRepositorySummary(value.repo_summary) &&
    isRecord(value.detected_stack) &&
    isStringArray(value.detected_stack.frameworks) &&
    isStringArray(value.detected_stack.languages) &&
    isRecord(value.backend_summary) &&
    isRecordArray(value.backend_summary.routes, isBackendRouteSummary) &&
    isRecord(value.frontend_summary) &&
    (value.frontend_summary.framework === null || typeof value.frontend_summary.framework === 'string') &&
    (value.frontend_summary.bundler === null || typeof value.frontend_summary.bundler === 'string') &&
    (value.frontend_summary.state_manager === null || typeof value.frontend_summary.state_manager === 'string') &&
    isRecordArray(value.frontend_summary.routing, isFrontendRouteSummary) &&
    isRecordArray(value.frontend_summary.api_calls, isFrontendApiCallSummary) &&
    isRecordArray(value.frontend_summary.state_units, isFrontendStateUnitSummary) &&
    isRecordArray(value.frontend_summary.components, isFrontendComponentSummary) &&
    isRecord(value.deploy_summary) &&
    isRecordArray(value.deploy_summary.services, isDeployServiceSummary) &&
    isStringArray(value.deploy_summary.environment_files) &&
    isStringArray(value.deploy_summary.manifests) &&
    (value.deploy_summary.environment_variables === undefined ||
      isRecordArray(value.deploy_summary.environment_variables, isEnvironmentVariableSummary)) &&
    (value.deploy_summary.kubernetes_resources === undefined ||
      isRecordArray(value.deploy_summary.kubernetes_resources, isKubernetesResourceSummary)) &&
    isRecord(value.logic_summary) &&
    isRecordArray(value.logic_summary.flows, isLogicFlowSummary) &&
    isRecord(value.tutorial_summary) &&
    typeof value.tutorial_summary.mental_model === 'string' &&
    isStringArray(value.tutorial_summary.request_lifecycle) &&
    isStringArray(value.tutorial_summary.run_steps) &&
    isStringArray(value.tutorial_summary.pitfalls) &&
    isStringArray(value.tutorial_summary.next_steps) &&
    isStringArray(value.tutorial_summary.self_check_questions) &&
    isRecordArray(value.tutorial_summary.faq_entries, isTutorialFaqEntry) &&
    isRecordArray(value.tutorial_summary.code_walkthroughs, isTutorialCodeWalkthrough) &&
    isRecord(value.critique_summary) &&
    isStringArray(value.critique_summary.coverage_notes) &&
    isStringArray(value.critique_summary.inferred_sections) &&
    isStringArray(value.critique_summary.missing_areas) &&
    isRecord(value.mermaid_sections) &&
    typeof value.mermaid_sections.system === 'string' &&
    (value.agent_metadata === undefined || isAgentMetadata(value.agent_metadata))
  )
}

export function isTaskStreamEvent(value: unknown): value is TaskStreamEvent {
  if (!isRecord(value)) {
    return false
  }

  const keys = Object.keys(value)
  if (keys.length === 0 || keys.some((key) => !taskStreamEventKeys.includes(key as (typeof taskStreamEventKeys)[number]))) {
    return false
  }

  return (
    (value.state === undefined || isTaskState(value.state)) &&
    (value.stage === undefined || isTaskStage(value.stage)) &&
    (value.progress === undefined || typeof value.progress === 'number') &&
    (value.node === undefined || typeof value.node === 'string') &&
    (value.message === undefined || typeof value.message === 'string') &&
    (value.error === undefined || typeof value.error === 'string') &&
    (value.knowledge_state === undefined || isTaskKnowledgeState(value.knowledge_state)) &&
    (value.knowledge_error === undefined || typeof value.knowledge_error === 'string')
  )
}

export function isAuditEvent(value: unknown): value is AuditEvent {
  return (
    isRecord(value) &&
    typeof value.action === 'string' &&
    typeof value.outcome === 'string' &&
    (value.request_id === undefined || isNullableString(value.request_id)) &&
    (value.method === undefined || typeof value.method === 'string') &&
    (value.path === undefined || typeof value.path === 'string') &&
    (value.client_ip === undefined || typeof value.client_ip === 'string') &&
    (value.task_id === undefined || typeof value.task_id === 'string') &&
    (value.subject === undefined || typeof value.subject === 'string') &&
    (value.github_url === undefined || typeof value.github_url === 'string') &&
    (value.artifact_kind === undefined || typeof value.artifact_kind === 'string') &&
    (value.required_scopes === undefined || isStringArray(value.required_scopes))
  )
}

export function isAuditEventsPage(value: unknown): value is AuditEventsPage {
  return (
    isRecord(value) &&
    isRecordArray(value.events, isAuditEvent) &&
    isNumber(value.total) &&
    isNumber(value.limit) &&
    isNumber(value.offset)
  )
}

export function isMetricsSnapshot(value: unknown): value is MetricsSnapshot {
  return isRecord(value) && Object.values(value).every(isNumber)
}
