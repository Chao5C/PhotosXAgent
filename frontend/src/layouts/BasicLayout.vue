<template>
  <div class="basic-layout">
    <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }" :style="{ width: appStore.actualSidebarWidth + 'px' }">
      <div class="sidebar-header">
        <div class="logo">
          <img src="/logo.svg" alt="PhotosXAgent" />
          <span v-show="!appStore.sidebarCollapsed" class="logo-text">PhotosXAgent</span>
        </div>
      </div>
      <nav class="sidebar-nav">
        <SidebarMenu />
      </nav>
      <div class="sidebar-footer">
        <UserProfile />
      </div>
    </aside>
    <div class="main-container" :style="{ marginLeft: appStore.actualSidebarWidth + 'px' }">
      <header class="header">
        <div class="header-left">
          <el-button type="text" class="sidebar-toggle" @click="appStore.toggleSidebar()">
            <el-icon><Expand v-if="appStore.sidebarCollapsed" /><Fold v-else /></el-icon>
          </el-button>
          <span class="page-heading">{{ route.meta.title || 'PhotosXAgent' }}</span>
        </div>
        <div class="header-right">
          <el-tooltip content="切换主题">
            <el-button type="text" @click="appStore.toggleTheme()">
              <el-icon><Sunny v-if="appStore.isDarkTheme" /><Moon v-else /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </header>
      <main class="main-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import SidebarMenu from '@/components/Layout/SidebarMenu.vue'
import UserProfile from '@/components/Layout/UserProfile.vue'
import { Expand, Fold, Sunny, Moon } from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()
</script>

<style lang="scss" scoped>
.basic-layout {
  min-height: 100vh;
  background: var(--el-bg-color-page);
}
.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  z-index: 1000;
  transition: width 0.25s ease;
}
.sidebar-header {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
    img { width: 32px; height: 32px; }
    .logo-text { font-weight: 700; white-space: nowrap; }
  }
}
.sidebar-nav { flex: 1; overflow: auto; padding: 8px 0; }
.sidebar-footer { border-top: 1px solid var(--el-border-color-lighter); }
.main-container { min-height: 100vh; display: flex; flex-direction: column; }
.header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  position: sticky;
  top: 0;
  z-index: 10;
}
.header-left, .header-right { display: flex; align-items: center; gap: 8px; }
.page-heading { font-weight: 600; }
.main-content { padding: 24px; max-width: 1400px; width: 100%; margin: 0 auto; }
</style>
