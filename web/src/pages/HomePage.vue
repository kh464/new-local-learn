<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import RepositorySubmitForm from '../components/RepositorySubmitForm.vue'
import { createAnalysisTask } from '../services/api'

const router = useRouter()
const githubUrl = ref('')
const pending = ref(false)
const error = ref<string | null>(null)

async function handleSubmit() {
  const cleanedUrl = githubUrl.value.trim()
  if (pending.value || cleanedUrl.length === 0) {
    return
  }

  pending.value = true
  error.value = null

  try {
    const task = await createAnalysisTask(cleanedUrl)
    await router.push(`/tasks/${task.task_id}`)
  } catch (submissionError) {
    if (submissionError instanceof Error) {
      error.value = submissionError.message
    } else {
      error.value = '出现问题，请重试。'
    }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <section class="home-hero">
    <div class="home-hero__panel">
      <p class="home-hero__eyebrow">提交仓库以启动分析</p>
      <h2 class="home-hero__title">将 GitHub 项目转化为实时技术简报。</h2>
      <p class="home-hero__subtitle">
        粘贴仓库 URL，工作台会生成架构、流程以及实现细节的结构化概览。
      </p>
      <RepositorySubmitForm v-model="githubUrl" :pending="pending" @submit="handleSubmit" />
      <p v-if="error" class="home-hero__error" role="alert">{{ error }}</p>
    </div>
  </section>
</template>

<style scoped>
.home-hero {
  display: grid;
  place-items: center;
  padding: 24px 0 48px;
}

.home-hero__panel {
  width: min(720px, 100%);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 32px;
  box-shadow: var(--shadow);
  display: grid;
  gap: 16px;
}

.home-hero__eyebrow {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--accent-strong);
}

.home-hero__title {
  margin: 0;
  font-size: clamp(24px, 3vw, 32px);
}

.home-hero__subtitle {
  margin: 0;
  color: var(--muted);
}

.home-hero__error {
  margin: 0;
  color: var(--danger);
  font-weight: 600;
}
@media (max-width: 600px) {
  .home-hero__panel {
    padding: 24px;
  }
}
</style>
