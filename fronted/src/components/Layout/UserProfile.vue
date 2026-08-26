<template>
  <div class="user-profile" :class="{ collapsed: appStore.sidebarCollapsed }">
    <el-dropdown trigger="click" @command="onCommand">
      <div class="profile-info">
        <el-avatar :size="32">{{ authStore.userDisplayName.slice(0, 1) }}</el-avatar>
        <div v-if="!appStore.sidebarCollapsed" class="user-info">
          <div class="username">{{ authStore.userDisplayName }}</div>
          <div class="role">{{ authStore.user?.is_admin ? '管理员' : '用户' }}</div>
        </div>
      </div>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="settings">设置</el-dropdown-item>
          <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

const onCommand = async (command: string) => {
  if (command === 'settings') router.push('/settings')
  if (command === 'logout') {
    await authStore.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  }
}
</script>

<style lang="scss" scoped>
.user-profile { padding: 12px; }
.profile-info {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.username { font-weight: 600; font-size: 13px; }
.role { font-size: 12px; color: var(--el-text-color-secondary); }
.collapsed { text-align: center; }
</style>
