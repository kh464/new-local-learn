const taskTokens = new Map<string, string>()

export function registerTaskToken(taskId: string, taskToken: string) {
  taskTokens.set(taskId, taskToken)
}

export function getTaskToken(taskId: string): string {
  return taskTokens.get(taskId) ?? ''
}

export function clearTaskTokens() {
  taskTokens.clear()
}
