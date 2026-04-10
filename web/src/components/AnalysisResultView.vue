<script setup lang="ts">
import { computed } from 'vue'

import {
  formatBooleanZh,
  formatExecutionModeZh,
  formatFallbackTextZh,
  formatTaskStateZh,
} from '../presentation/copy'
import { buildTaskArtifactUrl, downloadTaskArtifact } from '../services/api'
import { getAccessToken } from '../services/authSession'
import type { AnalysisResult } from '../types/contracts'

import ResultSectionCard from './ResultSectionCard.vue'

const props = defineProps<{
  taskId: string
  result: AnalysisResult
}>()

type AgentExecutionNode = NonNullable<NonNullable<AnalysisResult['agent_metadata']>['execution_nodes'][number]>

const usedRolesText = computed(() => props.result.agent_metadata?.used_roles.join(', ') || '无')
const fallbackRolesText = computed(() => props.result.agent_metadata?.fallbacks.join(', ') || '无')
const executionNodes = computed(() => props.result.agent_metadata?.execution_nodes ?? [])
const environmentFilesText = computed(() => props.result.deploy_summary.environment_files.join(', ') || '无')
const manifestsText = computed(() => props.result.deploy_summary.manifests.join(', ') || '无')
const tutorialGenerationNode = computed<AgentExecutionNode | null>(
  () => executionNodes.value.find((node) => node.node === 'tutorial_generation') ?? null,
)
const tutorialGenerationStatus = computed(() => {
  const node = tutorialGenerationNode.value
  const metadataFallbacks = props.result.agent_metadata?.fallbacks ?? []
  const usedRoles = props.result.agent_metadata?.used_roles ?? []
  const usedFallback =
    node?.status === 'fallback' ||
    node?.execution_mode === 'fallback' ||
    metadataFallbacks.includes('tutorial_generation')
  const inferredLlmSuccess =
    node === null &&
    props.result.agent_metadata?.enabled === true &&
    usedRoles.includes('tutor') &&
    !metadataFallbacks.includes('tutorial_generation')

  if (usedFallback) {
    return {
      label: '已回退到内置生成',
      reason: node?.reason ?? '',
    }
  }

  if ((node?.execution_mode === 'llm' && node.status === 'completed') || inferredLlmSuccess) {
    return {
      label: '大模型生成',
      reason: '',
    }
  }

  return {
    label: '内置生成',
    reason: '',
  }
})
const artifactLinks = computed(() =>
  [
    {
      key: 'markdown',
      title: 'Markdown 产物路径',
      label: '下载 Markdown',
      path: props.result.markdown_path,
      kind: 'markdown' as const,
    },
    {
      key: 'html',
      title: 'HTML 产物路径',
      label: '下载 HTML',
      path: props.result.html_path,
      kind: 'html' as const,
    },
    {
      key: 'pdf',
      title: 'PDF 产物路径',
      label: '下载 PDF',
      path: props.result.pdf_path,
      kind: 'pdf' as const,
    },
  ].map((artifact) => {
    const href = buildTaskArtifactUrl(props.taskId, artifact.kind)
    const requiresAuthenticatedDownload = getAccessToken().length > 0 && !href.includes('?')
    return {
      ...artifact,
      href,
      requiresAuthenticatedDownload,
    }
  }),
)

async function handleArtifactDownload(kind: 'markdown' | 'html' | 'pdf') {
  await downloadTaskArtifact(props.taskId, kind)
}
</script>

