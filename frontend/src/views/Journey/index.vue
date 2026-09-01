<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">行程模拟</h2>
        <p class="sub">按拍摄时间与 GPS 在地图上还原移动轨迹；地点来自高德逆地理编码，非 LLM 猜测。</p>
      </div>
      <div class="ops">
        <el-button :loading="regeocoding" @click="refreshPlaces">刷新地点</el-button>
        <el-button :disabled="!points.length" @click="togglePlay">{{ playing ? '暂停' : '播放行程' }}</el-button>
        <el-button @click="resetPlay" :disabled="!points.length">重置</el-button>
      </div>
    </div>
    <div class="map-wrap">
      <div ref="mapEl" class="map"></div>
    </div>
    <el-timeline v-if="points.length" class="timeline">
      <el-timeline-item
        v-for="(p, idx) in points"
        :key="p.id"
        :timestamp="p.taken_at || ''"
        :type="idx <= cursor ? 'primary' : 'info'"
      >
        <div class="timeline-row" @click="focusPoint(idx)">
          <img v-if="thumbUrls[p.id]" :src="thumbUrls[p.id]" class="timeline-thumb" alt="" />
          <span>
            {{ p.place || p.city || (p.lat != null ? `${Number(p.lat).toFixed(4)}, ${Number(p.lng).toFixed(4)}` : '未知地点') }}
            · {{ p.caption || p.filename }}
          </span>
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="还没有带 GPS 的照片，上传含定位的图片后即可模拟行程" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import L from 'leaflet'
import { ElMessage } from 'element-plus'
import { journeyApi, photoApi, photoFileUrl } from '@/api/photos'
import { useAuthStore } from '@/stores/auth'
import type { JourneyPoint } from '@/types'

const router = useRouter()
const authStore = useAuthStore()
const mapEl = ref<HTMLElement | null>(null)
const points = ref<JourneyPoint[]>([])
const thumbUrls = ref<Record<string, string>>({})
const playing = ref(false)
const regeocoding = ref(false)
const cursor = ref(0)
let map: L.Map | null = null
let line: L.Polyline | null = null
let photoMarkers: L.Marker[] = []
let objectUrls: string[] = []
let timer: number | undefined

const addTiles = (target: L.Map) => {
  const gaode = L.tileLayer(
    'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    { subdomains: '1234', maxZoom: 18, attribution: '&copy; 高德地图' }
  )
  const carto = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    subdomains: 'abcd',
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap, Carto'
  })
  gaode.on('tileerror', () => {
    if (!target.hasLayer(carto)) {
      target.removeLayer(gaode)
      carto.addTo(target)
    }
  })
  gaode.addTo(target)
}

const clearThumbs = () => {
  objectUrls.forEach((url) => URL.revokeObjectURL(url))
  objectUrls = []
  thumbUrls.value = {}
}

