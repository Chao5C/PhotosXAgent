<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">推荐与建议</h2>
        <p class="sub">Agent2 会在检测到较远新地点时，结合天气给出建议。</p>
      </div>
      <el-button @click="readAll" :disabled="!unread">全部已读</el-button>
    </div>
    <el-empty v-if="items.length === 0" description="暂无推荐。上传带定位的远距离照片后，Agent2 会在这里推送。" />
    <el-card v-for="item in items" :key="item.id" class="rec" :class="{ unread: !item.read }">
      <div class="row">
        <el-tag :type="item.priority === 'high' ? 'danger' : 'info'">{{ item.type }}</el-tag>
        <span class="time">{{ item.created_at }}</span>
      </div>
      <h3>{{ item.title }}</h3>
      <p>{{ item.body }}</p>
      <p v-if="item.weather_brief" class="weather">{{ item.weather_brief }}</p>
      <el-button v-if="!item.read" text type="primary" @click="mark(item.id)">标记已读</el-button>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { recApi } from '@/api/photos'
import type { Recommendation } from '@/types'

const items = ref<Recommendation[]>([])
const unread = computed(() => items.value.some((i) => !i.read))

const load = async () => {
  const res = await recApi.list()
  items.value = res.data.items || []
}

const mark = async (id: string) => {
  await recApi.read(id)
  await load()
}

const readAll = async () => {
  await recApi.readAll()
  await load()
}

onMounted(load)
</script>

<style scoped>
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.rec { margin-bottom: 12px; }
.unread { border-left: 4px solid var(--el-color-primary); }
.row { display: flex; justify-content: space-between; margin-bottom: 8px; }
.time, .weather { color: var(--el-text-color-secondary); font-size: 13px; }
</style>
