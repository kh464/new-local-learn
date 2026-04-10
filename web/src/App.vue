<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { RouterLink, RouterView, routeLocationKey } from 'vue-router'

import { clearAccessToken, getAccessToken, isAccessTokenManagedByEnv, setAccessToken } from './services/authSession'

const route = inject(routeLocationKey, null)
const routeKey = computed(() => route?.fullPath ?? 'app-router-view')
const tokenInput = ref(getAccessToken())
const tokenManagedByEnv = computed(() => isAccessTokenManagedByEnv())
const tokenStatus = computed(() => {
  if (tokenManagedByEnv.value) {
    return '访问令牌来自 VITE_ACCESS_TOKEN。'
  }
  return tokenInput.value.trim() ? '访问令牌已保存在此浏览器会话。' : '未保存访问令牌。'
})

function persistAccessToken() {
  const trimmedToken = tokenInput.value.trim()
  setAccessToken(trimmedToken)
  tokenInput.value = getAccessToken()
}

function resetAccessToken() {
  clearAccessToken()
  tokenInput.value = getAccessToken()
}
</script>

<template>
  <div class="app-shell">
    <header class="app-shell__header">
      <p class="app-shell__eyebrow">工程工作台</p>
      <h1 data-testid="app-title">GitHub 技术文档生成器</h1>
      <nav class="app-shell__nav" aria-label="主要导航">
        <RouterLink class="app-shell__link" to="/">提交任务</RouterLink>
        <RouterLink class="app-shell__link" to="/admin">管理台</RouterLink>
      </nav>
      <section class="app-shell__auth panel">
        <div class="app-shell__auth-copy">
          <p class="app-shell__auth-title">访问令牌</p>
          <p class="app-shell__auth-text">{{ tokenStatus }}</p>
        </div>
        <div class="app-shell__auth-controls">
          <input
            v-model="tokenInput"
            type="password"
            placeholder="粘贴访问令牌"
            :disabled="tokenManagedByEnv"
          >
          <button type="button" :disabled="tokenManagedByEnv" @click="persistAccessToken">保存令牌</button>
          <button type="button" :disabled="tokenManagedByEnv" @click="resetAccessToken">清除</button>
        </div>
      </section>
    </header>
    <main class="app-shell__main">
      <RouterView :key="routeKey" />
    </main>
  </div>
</template>

<style scoped>
.app-shell__nav {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.app-shell__auth {
  margin-top: 18px;
  display: grid;
  gap: 12px;
}

.app-shell__auth-copy,
.app-shell__auth-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.app-shell__auth-title,
.app-shell__auth-text {
  margin: 0;
}

.app-shell__auth-title {
  font-weight: 700;
}

.app-shell__auth-text {
  color: var(--muted);
}

.app-shell__auth-controls input,
.app-shell__auth-controls button {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  font: inherit;
}

.app-shell__auth-controls input {
  min-width: min(360px, 100%);
}

.app-shell__link {
  color: var(--accent-strong);
  font-weight: 600;
  text-decoration: none;
}

.app-shell__link.router-link-active {
  text-decoration: underline;
  text-underline-offset: 4px;
}
</style>
