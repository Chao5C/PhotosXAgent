<template>
  <el-menu :default-active="active" :collapse="appStore.sidebarCollapsed" router class="sidebar-menu">
    <el-menu-item index="/gallery">
      <el-icon><Picture /></el-icon>
      <template #title>图库</template>
    </el-menu-item>
    <el-menu-item index="/albums">
      <el-icon><Collection /></el-icon>
      <template #title>相册</template>
    </el-menu-item>
    <el-menu-item index="/journey">
      <el-icon><MapLocation /></el-icon>
      <template #title>行程模拟</template>
    </el-menu-item>
    <el-menu-item index="/recommendations">
      <el-icon><Bell /></el-icon>
      <template #title>推荐建议</template>
    </el-menu-item>
    <el-menu-item index="/chat">
      <el-icon><ChatDotRound /></el-icon>
      <template #title>助手</template>
    </el-menu-item>
    <el-menu-item index="/studio">
      <el-icon><VideoCamera /></el-icon>
      <template #title>自媒体工作台</template>
    </el-menu-item>
    <el-menu-item index="/settings">
      <el-icon><Setting /></el-icon>
      <template #title>设置</template>
    </el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { Picture, Collection, MapLocation, Bell, ChatDotRound, VideoCamera, Setting } from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()
const active = computed(() => {
  if (route.path.startsWith('/albums')) return '/albums'
  if (route.path.startsWith('/photo')) return '/gallery'
  return route.path
})
</script>

<style scoped>
.sidebar-menu { border-right: none; }
</style>
