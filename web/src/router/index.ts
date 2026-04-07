import { createRouter, createWebHistory } from 'vue-router'

import AdminPage from '../pages/AdminPage.vue'
import HomePage from '../pages/HomePage.vue'
import TaskDetailPage from '../pages/TaskDetailPage.vue'

export const routes = [
  {
    path: '/',
    name: 'home',
    component: HomePage,
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminPage,
  },
  {
    path: '/tasks/:taskId',
    name: 'task-detail',
    component: TaskDetailPage,
    props: true,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
