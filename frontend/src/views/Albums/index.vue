<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">相册</h2>
        <p class="sub">Agent1 打标签后，系统会按合照、宠物、风景、地点等自动归类。</p>
      </div>
    </div>
    <el-empty v-if="albums.length === 0" description="解析完成后会自动生成相册" />
    <div class="grid">
      <div v-for="album in albums" :key="album.id" class="card" @click="router.push(`/albums/${album.id}`)">
        <div class="cover">
          <PhotoThumb v-if="album.cover_id" :id="album.cover_id" />
        </div>
        <div class="info">
          <div class="name">{{ album.name }}</div>
          <div class="count">{{ album.count }} 张 · {{ kindLabel(album.kind) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { albumApi } from '@/api/photos'
import type { Album } from '@/types'
import PhotoThumb from '@/components/PhotoThumb.vue'

const router = useRouter()
const albums = ref<Album[]>([])
const kindLabel = (kind: string) =>
  ({ group: '合照', pet: '宠物', scenery: '风景', food: '美食', architecture: '建筑', location: '地点合集' }[kind] || kind)

onMounted(async () => {
  const res = await albumApi.list()
  albums.value = res.data || []
})
</script>

<style scoped lang="scss">
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
}
.cover { height: 160px; background: var(--el-fill-color); }
.info { padding: 12px; }
.name { font-weight: 600; }
.count { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 4px; }
</style>
