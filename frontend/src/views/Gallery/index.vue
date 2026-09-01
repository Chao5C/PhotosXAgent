<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">图库</h2>
        <p class="sub">上传照片后，Agent1 会提取 EXIF 并识别内容、打标签。</p>
      </div>
      <div class="header-ops">
        <el-button :loading="requeueing" @click="requeueFailed">重新解析未完成</el-button>
        <el-upload :show-file-list="false" :http-request="onUpload" multiple accept="image/*">
          <el-button type="primary" :loading="uploading">上传图片</el-button>
        </el-upload>
      </div>
    </div>

    <div v-if="selected.length" class="batch-bar">
      <span>已选 {{ selected.length }} 张</span>
      <el-button size="small" :loading="batchAnalyzing" @click="batchReanalyze">重新解析</el-button>
      <el-button size="small" type="danger" :loading="batchDeleting" @click="batchDelete">删除</el-button>
      <el-button size="small" text @click="clearSelection">取消选择</el-button>
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
      <el-checkbox
        v-model="selectAll"
        :indeterminate="indeterminate"
        @change="(val: string | number | boolean) => toggleSelectAll(!!val)"
      >
        全选
      </el-checkbox>
    </div>

    <el-empty v-if="!loading && photos.length === 0" description="还没有照片，先上传几张吧" />
    <div v-else class="grid">
      <div
        v-for="photo in photos"
        :key="photo.id"
        class="card"
        :class="{ selected: isSelected(photo.id) }"
        @click="openPhoto(photo.id)"
      >
        <div class="thumb">
          <PhotoThumb v-if="photo.id" :id="photo.id" />
          <div class="select-box" @click.stop>
            <el-checkbox
              :model-value="isSelected(photo.id)"
              @change="(val: string | number | boolean) => toggleSelect(photo.id, !!val)"
            />
          </div>
          <el-tag v-if="photo.status !== 'ready'" size="small" class="status" :type="statusType(photo.status)">
            {{ statusText(photo.status) }}
          </el-tag>
        </div>
        <div class="meta">
          <div class="caption">{{ displayCaption(photo) }}</div>
          <div class="tags">
            <el-tag v-for="tag in (photo.vision?.tags || []).slice(0, 3)" :key="tag" size="small">{{ tag }}</el-tag>
          </div>
        </div>
      </div>
    </div>

    <ParseQueuePanel :queue="queue" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { photoApi } from '@/api/photos'
import type { ParseQueue, Photo } from '@/types'
import PhotoThumb from '@/components/PhotoThumb.vue'
import ParseQueuePanel from '@/components/ParseQueuePanel.vue'

const router = useRouter()
const photos = ref<Photo[]>([])
const queue = ref<ParseQueue | null>(null)
const query = ref('')
const scene = ref('')
const loading = ref(false)
const uploading = ref(false)
const requeueing = ref(false)
const batchDeleting = ref(false)
const batchAnalyzing = ref(false)
const selected = ref<string[]>([])
const selectAll = ref(false)
let timer: number | undefined

const pollMs = computed(() => ((queue.value?.active || 0) > 0 ? 3000 : 8000))

const validPhotos = computed(() => photos.value.filter((p) => isValidId(p.id)))

const indeterminate = computed(() => {
  const n = selected.value.length
  return n > 0 && n < validPhotos.value.length
})

const isValidId = (id?: string) => !!id && id !== 'undefined' && /^[a-f0-9]{24}$/i.test(id)

const statusText = (status: string) =>
  ({ pending: '排队中', analyzing: '识别中', failed: '失败', ready: '已完成' }[status] || status)

const statusType = (status: string) =>
  ({ pending: 'info', analyzing: 'warning', failed: 'danger', ready: 'success' }[status] || 'info')

const FALLBACK_CAPTION = '已提取拍摄信息，视觉模型未配置或调用失败。'

const displayCaption = (photo: Photo) => {
  const ai = photo.vision?.caption?.trim()
  if (ai && ai !== FALLBACK_CAPTION) return ai
  return photo.user_description || photo.filename
}

const isSelected = (id?: string) => !!id && selected.value.includes(id)

const toggleSelect = (id: string | undefined, checked: boolean) => {
  if (!isValidId(id)) return
  if (checked) {
    if (!selected.value.includes(id!)) selected.value.push(id!)
  } else {
    selected.value = selected.value.filter((item) => item !== id)
  }
}

const toggleSelectAll = (checked: boolean) => {
  selectAll.value = checked
  selected.value = checked ? validPhotos.value.map((p) => p.id) : []
}

const clearSelection = () => {
  selected.value = []
  selectAll.value = false
}

const openPhoto = (id?: string) => {
  if (!isValidId(id)) return
  router.push(`/photo/${id}`)
}

const loadQueue = async () => {
  const res = await photoApi.parseQueue()
  queue.value = res.data
}

const load = async () => {
  loading.value = true
  const res = await photoApi.list({ q: query.value || undefined, scene: scene.value || undefined })
  photos.value = res.data.items || []
  selected.value = selected.value.filter((id) => photos.value.some((p) => p.id === id))
  await loadQueue()
  loading.value = false
  schedulePoll()
}

const schedulePoll = () => {
  if (timer) window.clearInterval(timer)
  timer = window.setInterval(load, pollMs.value)
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

const requeueFailed = async () => {
  requeueing.value = true
  try {
    const res = await photoApi.reanalyzeBatch()
    ElMessage.success(res.message || `已提交 ${res.data?.queued || 0} 张照片`)
    await load()
  } finally {
    requeueing.value = false
  }
}

const batchReanalyze = async () => {
  const ids = selected.value.filter(isValidId)
  if (!ids.length) return
  batchAnalyzing.value = true
  try {
    const res = await photoApi.reanalyzeIds(ids)
    ElMessage.success(res.message || `已提交 ${res.data?.queued || 0} 张照片`)
    clearSelection()
    await load()
  } finally {
    batchAnalyzing.value = false
  }
}

const batchDelete = async () => {
  const ids = selected.value.filter(isValidId)
  if (!ids.length) return
  await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 张照片？`, '批量删除')
  batchDeleting.value = true
  try {
    const res = await photoApi.deleteBatch(ids)
    ElMessage.success(res.message || `已删除 ${res.data?.deleted || 0} 张`)
    clearSelection()
    await load()
  } finally {
    batchDeleting.value = false
  }
}

watch(
  () => selected.value.length,
  () => {
    selectAll.value = validPhotos.value.length > 0 && selected.value.length === validPhotos.value.length
  }
)

onMounted(load)
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped lang="scss">
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.header-ops { display: flex; gap: 10px; align-items: center; }
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
}
.filters { display: flex; gap: 12px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  padding-bottom: 120px;
}
.card {
  background: var(--el-bg-color);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}
.thumb { height: 180px; position: relative; }
.select-box {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 2;
  padding: 2px 4px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(4px);
}
.status { position: absolute; top: 8px; right: 8px; }
.meta { padding: 10px; }
.caption {
  font-size: 13px;
  height: 36px;
  overflow: hidden;
}
.tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
</style>