const preloadThumbs = async () => {
  clearThumbs()
  const token = authStore.token || ''
  await Promise.all(
    points.value.map(async (p) => {
      try {
        const res = await fetch(photoFileUrl(p.id, true), {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (!res.ok) return
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        objectUrls.push(url)
        thumbUrls.value[p.id] = url
      } catch {
        /* ignore single thumb failure */
      }
    })
  )
}

const photoIcon = (url: string, active = false) =>
  L.divIcon({
    className: 'journey-photo-marker',
    html: `<div class="photo-pin${active ? ' active' : ''}"><img src="${url}" alt="" /></div>`,
    iconSize: [48, 48],
    iconAnchor: [24, 24],
    popupAnchor: [0, -24]
  })

const popupHtml = (p: JourneyPoint, url: string) => {
  const place = p.place || p.city || `${Number(p.lat).toFixed(4)}, ${Number(p.lng).toFixed(4)}`
  return `
    <div class="journey-popup">
      <img src="${url}" alt="" />
      <div class="popup-meta">
        <strong>${place}</strong>
        <div>${p.taken_at || ''}</div>
        <div>${p.caption || p.filename || ''}</div>
      </div>
    </div>
  `
}

const updateMarkerHighlight = () => {
  photoMarkers.forEach((marker, idx) => {
    const p = points.value[idx]
    const url = thumbUrls.value[p.id]
    if (!url) return
    marker.setIcon(photoIcon(url, idx === cursor.value))
  })
}

const initMap = async () => {
  await nextTick()
  if (!mapEl.value || map) return
  map = L.map(mapEl.value, { zoomControl: true }).setView([35.0, 105.0], 4)
  addTiles(map)
  requestAnimationFrame(() => map?.invalidateSize())
  setTimeout(() => map?.invalidateSize(), 250)
}

const draw = () => {
  if (!map) return
  line?.remove()
  photoMarkers.forEach((m) => m.remove())
  photoMarkers = []

  const latlngs = points.value
    .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng))
    .map((p) => [p.lat, p.lng] as [number, number])

  if (!latlngs.length) {
    map.setView([35.0, 105.0], 4)
    map.invalidateSize()
    return
  }

  line = L.polyline(latlngs, { color: '#409EFF', weight: 3, opacity: 0.85 }).addTo(map)

  points.value.forEach((p, idx) => {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lng)) return
    const url = thumbUrls.value[p.id]
    if (!url) return
    const marker = L.marker([p.lat, p.lng], { icon: photoIcon(url, idx === cursor.value) })
      .bindPopup(popupHtml(p, url), { maxWidth: 240 })
      .on('click', () => {
        cursor.value = idx
        updateMarkerHighlight()
      })
      .addTo(map!)
    marker.on('dblclick', () => router.push(`/photo/${p.id}`))
    photoMarkers.push(marker)
  })

  map.fitBounds(line.getBounds().pad(0.22))
  map.invalidateSize()
  cursor.value = 0
}

const focusPoint = (idx: number) => {
  cursor.value = idx
  updateMarkerHighlight()
  const p = points.value[idx]
  if (p && map) {
    map.panTo([p.lat, p.lng])
    photoMarkers[idx]?.openPopup()
  }
}

const step = () => {
  if (cursor.value >= points.value.length - 1) {
    playing.value = false
    if (timer) clearInterval(timer)
    return
  }
  cursor.value += 1
  updateMarkerHighlight()
  const p = points.value[cursor.value]
  map?.panTo([p.lat, p.lng])
  photoMarkers[cursor.value]?.openPopup()
}

const togglePlay = () => {
  if (playing.value) {
    playing.value = false
    if (timer) clearInterval(timer)
    return
  }
  playing.value = true
  timer = window.setInterval(step, 1200)
}

const resetPlay = () => {
  playing.value = false
  if (timer) clearInterval(timer)
  cursor.value = 0
  updateMarkerHighlight()
  if (points.value[0]) {
    map?.panTo([points.value[0].lat, points.value[0].lng])
    photoMarkers[0]?.openPopup()
  }
}

const loadJourney = async () => {
  const res = await journeyApi.get()
  points.value = res.data.points || []
  await preloadThumbs()
  await nextTick()
  draw()
}

const refreshPlaces = async () => {
  regeocoding.value = true
  try {
    const res = await photoApi.regeocodeBatch()
    ElMessage.success(res.message || `已刷新 ${res.data?.updated || 0} 张照片地点`)
    await loadJourney()
  } finally {
    regeocoding.value = false
  }
}

onMounted(async () => {
  await initMap()
  await loadJourney()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  clearThumbs()
  map?.remove()
  map = null
})
</script>

<style scoped>
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.ops { display: flex; gap: 8px; flex-wrap: wrap; }
.map-wrap {
  width: 100%;
  height: 520px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  position: relative;
  z-index: 1;
}
.map {
  width: 100%;
  height: 100%;
  min-height: 520px;
}
.timeline { margin-top: 20px; }
.timeline-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.timeline-thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
</style>

<style>
.leaflet-container {
  width: 100%;
  height: 100%;
  z-index: 1;
  background: #e8eef5;
}
.journey-photo-marker {
  background: transparent;
  border: none;
}
.photo-pin {
  width: 44px;
  height: 44px;
  border: 2px solid #fff;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.photo-pin img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.photo-pin.active {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.35);
  transform: scale(1.08);
  z-index: 2;
}
.journey-popup img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border-radius: 6px;
  margin-bottom: 8px;
}
.journey-popup .popup-meta {
  font-size: 12px;
  line-height: 1.5;
  color: #303133;
}
</style>