<template>
  <div class="result-grid">
    <ResultSectionCard title="项目概览" eyebrow="仓库">
      <p>{{ result.repo_summary.name }}</p>
      <p>{{ result.github_url }}</p>
      <p>{{ result.repo_summary.file_count }} 个文件已扫描</p>
    </ResultSectionCard>

    <ResultSectionCard title="识别到的技术栈" eyebrow="技术栈">
      <ul>
        <li v-for="framework in result.detected_stack.frameworks" :key="framework">{{ framework }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="后端分析" eyebrow="路由">
      <ul>
        <li v-for="route in result.backend_summary.routes" :key="`${route.method}-${route.path}`">
          {{ route.method }} {{ route.path }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="前端分析" eyebrow="调用">
      <p>框架：{{ formatFallbackTextZh(result.frontend_summary.framework) }}</p>
      <p>构建工具：{{ formatFallbackTextZh(result.frontend_summary.bundler) }}</p>
      <p>状态管理：{{ formatFallbackTextZh(result.frontend_summary.state_manager) }}</p>
      <ul>
        <li v-for="unit in result.frontend_summary.state_units" :key="`${unit.source_file}-${unit.name}`">
          {{ unit.name }}
        </li>
        <li v-for="component in result.frontend_summary.components" :key="component.source_file">
          {{ component.name }}
        </li>
        <li v-for="call in result.frontend_summary.api_calls" :key="`${call.source_file}-${call.url}`">
          {{ call.url }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="核心逻辑链路" eyebrow="推断">
      <ul>
        <li v-for="flow in result.logic_summary.flows" :key="`${flow.frontend_call}-${flow.backend_route}`">
          {{ flow.frontend_call }} -> {{ flow.backend_method }} {{ flow.backend_route }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="部署分析" eyebrow="基础设施">
      <p>环境变量文件：{{ environmentFilesText }}</p>
      <p>Kubernetes 清单：{{ manifestsText }}</p>
      <ul>
        <li v-for="service in result.deploy_summary.services" :key="`${service.source_file}-${service.name}`">
          {{ service.name }}<span v-if="service.depends_on?.length"> 依赖 {{ service.depends_on.join(', ') }}</span>
        </li>
        <li
          v-for="variable in result.deploy_summary.environment_variables ?? []"
          :key="`${variable.source_file}-${variable.key}`"
        >
          {{ variable.key }}
        </li>
        <li
          v-for="resource in result.deploy_summary.kubernetes_resources ?? []"
          :key="`${resource.source_file}-${resource.kind}-${resource.name}`"
        >
          {{ resource.kind }} {{ resource.name }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="新手学习指南" eyebrow="导师">
      <p>{{ result.tutorial_summary.mental_model }}</p>
      <div class="tutorial-generation-status">
        <h4>教程生成状态</h4>
        <p>{{ tutorialGenerationStatus.label }}</p>
        <p v-if="tutorialGenerationStatus.reason">{{ tutorialGenerationStatus.reason }}</p>
      </div>
      <h4>请求生命周期</h4>
      <ul>
        <li v-for="step in result.tutorial_summary.request_lifecycle" :key="step">{{ step }}</li>
      </ul>
      <h4>运行步骤</h4>
      <ul>
        <li v-for="step in result.tutorial_summary.run_steps" :key="step">{{ step }}</li>
      </ul>
      <h4>常见陷阱</h4>
      <ul>
        <li v-for="pitfall in result.tutorial_summary.pitfalls" :key="pitfall">{{ pitfall }}</li>
      </ul>
      <h4>代码走读</h4>
      <ul>
        <li
          v-for="walkthrough in result.tutorial_summary.code_walkthroughs"
          :key="`${walkthrough.source_file}-${walkthrough.title}`"
        >
          {{ walkthrough.title }}
        </li>
      </ul>
      <h4>常见问题</h4>
      <ul>
        <li v-for="faq in result.tutorial_summary.faq_entries" :key="faq.question">
          {{ faq.question }}：{{ faq.answer }}
        </li>
      </ul>
      <h4>下一步</h4>
      <ul>
        <li v-for="step in result.tutorial_summary.next_steps" :key="step">{{ step }}</li>
      </ul>
      <h4>自检问题</h4>
      <ul>
        <li v-for="question in result.tutorial_summary.self_check_questions" :key="question">{{ question }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="覆盖说明" eyebrow="评审">
      <ul>
        <li v-for="note in result.critique_summary.coverage_notes" :key="note">{{ note }}</li>
        <li v-for="item in result.critique_summary.inferred_sections" :key="item">{{ item }}</li>
        <li v-for="item in result.critique_summary.missing_areas" :key="item">{{ item }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard v-if="result.agent_metadata" title="代理执行情况" eyebrow="编排">
      <p>已启用：{{ formatBooleanZh(result.agent_metadata.enabled) }}</p>
      <p>使用角色：{{ usedRolesText }}</p>
      <p>兜底角色：{{ fallbackRolesText }}</p>
      <ul>
        <li v-for="node in executionNodes" :key="node.node">
          {{ node.node }}：{{ formatTaskStateZh(node.status) }}（{{ formatExecutionModeZh(node.execution_mode) }}）
          <span v-if="node.reason"> {{ node.reason }}</span>
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard
      v-for="artifact in artifactLinks"
      :key="artifact.key"
      :title="artifact.title"
      eyebrow="产物"
    >
      <button
        v-if="artifact.requiresAuthenticatedDownload"
        type="button"
        data-artifact-button
        class="artifact-link artifact-link--button"
        @click="handleArtifactDownload(artifact.kind)"
      >
        {{ artifact.label }}
      </button>
      <a
        v-else
        :href="artifact.href"
        :download="true"
        data-artifact-link
        class="artifact-link"
      >
        {{ artifact.label }}
      </a>
      <pre>{{ artifact.path }}</pre>
    </ResultSectionCard>

    <ResultSectionCard title="系统图源码" eyebrow="Mermaid">
      <pre>{{ result.mermaid_sections.system }}</pre>
    </ResultSectionCard>
  </div>
</template>

<style scoped>
.artifact-link {
  color: inherit;
  font-weight: 600;
}

.artifact-link--button {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  font: inherit;
}

.tutorial-generation-status {
  margin-bottom: 0.75rem;
}
</style>
