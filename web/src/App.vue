<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

import { clearAccessToken, getAccessToken, isAccessTokenManagedByEnv, setAccessToken } from './services/authSession'

const tokenInput = ref(getAccessToken())
const tokenManagedByEnv = computed(() => isAccessTokenManagedByEnv())
const tokenStatus = computed(() => {
  if (tokenManagedByEnv.value) {
    return 'Access token comes from VITE_ACCESS_TOKEN.'
  }
  return tokenInput.value.trim() ? 'Access token stored in this browser session.' : 'No access token saved.'
})

function persistAccessToken() {
  setAccessToken(tokenInput.value)
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
      <p class="app-shell__eyebrow">Engineering Workbench</p>
      <h1 data-testid="app-title">GitHub Tech Doc Generator</h1>
      <nav class="app-shell__nav" aria-label="Primary">
        <RouterLink class="app-shell__link" to="/">Submit</RouterLink>
        <RouterLink class="app-shell__link" to="/admin">Admin</RouterLink>
      </nav>
      <section class="app-shell__auth panel">
        <div class="app-shell__auth-copy">
          <p class="app-shell__auth-title">Access Token</p>
          <p class="app-shell__auth-text">{{ tokenStatus }}</p>
        </div>
        <div class="app-shell__auth-controls">
          <input
            v-model="tokenInput"
            type="password"
            placeholder="Paste bearer token"
            :disabled="tokenManagedByEnv"
          >
          <button type="button" :disabled="tokenManagedByEnv" @click="persistAccessToken">Save token</button>
          <button type="button" :disabled="tokenManagedByEnv" @click="resetAccessToken">Clear</button>
        </div>
      </section>
    </header>
    <main class="app-shell__main">
      <RouterView />
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
