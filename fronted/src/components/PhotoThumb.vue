<template>
  <img v-if="src" :src="src" :alt="alt" class="photo-thumb" @click="$emit('click')" />
  <div v-else class="photo-thumb placeholder">加载中</div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { photoFileUrl } from '@/api/photos'

const props = defineProps<{ id: string; thumb?: boolean; alt?: string }>()
defineEmits(['click'])
const src = ref('')
let objectUrl = ''

const load = async () => {
  const authStore = useAuthStore()
  const response = await fetch(photoFileUrl(props.id, props.thumb !== false), {
    headers: { Authorization: `Bearer ${authStore.token || ''}` }
  })
  if (!response.ok) return
  const blob = await response.blob()
  if (objectUrl) URL.revokeObjectURL(objectUrl)
  objectUrl = URL.createObjectURL(blob)
  src.value = objectUrl
}

onMounted(load)
watch(() => props.id, load)
onBeforeUnmount(() => {
  if (objectUrl) URL.revokeObjectURL(objectUrl)
})
</script>

<style scoped>
.photo-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  cursor: pointer;
}
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
