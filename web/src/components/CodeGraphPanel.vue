<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { fetchTaskGraph } from '../services/graphApi'
import type {
  TaskGraphEdgePayload,
  TaskGraphNodePayload,
  TaskGraphPayload,
  TaskGraphView,
} from '../types/contracts'

const props = defineProps<{
  taskId: string
  highlightedNodeIds?: string[]
}>()

const emit = defineEmits<{
  (event: 'select-node', nodeIds: string[]): void
}>()

const graph = ref<TaskGraphPayload | null>(null)
const loading = ref(false)
const error = ref('')
const selectedNodeId = ref('')

const linkedNodeIds = computed(() => new Set(props.highlightedNodeIds ?? []))

const selectedNode = computed(() => {
  if (!graph.value) {
    return null
  }
  return graph.value.nodes.find((node) => node.node_id === selectedNodeId.value) ?? graph.value.nodes[0] ?? null
})

const selectedNodeEdges = computed(() => {
  if (!graph.value || !selectedNode.value) {
    return [] as TaskGraphEdgePayload[]
  }
  return graph.value.edges.filter(
    (edge) => edge.from_node_id === selectedNode.value?.node_id || edge.to_node_id === selectedNode.value?.node_id,
  )
})

function describeNodeMeta(node: TaskGraphNodePayload): string[] {
  const lines: string[] = []
  if (node.kind === 'file' && node.file_kind) {
    lines.push(`文件角色：${node.file_kind}`)
  }
  if (node.kind === 'symbol' && node.symbol_kind) {
    lines.push(`符号类型：${node.symbol_kind}`)
  }
  if (node.language) {
    lines.push(`语言：${node.language}`)
  }
  if (node.start_line && node.end_line) {
    lines.push(`代码范围：${node.start_line}-${node.end_line}`)
  }
  if (node.path) {
    lines.push(`文件位置：${node.path}`)
  }
  return lines
}

async function loadGraph(options: { view?: TaskGraphView; symbolId?: string; path?: string } = {}) {
  loading.value = true
  error.value = ''
  try {
    const payload = await fetchTaskGraph(props.taskId, { view: 'repository', ...options })
    graph.value = payload
    selectedNodeId.value = payload.focus_node_id ?? payload.nodes[0]?.node_id ?? ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '代码图谱加载失败。'
    graph.value = null
    selectedNodeId.value = ''
  } finally {
    loading.value = false
  }
}

function handleNodeSelect(nodeId: string) {
  selectedNodeId.value = nodeId
  emit('select-node', [nodeId])
}

async function openRepositoryView() {
  await loadGraph({ view: 'repository' })
}

async function openSymbolView() {
  if (!selectedNode.value || selectedNode.value.kind !== 'symbol') {
    return
  }
  await loadGraph({ view: 'symbol', symbolId: selectedNode.value.node_id })
}

async function openModuleView() {
  if (!selectedNode.value?.path) {
    return
  }
  await loadGraph({ view: 'module', path: selectedNode.value.path })
}

watch(
  () => props.taskId,
  async () => {
    await loadGraph({ view: 'repository' })
  },
  { immediate: true },
)
</script>

<template>
  <section class="code-graph-panel panel">
    <div class="code-graph-panel__header">
      <div>
        <p class="code-graph-panel__eyebrow">代码图谱</p>
        <h3>代码神经网络图</h3>
      </div>
      <p class="code-graph-panel__hint">基于知识库中的文件节点、符号节点和调用边生成。</p>
    </div>

    <p v-if="loading" class="code-graph-panel__status">正在加载代码图谱...</p>
    <p v-else-if="error" class="code-graph-panel__error">{{ error }}</p>

    <div v-else-if="graph" class="code-graph-panel__layout">
      <div class="code-graph-panel__node-list">
        <button
          v-for="node in graph.nodes"
          :key="node.node_id"
          type="button"
          class="code-graph-panel__node"
          :class="{
            'code-graph-panel__node--active': node.node_id === selectedNodeId,
            'code-graph-panel__node--linked': linkedNodeIds.has(node.node_id),
          }"
          :data-testid="`graph-node-${node.node_id}`"
          @click="handleNodeSelect(node.node_id)"
        >
          <span class="code-graph-panel__node-kind">{{ node.kind === 'file' ? '文件' : '符号' }}</span>
          <strong>{{ node.label }}</strong>
        </button>
      </div>

      <div v-if="selectedNode" class="code-graph-panel__details">
        <h4>{{ selectedNode.label }}</h4>
        <p class="code-graph-panel__summary">{{ selectedNode.summary || '暂无中文说明。' }}</p>

        <div class="code-graph-panel__actions">
          <button
            v-if="graph.view !== 'repository'"
            type="button"
            data-testid="graph-back-repository"
            @click="openRepositoryView"
          >
            返回仓库总图
          </button>
          <button
            v-if="selectedNode.kind === 'symbol' && graph.view !== 'symbol'"
            type="button"
            data-testid="graph-open-symbol-view"
            @click="openSymbolView"
          >
            查看符号子图
          </button>
          <button
            v-if="selectedNode.path && graph.view !== 'module'"
            type="button"
            data-testid="graph-open-module-view"
            @click="openModuleView"
          >
            查看模块子图
          </button>
        </div>

        <ul class="code-graph-panel__meta">
          <li v-for="item in describeNodeMeta(selectedNode)" :key="item">{{ item }}</li>
        </ul>

        <div class="code-graph-panel__edges">
          <h5>相关连线</h5>
          <ul class="code-graph-panel__edge-list">
            <li v-for="edge in selectedNodeEdges" :key="`${edge.from_node_id}-${edge.to_node_id}-${edge.kind}-${edge.line ?? 0}`">
              <code>{{ edge.kind }}</code>
              <span>{{ edge.from_node_id }} -> {{ edge.to_node_id }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.code-graph-panel {
  display: grid;
  gap: 16px;
  align-content: start;
}

.code-graph-panel__header,
.code-graph-panel__layout,
.code-graph-panel__details,
.code-graph-panel__edges {
  display: grid;
  gap: 10px;
}

.code-graph-panel__header h3,
.code-graph-panel__eyebrow,
.code-graph-panel__hint,
.code-graph-panel__status,
.code-graph-panel__error,
.code-graph-panel__details h4,
.code-graph-panel__details h5,
.code-graph-panel__summary {
  margin: 0;
}

.code-graph-panel__eyebrow {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-strong);
}

.code-graph-panel__hint,
.code-graph-panel__status,
.code-graph-panel__summary {
  color: var(--muted);
}

.code-graph-panel__error {
  color: var(--danger);
  font-weight: 600;
}

.code-graph-panel__layout {
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 16px;
}

.code-graph-panel__node-list {
  display: grid;
  gap: 8px;
  max-height: 420px;
  overflow: auto;
}

.code-graph-panel__node {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
  cursor: pointer;
}

.code-graph-panel__node--active {
  border-color: rgba(11, 110, 79, 0.48);
  background: rgba(11, 110, 79, 0.08);
}

.code-graph-panel__node--linked {
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.4);
  background: rgba(59, 130, 246, 0.08);
}

.code-graph-panel__node-kind {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.code-graph-panel__details {
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(15, 23, 42, 0.04);
}

.code-graph-panel__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.code-graph-panel__actions button {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.code-graph-panel__meta,
.code-graph-panel__edge-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 18px;
}

.code-graph-panel__edge-list code {
  margin-right: 8px;
}

@media (max-width: 960px) {
  .code-graph-panel__layout {
    grid-template-columns: 1fr;
  }
}
</style>
