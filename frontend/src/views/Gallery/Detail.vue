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
          <h3>{{ briefCaption }}</h3>
          <p class="muted">{{ photo.filename }} · {{ photo.status }}</p>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="拍摄时间">{{ photo.metadata?.taken_at || '未知' }}</el-descriptions-item>
            <el-descriptions-item label="设备">{{ photo.metadata?.camera || '未知' }}</el-descriptions-item>
            <el-descriptions-item label="GPS">{{ gpsText }}</el-descriptions-item>
            <el-descriptions-item label="地点">{{ placeText }}</el-descriptions-item>
            <el-descriptions-item label="场景">{{ sceneLabel }}</el-descriptions-item>
            <el-descriptions-item label="人数">{{ photo.vision?.people_count ?? '-' }}</el-descriptions-item>
          </el-descriptions>

          <div class="desc-block">
            <div class="muted">自定义简略描述（可选，留空则使用上方识别结果）</div>
            <el-input
              v-model="captionDraft"
              type="textarea"
              :rows="2"
              placeholder="在此修改简略描述"
            />
          </div>

          <div class="desc-block">
            <el-collapse v-model="longOpen">
              <el-collapse-item name="long">
                <template #title>
                  <span>详细描述（50–100 字，可展开编辑）</span>
                  <el-tag v-if="longPreview" size="small" type="info" style="margin-left: 8px">已生成</el-tag>
                </template>
                <el-input
                  v-model="longDraft"
                  type="textarea"
                  :rows="5"
                  :placeholder="photo.vision?.long_description || '识别完成后显示详细描述'"
                />
              </el-collapse-item>
            </el-collapse>
          </div>

          <el-button type="primary" size="small" style="margin-top: 8px" @click="saveDesc">保存描述</el-button>

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
const captionDraft = ref('')
const longDraft = ref('')
const longOpen = ref<string[]>([])

const SCENE_LABELS: Record<string, string> = {
  group: '合照',
  pet: '宠物',
  scenery: '风景',
  food: '美食',
  architecture: '建筑',
  other: '其他'
}

const gpsText = computed(() => {
  const lat = photo.value?.metadata?.lat
  const lng = photo.value?.metadata?.lng
  return lat != null && lng != null ? `${Number(lat).toFixed(5)}, ${Number(lng).toFixed(5)}` : '无'
})

const briefCaption = computed(() => {
  const p = photo.value
  if (!p) return ''
  const ai = p.vision?.caption?.trim()
  const user = p.user_description?.trim()
  const fallback = '已提取拍摄信息，视觉模型未配置或调用失败。'
  if (ai && ai !== fallback) return ai
  if (user) return user
  return ai || p.filename || '暂无描述'
})

const longPreview = computed(() => {
  const p = photo.value
  if (!p) return ''
  return (p.user_long_description || p.vision?.long_description || '').trim()
})

const sceneLabel = computed(() => {
  const key = photo.value?.vision?.scene_type || ''
  return SCENE_LABELS[key] || key || '-'
})

const placeText = computed(() => {
  const p = photo.value
  if (!p) return '未知'
  const geo = p.geo || {}
  const meta = p.metadata || {}
  return (
    geo.place_name ||
    geo.city ||
    geo.district ||
    geo.township ||
    geo.street ||
    (geo.display_name ? geo.display_name.split(',')[0] : '') ||
    (meta.lat != null && meta.lng != null ? `${Number(meta.lat).toFixed(4)}, ${Number(meta.lng).toFixed(4)}` : '') ||
    '未知'
  )
})

const load = async () => {
  const res = await photoApi.get(route.params.id as string)
  photo.value = res.data
  captionDraft.value = res.data.user_description ?? ''
  longDraft.value = res.data.user_long_description ?? res.data.vision?.long_description ?? ''
  if (longDraft.value) longOpen.value = ['long']
}

const saveDesc = async () => {
  const id = route.params.id as string
  await photoApi.update(id, {
    user_description: captionDraft.value,
    user_long_description: longDraft.value
  })
  ElMessage.success('已更新描述')
  await load()
}

const reanalyze = async () => {
  await photoApi.analyze(route.params.id as string)
  ElMessage.success('已重新提交给 Agent1，请稍后刷新')
  setTimeout(load, 3000)
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
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
.tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
.desc-block { margin-top: 16px; }
h3 { margin: 0 0 8px; line-height: 1.4; font-size: 20px; }
</style>
