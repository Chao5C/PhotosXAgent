<template>
  <div>
    <div class="page-header">
      <el-button @click="router.push('/albums')">返回相册</el-button>
      <h2 class="page-title">{{ album?.name }}</h2>
    </div>
    <div class="grid">
      <div v-for="photo in album?.photos || []" :key="photo.id" class="item" @click="router.push(`/photo/${photo.id}`)">
        <PhotoThumb :id="photo.id" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { albumApi } from '@/api/photos'
import type { Album } from '@/types'
import PhotoThumb from '@/components/PhotoThumb.vue'

const route = useRoute()
const router = useRouter()
const album = ref<Album | null>(null)

onMounted(async () => {
  const res = await albumApi.get(route.params.id as string)
  album.value = res.data
})
</script>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.item { height: 160px; border-radius: 8px; overflow: hidden; cursor: pointer; }
</style>
