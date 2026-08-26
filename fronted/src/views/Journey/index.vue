<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">行程模拟</h2>
        <p class="sub">按拍摄时间与 GPS 在地图上还原移动轨迹。需要照片带定位信息。</p>
      </div>
      <div class="ops">
        <el-button :disabled="!points.length" @click="togglePlay">{{ playing ? '暂停' : '播放行程' }}</el-button>
        <el-button @click="resetPlay" :disabled="!points.length">重置</el-button>
      </div>
    </div>
    <div class="map-wrap">
      <div ref="mapEl" class="map"></div>
    </div>
    <el-timeline v-if="points.length" class="timeline">
      <el-timeline-item v-for="(p, idx) in points" :key="p.id" :timestamp="p.taken_at || ''" :type="idx <= cursor ? 'primary' : 'info'">
        {{ p.place || p.city || '未知地点' }} · {{ p.caption || p.filename }}
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="还没有带 GPS 的照片，上传含定位的图片后即可模拟行程" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import L from 'leaflet'
import { journeyApi } from '@/api/photos'
import type { JourneyPoint } from '@/types'

const mapEl = ref<HTMLElement | null>(null)
const points = ref<JourneyPoint[]>([])
const playing = ref(false)
const cursor = ref(0)
let map: L.Map | null = null
let marker: L.CircleMarker | null = null
let line: L.Polyline | null = null
let timer: number | undefined

const addTiles = (target: L.Map) => {
  const gaode = L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
    subdomains: '1234',
    maxZoom: 18,
    attribution: '&copy; 高德地图'
  })
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
  marker?.remove()
  const latlngs = points.value
    .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng))
    .map((p) => [p.lat, p.lng] as [number, number])
  if (!latlngs.length) {
    map.setView([35.0, 105.0], 4)
    map.invalidateSize()
    return
  }
  line = L.polyline(latlngs, { color: '#409EFF', weight: 4 }).addTo(map)
  marker = L.circleMarker(latlngs[0], { radius: 9, color: '#fff', fillColor: '#E6A23C', fillOpacity: 1, weight: 2 }).addTo(map)
  map.fitBounds(line.getBounds().pad(0.25))
  map.invalidateSize()
  cursor.value = 0
}

const step = () => {
  if (!marker || cursor.value >= points.value.length - 1) {
    playing.value = false
    if (timer) clearInterval(timer)
    return
  }
  cursor.value += 1
  const p = points.value[cursor.value]
  marker.setLatLng([p.lat, p.lng])
  map?.panTo([p.lat, p.lng])
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
  if (marker && points.value[0]) marker.setLatLng([points.value[0].lat, points.value[0].lng])
}

onMounted(async () => {
  await initMap()
  const res = await journeyApi.get()
  points.value = res.data.points || []
  await nextTick()
  draw()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  map?.remove()
  map = null
})
</script>

<style scoped>
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.ops { display: flex; gap: 8px; }
.map-wrap {
  width: 100%;
  height: 480px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  position: relative;
  z-index: 1;
}
.map {
  width: 100%;
  height: 100%;
  min-height: 480px;
}
.timeline { margin-top: 20px; }
</style>

<style>
.leaflet-container {
  width: 100%;
  height: 100%;
  z-index: 1;
  background: #e8eef5;
}
.leaflet-pane,
.leaflet-tile,
.leaflet-marker-icon,
.leaflet-marker-shadow,
.leaflet-tile-container,
.leaflet-map-pane svg,
.leaflet-map-pane canvas,
.leaflet-zoom-box,
.leaflet-image-layer,
.leaflet-layer {
  position: absolute;
  left: 0;
  top: 0;
}
</style>
