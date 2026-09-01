<template>
  <div v-if="queue" class="queue-float" :class="{ collapsed: !expanded }">
    <div class="queue-float-head" @click="expanded = !expanded">
      <div class="title">
        <strong>解析队列</strong>
        <el-badge v-if="queue.active" :value="queue.active" type="warning" />
      </div>
      <div class="head-right">
        <el-tag v-if="expanded" size="small" type="info">排队 {{ queue.counts.pending }}</el-tag>
        <el-tag v-if="expanded" size="small" type="warning">识别中 {{ queue.counts.analyzing }}</el-tag>
        <el-tag v-if="expanded" size="small" type="danger">失败 {{ queue.counts.failed }}</el-tag>
        <el-icon class="toggle-icon"><component :is="expanded ? ArrowDown : ArrowUp" /></el-icon>
      </div>
    </div>
    <div v-show="expanded" class="queue-float-body">
      <el-table v-if="queue.items.length" :data="queue.items" size="small" max-height="240">
        <el-table-column label="缩略图" width="56">
          <template #default="{ row }">
            <div v-if="row.id" class="queue-thumb"><PhotoThumb :id="row.id" /></div>
          </template>
        </el-table-column>
        <el-table-column prop="filename" label="文件" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="72">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="parse_error" label="错误" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="56">
          <template #default="{ row }">
            <el-button v-if="row.id" link type="primary" @click="openDetail(row.id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无排队任务" :image-size="48" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import type { ParseQueue } from '@/types'
import PhotoThumb from '@/components/PhotoThumb.vue'

defineProps<{ queue: ParseQueue | null }>()

const router = useRouter()
const expanded = ref(true)

const statusText = (status: string) =>
  ({ pending: '排队', analyzing: '识别中', failed: '失败', ready: '完成' }[status] || status)

const statusType = (status: string) =>
  ({ pending: 'info', analyzing: 'warning', failed: 'danger', ready: 'success' }[status] || 'info')

const openDetail = (id: string) => {
  if (!id) return
  router.push(`/photo/${id}`)
}
</script>

<style scoped lang="scss">
.queue-float {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 420px;
  max-width: calc(100vw - 48px);
  z-index: 2000;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}
.queue-float.collapsed {
  width: 280px;
}
.queue-float-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  background: var(--el-fill-color-light);
  user-select: none;
}
.title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.head-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.toggle-icon {
  color: var(--el-text-color-secondary);
}
.queue-float-body {
  padding: 8px 10px 10px;
}
.queue-thumb {
  width: 40px;
  height: 40px;
  overflow: hidden;
  border-radius: 6px;
}
</style>
