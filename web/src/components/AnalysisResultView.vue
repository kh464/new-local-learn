<script setup lang="ts">
import { computed } from 'vue'

import { buildTaskArtifactUrl, downloadTaskArtifact } from '../services/api'
import { getAccessToken } from '../services/authSession'
import type { AnalysisResult } from '../types/contracts'

import ResultSectionCard from './ResultSectionCard.vue'

const props = defineProps<{
  taskId: string
  result: AnalysisResult
}>()

const usedRolesText = computed(() => props.result.agent_metadata?.used_roles.join(', ') || 'none')
const fallbackRolesText = computed(() => props.result.agent_metadata?.fallbacks.join(', ') || 'none')
const executionNodes = computed(() => props.result.agent_metadata?.execution_nodes ?? [])
const artifactLinks = computed(() =>
  [
    {
      key: 'markdown',
      title: 'Markdown Artifact Path',
      label: 'Download Markdown',
      path: props.result.markdown_path,
      kind: 'markdown' as const,
    },
    {
      key: 'html',
      title: 'HTML Artifact Path',
      label: 'Download HTML',
      path: props.result.html_path,
      kind: 'html' as const,
    },
    {
      key: 'pdf',
      title: 'PDF Artifact Path',
      label: 'Download PDF',
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
    <ResultSectionCard title="Project Overview" eyebrow="Repository">
      <p>{{ result.repo_summary.name }}</p>
      <p>{{ result.github_url }}</p>
      <p>{{ result.repo_summary.file_count }} files scanned</p>
    </ResultSectionCard>

    <ResultSectionCard title="Detected Tech Stack" eyebrow="Stack">
      <ul>
        <li v-for="framework in result.detected_stack.frameworks" :key="framework">{{ framework }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Backend Analysis" eyebrow="Routes">
      <ul>
        <li v-for="route in result.backend_summary.routes" :key="`${route.method}-${route.path}`">
          {{ route.method }} {{ route.path }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Frontend Analysis" eyebrow="Calls">
      <p>Framework: {{ result.frontend_summary.framework ?? 'unknown' }}</p>
      <p>Bundler: {{ result.frontend_summary.bundler ?? 'unknown' }}</p>
      <p>State Manager: {{ result.frontend_summary.state_manager ?? 'not detected' }}</p>
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

    <ResultSectionCard title="Core Logic Flows" eyebrow="Inference">
      <ul>
        <li v-for="flow in result.logic_summary.flows" :key="`${flow.frontend_call}-${flow.backend_route}`">
          {{ flow.frontend_call }} -> {{ flow.backend_method }} {{ flow.backend_route }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Deploy Analysis" eyebrow="Infra">
      <p>Environment files: {{ result.deploy_summary.environment_files.join(', ') || 'none' }}</p>
      <p>Kubernetes manifests: {{ result.deploy_summary.manifests.join(', ') || 'none' }}</p>
      <ul>
        <li v-for="service in result.deploy_summary.services" :key="`${service.source_file}-${service.name}`">
          {{ service.name }}<span v-if="service.depends_on?.length"> depends on {{ service.depends_on.join(', ') }}</span>
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

    <ResultSectionCard title="Beginner Learning Guide" eyebrow="Tutor">
      <p>{{ result.tutorial_summary.mental_model }}</p>
      <h4>Request Lifecycle</h4>
      <ul>
        <li v-for="step in result.tutorial_summary.request_lifecycle" :key="step">{{ step }}</li>
      </ul>
      <h4>Run Steps</h4>
      <ul>
        <li v-for="step in result.tutorial_summary.run_steps" :key="step">{{ step }}</li>
      </ul>
      <h4>Pitfalls</h4>
      <ul>
        <li v-for="pitfall in result.tutorial_summary.pitfalls" :key="pitfall">{{ pitfall }}</li>
      </ul>
      <h4>Code Walkthroughs</h4>
      <ul>
        <li v-for="walkthrough in result.tutorial_summary.code_walkthroughs" :key="`${walkthrough.source_file}-${walkthrough.title}`">
          {{ walkthrough.title }}
        </li>
      </ul>
      <h4>FAQ</h4>
      <ul>
        <li v-for="faq in result.tutorial_summary.faq_entries" :key="faq.question">
          {{ faq.question }}: {{ faq.answer }}
        </li>
      </ul>
      <h4>Next Steps</h4>
      <ul>
        <li v-for="step in result.tutorial_summary.next_steps" :key="step">{{ step }}</li>
      </ul>
      <h4>Self-Check</h4>
      <ul>
        <li v-for="question in result.tutorial_summary.self_check_questions" :key="question">{{ question }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Coverage Notes" eyebrow="Critic">
      <ul>
        <li v-for="note in result.critique_summary.coverage_notes" :key="note">{{ note }}</li>
        <li v-for="item in result.critique_summary.inferred_sections" :key="item">{{ item }}</li>
        <li v-for="item in result.critique_summary.missing_areas" :key="item">{{ item }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard v-if="result.agent_metadata" title="Agent Execution" eyebrow="Orchestrator">
      <p>Enabled: {{ result.agent_metadata.enabled ? 'yes' : 'no' }}</p>
      <p>Used Roles: {{ usedRolesText }}</p>
      <p>Fallbacks: {{ fallbackRolesText }}</p>
      <ul>
        <li v-for="node in executionNodes" :key="node.node">
          {{ node.node }}: {{ node.status }} ({{ node.execution_mode ?? 'planned' }})
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard
      v-for="artifact in artifactLinks"
      :key="artifact.key"
      :title="artifact.title"
      eyebrow="Artifact"
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

    <ResultSectionCard title="System Diagram Source" eyebrow="Mermaid">
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
</style>
