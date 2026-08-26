<template>
  <div v-if="photo">
    <div class="page-header">
      <el-button @click="router.back()">返回</el-button>
      <div class="ops">
        <el-button @click="reanalyze">重新解析</el-button>
        <el-button type="danger" @click="remove">删除</el-button>
      </div>
    </div>
    <el-row :gutter="20">
      <el-col :md="14">
        <div class="preview">
          <PhotoThumb :id="photo.id" :thumb="false" />
        </div>
      </el-col>
      <el-col :md="10">
        <el-card>
          <h3>{{ photo.vision?.caption || photo.filename }}</h3>
          <p class="muted">{{ photo.filename }} · {{ photo.status }}</p>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="拍摄时间">{{ photo.metadata?.taken_at || '未知' }}</el-descriptions-item>
            <el-descriptions-item label="设备">{{ photo.metadata?.camera || '未知' }}</el-descriptions-item>
            <el-descriptions-item label="GPS">{{ gpsText }}</el-descriptions-item>
            <el-descriptions-item label="地点">{{ photo.geo?.place_name || photo.geo?.city || '未知' }}</el-descriptions-item>
            <el-descriptions-item label="场景">{{ photo.vision?.scene_type || '-' }}</el-descriptions-item>
            <el-descriptions-item label="人数">{{ photo.vision?.people_count ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="情绪">{{ photo.vision?.mood || '-' }}</el-descriptions-item>
          </el-descriptions>
          <div class="tags">
            <el-tag v-for="tag in photo.vision?.tags || []" :key="tag">{{ tag }}</el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { photoApi } from '@/api/photos'
import type { Photo } from '@/types'
import PhotoThumb from '@/components/PhotoThumb.vue'

const route = useRoute()
const router = useRouter()
const photo = ref<Photo | null>(null)
const gpsText = computed(() => {
  const lat = photo.value?.metadata?.lat
  const lng = photo.value?.metadata?.lng
  return lat && lng ? `${lat.toFixed(5)}, ${lng.toFixed(5)}` : '无'
})

const load = async () => {
  const res = await photoApi.get(route.params.id as string)
  photo.value = res.data
}

const reanalyze = async () => {
  await photoApi.analyze(route.params.id as string)
  ElMessage.success('已重新提交给 Agent1')
}

const remove = async () => {
  await ElMessageBox.confirm('确认删除这张照片？', '删除')
  await photoApi.remove(route.params.id as string)
  ElMessage.success('已删除')
  router.push('/gallery')
}

onMounted(load)
</script>

<style scoped>
.ops { margin-left: auto; display: flex; gap: 8px; }
.preview { height: 520px; background: #111; border-radius: 12px; overflow: hidden; }
.muted { color: var(--el-text-color-secondary); }
.tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
</style>
