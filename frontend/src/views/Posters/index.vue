<template>
  <div class="posters-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">海报图库</h2>
        <p class="sub">由助手生成的出行攻略海报会保存在这里。</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-empty v-if="!loading && !items.length" description="还没有海报。在助手里生成攻略后，回复「生成海报」即可创建。" />
    <div v-else class="grid" v-loading="loading">
      <div v-for="item in items" :key="item.id" class="card">
        <div class="thumb-wrap">
          <img v-if="previews[item.id]" :src="previews[item.id]" :alt="item.title" class="thumb" />
          <div v-else class="thumb placeholder">加载中…</div>
        </div>
        <div class="meta">
          <div class="title">{{ item.title || '出行攻略' }}</div>
          <div class="muted">{{ item.place || '未知地点' }}</div>
          <div class="muted time">{{ formatTime(item.created_at) }}</div>
        </div>
        <div class="actions">
          <el-button text type="primary" @click="download(item)">下载</el-button>
          <el-button text type="danger" @click="remove(item)">删除</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { posterApi, posterFileUrl, type PosterItem } from '@/api/posters'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const items = ref<PosterItem[]>([])
const loading = ref(false)
const previews = reactive<Record<string, string>>({})

const formatTime = (value?: string) => (value ? String(value).replace('T', ' ').slice(0, 19) : '-')

const loadPreview = async (item: PosterItem) => {
  if (!item.id || previews[item.id]) return
  try {
    const resp = await fetch(posterFileUrl(item.id), {
      headers: { Authorization: `Bearer ${authStore.token || ''}` }
    })
    if (!resp.ok) return
    const blob = await resp.blob()
    previews[item.id] = URL.createObjectURL(blob)
  } catch {
    /* ignore */
  }
}

const load = async () => {
  loading.value = true
  try {
    const res = await posterApi.list()
    items.value = res.data?.items || []
    for (const item of items.value) loadPreview(item)
  } finally {
    loading.value = false
  }
}

const download = async (item: PosterItem) => {
  if (!item.id) return
  if (!previews[item.id]) await loadPreview(item)
  const url = previews[item.id]
  if (!url) {
    ElMessage.error('海报加载失败')
    return
  }
  const a = document.createElement('a')
  a.href = url
  a.download = `${item.title || 'poster'}.png`
  a.click()
}

const remove = async (item: PosterItem) => {
  if (!item.id) return
  await ElMessageBox.confirm(`确定删除海报「${item.title || '出行攻略'}」吗？`, '删除海报')
  await posterApi.remove(item.id)
  if (previews[item.id]) URL.revokeObjectURL(previews[item.id])
  delete previews[item.id]
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped lang="scss">
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  overflow: hidden;
  background: var(--el-bg-color);
}
.thumb-wrap { background: var(--el-fill-color-light); }
.thumb {
  width: 100%;
  aspect-ratio: 1080 / 1520;
  object-fit: cover;
  display: block;
}
.placeholder {
  aspect-ratio: 1080 / 1520;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
}
.meta { padding: 12px; }
.title { font-weight: 600; margin-bottom: 4px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.time { margin-top: 4px; }
.actions { display: flex; gap: 8px; padding: 0 12px 12px; }
</style>
