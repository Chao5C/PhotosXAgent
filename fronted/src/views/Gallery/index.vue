<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">图库</h2>
        <p class="sub">上传照片后，Agent1 会提取 EXIF 并识别内容、打标签。</p>
      </div>
      <el-upload :show-file-list="false" :http-request="onUpload" multiple accept="image/*">
        <el-button type="primary" :loading="uploading">上传图片</el-button>
      </el-upload>
    </div>

    <div class="filters">
      <el-input v-model="query" placeholder="搜索地点 / 标签 / 描述" clearable style="width: 260px" @keyup.enter="load" />
      <el-select v-model="scene" placeholder="场景" clearable style="width: 140px" @change="load">
        <el-option label="合照" value="group" />
        <el-option label="宠物" value="pet" />
        <el-option label="风景" value="scenery" />
        <el-option label="美食" value="food" />
        <el-option label="建筑" value="architecture" />
      </el-select>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-empty v-if="!loading && photos.length === 0" description="还没有照片，先上传几张吧" />
    <div v-else class="grid">
      <div v-for="photo in photos" :key="photo.id" class="card" @click="router.push(`/photo/${photo.id}`)">
        <div class="thumb">
          <PhotoThumb :id="photo.id" />
          <el-tag v-if="photo.status !== 'ready'" size="small" class="status" type="warning">{{ statusText(photo.status) }}</el-tag>
        </div>
        <div class="meta">
          <div class="caption">{{ photo.vision?.caption || photo.filename }}</div>
          <div class="tags">
            <el-tag v-for="tag in (photo.vision?.tags || []).slice(0, 3)" :key="tag" size="small">{{ tag }}</el-tag>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { photoApi } from '@/api/photos'
import type { Photo } from '@/types'
import PhotoThumb from '@/components/PhotoThumb.vue'

const router = useRouter()
const photos = ref<Photo[]>([])
const query = ref('')
const scene = ref('')
const loading = ref(false)
const uploading = ref(false)
let timer: number | undefined

const statusText = (status: string) => ({ pending: '排队中', analyzing: '识别中', failed: '失败' }[status] || status)

const load = async () => {
  loading.value = true
  const res = await photoApi.list({ q: query.value || undefined, scene: scene.value || undefined })
  photos.value = res.data.items || []
  loading.value = false
}

const onUpload = async (options: UploadRequestOptions) => {
  uploading.value = true
  try {
    await photoApi.upload([options.file as File])
    ElMessage.success('已上传，正在由 Agent1 解析')
    await load()
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 8000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped lang="scss">
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.filters { display: flex; gap: 12px; margin-bottom: 16px; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
.card {
  background: var(--el-bg-color);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
}
.thumb { height: 180px; position: relative; }
.status { position: absolute; top: 8px; left: 8px; }
.meta { padding: 10px; }
.caption {
  font-size: 13px;
  height: 36px;
  overflow: hidden;
}
.tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
</style>
