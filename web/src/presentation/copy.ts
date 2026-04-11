import type { TaskStage } from '../types/contracts'

const taskStateMap: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  succeeded: '成功',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const stageMap: Record<TaskStage, string> = {
  fetch_repo: '拉取代码',
  scan_tree: '扫描目录',
  detect_stack: '识别栈',
  analyze_backend: '分析后端',
  analyze_frontend: '分析前端',
  build_doc: '生成文档',
  build_knowledge: '构建知识库',
  finalize: '完成',
}

const executionModeMap: Record<string, string> = {
  deterministic: '确定性',
  llm: '大模型',
  fallback: '兜底',
  agent: '助手',
}

export const orderedTaskStages: TaskStage[] = [
  'fetch_repo',
  'scan_tree',
  'detect_stack',
  'analyze_backend',
  'analyze_frontend',
  'build_doc',
  'build_knowledge',
  'finalize',
]

function normalizeFallback(value?: string | null, empty = '无'): string {
  if (value === undefined || value === null) {
    return empty
  }

  const trimmed = value.trim()
  if (trimmed === '') {
    return empty
  }

  const normalized = trimmed.toLowerCase()
  if (normalized === 'none') {
    return empty
  }

  if (normalized === 'unknown') {
    return '未知'
  }

  if (normalized === 'not detected') {
    return '未检测到'
  }

  return value
}

export function formatTaskStateZh(value?: string | null): string {
  const fallback = normalizeFallback(value)
  return value ? taskStateMap[value.trim().toLowerCase()] ?? fallback : fallback
}

export function formatTaskStageZh(value?: string | null): string {
  const fallback = normalizeFallback(value)
  if (!value) {
    return fallback
  }

  const normalized = value.trim().toLowerCase() as TaskStage
  return stageMap[normalized] ?? fallback
}

export function formatExecutionModeZh(value?: string | null): string {
  if (value === undefined || value === null) {
    return '计划中'
  }
  const fallback = normalizeFallback(value)
  return executionModeMap[value.trim().toLowerCase()] ?? fallback
}

export function formatBooleanZh(value: boolean): string {
  return value ? '是' : '否'
}

export function formatFallbackTextZh(value?: string | null): string {
  return normalizeFallback(value)
}
