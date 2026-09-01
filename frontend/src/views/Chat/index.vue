<template>
  <div class="chat-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">助手 Agent</h2>
        <p class="sub">可上传照片咨询、检索相册，并接收行程攻略推送。</p>
      </div>
    </div>
    <div class="chat-card">
      <div ref="listRef" class="messages">
        <div v-for="(msg, idx) in messages" :key="msg.id || idx" class="msg" :class="msg.role">
          <div class="bubble" :class="msg.kind">
            <div class="text">{{ msg.content }}</div>
            <div v-if="msg.status" class="stream-status">{{ msg.status }}</div>
            <div v-if="msg.reminder" class="reminder-card">
              <div class="reminder-title">⏰ 已设置提醒</div>
              <div v-if="msg.reminder.text" class="reminder-text">{{ msg.reminder.text }}</div>
              <div class="reminder-time">触发时间：{{ formatReminderTime(msg.reminder.fire_at) }}</div>
            </div>
            <div v-if="posterDisplay(msg)" class="poster-card">
              <img :src="posterDisplay(msg)" alt="攻略海报" class="poster-image" />
              <div class="poster-actions">
                <el-button text type="primary" @click="downloadPoster(msg)">下载 PNG</el-button>
                <el-button text @click="router.push('/posters')">海报图库</el-button>
              </div>
            </div>
            <div v-if="msg.photo_ids?.length" class="attach-row">
              <div v-for="pid in msg.photo_ids" :key="pid" class="mini" @click="openPhoto(pid)">
                <PhotoThumb :id="pid" />
              </div>
            </div>
            <div v-if="msg.albums?.length" class="album-row">
              <el-tag
                v-for="album in msg.albums"
                :key="album.id"
                class="album-tag"
                @click="router.push(`/albums/${album.id}`)"
              >
                {{ album.name }} · {{ album.count || 0 }}
              </el-tag>
            </div>
            <div v-if="msg.photos?.length" class="photo-grid">
              <div v-for="photo in msg.photos" :key="photo.id" class="photo-card">
                <div class="thumb" @click="openPhoto(photo.id)">
                  <PhotoThumb :id="photo.id" />
                </div>
                <el-input
                  v-if="editing === photo.id"
                  v-model="editText"
                  size="small"
                  @keyup.enter="saveCaption(photo)"
                  @blur="saveCaption(photo)"
                />
                <div v-else class="caption" @click.stop="startEdit(photo)">
                  {{ photo.brief_caption || photo.caption || photo.filename || '点击修改描述' }}
                </div>
              </div>
            </div>
            <el-button
              v-if="msg.role === 'assistant' && msg.query_id && msg.has_more"
              text
              type="primary"
              size="small"
              @click="viewMore(msg)"
            >
              查看更多<span v-if="msg.total">（已展示 {{ msg.photos?.length || 0 }} / {{ msg.total }}）</span>
            </el-button>
          </div>
        </div>
      </div>
      <div v-if="pending.length" class="pending">
        <div v-for="(file, idx) in pending" :key="idx" class="pending-item">
          <span>{{ file.name }}</span>
          <el-button text type="danger" @click="pending.splice(idx, 1)">移除</el-button>
        </div>
      </div>
      <div class="composer">
        <el-select
          v-model="modelId"
          class="model-select"
          filterable
          clearable
          placeholder="选择模型"
          :disabled="!enabledGroups.length"
          @change="onModelChange"
        >
          <el-option-group v-for="group in enabledGroups" :key="group.provider" :label="group.display_name">
            <el-option
              v-for="item in group.models"
              :key="item.id"
              :label="item.model_display_name"
              :value="item.id"
            />
          </el-option-group>
        </el-select>
        <el-button @click="fileRef?.click()">上传</el-button>
        <input ref="fileRef" type="file" accept="image/*" multiple hidden @change="onPickFiles" />
        <el-input
          v-model="input"
          :placeholder="enabledGroups.length ? '找照片、问天气，或上传图片咨询' : '请先在配置管理中启用并配置模型'"
          @keyup.enter="send"
        />
        <el-button type="primary" :loading="sending" :disabled="!modelId" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chatApi, configApi, photoApi } from '@/api/photos'
import { posterFileUrl } from '@/api/posters'
import { llmApi, parseModelId, toModelId, type EnabledLLMModel } from '@/api/llm'
import type { ChatMessage, ChatPhotoCard, ChatReminder, ChatReply } from '@/types'
import PhotoThumb from '@/components/PhotoThumb.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const messages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const listRef = ref<HTMLElement | null>(null)
const fileRef = ref<HTMLInputElement | null>(null)
const modelId = ref('')
const enabledModels = ref<EnabledLLMModel[]>([])
const pending = ref<File[]>([])
const editing = ref('')
const editText = ref('')
let inboxTimer: number | undefined
let reminderPollTimer: number | undefined
let lastInboxAt = ''

const enabledGroups = computed(() => {
  const map = new Map<string, { provider: string; display_name: string; models: EnabledLLMModel[] }>()
  for (const item of enabledModels.value) {
    if (!map.has(item.provider)) {
      map.set(item.provider, {
        provider: item.provider,
        display_name: item.provider_display_name || item.provider,
        models: []
      })
    }
    map.get(item.provider)!.models.push(item)
  }
  return Array.from(map.values())
})

const scrollBottom = async () => {
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

const loadModel = async () => {
  const [modelsRes, cfg] = await Promise.all([llmApi.enabledModels(), configApi.get()])
  enabledModels.value = modelsRes.data || []
  const agent3 = cfg.data?.agent_models?.agent3
  const selected = toModelId(agent3?.provider, agent3?.model_name)
  modelId.value = enabledModels.value.some((item) => item.id === selected) ? selected : ''
}

const onModelChange = async (id: string) => {
  const binding = parseModelId(id || '')
  await configApi.update({ agent_models: { agent3: binding } })
}

const openPhoto = (id: string) => router.push(`/photo/${id}`)

const onPickFiles = (event: Event) => {
  const inputEl = event.target as HTMLInputElement
  pending.value = [...pending.value, ...Array.from(inputEl.files || [])]
  inputEl.value = ''
}

const startEdit = (photo: ChatPhotoCard) => {
  editing.value = photo.id
  editText.value = photo.caption || ''
}

const saveCaption = async (photo: ChatPhotoCard) => {
  if (editing.value !== photo.id) return
  const text = editText.value.trim()
  editing.value = ''
  if (text === (photo.caption || '')) return
  await photoApi.update(photo.id, { user_description: text })
  photo.caption = text
  ElMessage.success('已更新描述')
}

const viewMore = async (msg: ChatMessage) => {
  if (!msg.query_id) return
  const offset = msg.photos?.length || 0
  const res = await chatApi.search(msg.query_id, { offset, limit: 5 })
  msg.photos = [...(msg.photos || []), ...(res.data.photos || [])]
  msg.albums = res.data.albums || msg.albums
  msg.total = res.data.total ?? msg.total
  msg.has_more = res.data.has_more ?? false
}

const posterDisplay = (msg: ChatMessage) =>
  msg.poster?.image_data_url || msg.posterPreview || ''

const ensurePosterPreview = async (msg: ChatMessage) => {
  if (msg.poster?.image_data_url || msg.posterPreview) return
  const posterId = msg.poster?.id || msg.poster?.poster_id
  if (!posterId) return
  try {
    const resp = await fetch(posterFileUrl(posterId), {
      headers: { Authorization: `Bearer ${authStore.token || ''}` }
    })
    if (!resp.ok) return
    const blob = await resp.blob()
    msg.posterPreview = URL.createObjectURL(blob)
  } catch {
    /* ignore preview load errors */
  }
}

const downloadPoster = (msg: ChatMessage) => {
  const src = posterDisplay(msg)
  if (!src) return
  const a = document.createElement('a')
  a.href = src
  a.download = `${msg.poster?.title || 'poster'}.png`
  a.click()
}

const formatReminderTime = (value?: string) => {
  if (!value) return '稍后'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const scheduleReminderPolls = (reminder?: ChatReminder) => {
  if (!reminder?.fire_at) return
  if (reminderPollTimer) window.clearTimeout(reminderPollTimer)
  const target = new Date(reminder.fire_at).getTime()
  const poll = async () => {
    await pollInbox()
    if (Date.now() < target + 20000) {
      reminderPollTimer = window.setTimeout(poll, 2000)
    }
  }
  reminderPollTimer = window.setTimeout(poll, 2000)
}

const pollInbox = async () => {
  try {
    const res = await chatApi.inbox(lastInboxAt || undefined)
    const items = res.data || []
    for (const item of items) {
      if (item.created_at && item.created_at > lastInboxAt) lastInboxAt = item.created_at
      if (messages.value.some((m) => m.id && item.id && m.id === item.id)) continue
      if (item.content && messages.value.some((m) => m.role === 'assistant' && m.content === item.content && m.created_at === item.created_at)) continue
      messages.value.push(item)
    }
    if (items.length) await scrollBottom()
  } catch {
    /* ignore polling errors */
  }
}

const send = async () => {
  const text = input.value.trim()
  if ((!text && !pending.value.length) || sending.value) return
  if (!modelId.value) {
    ElMessage.warning('请先选择对话模型')
    return
  }
  sending.value = true
  const files = [...pending.value]
  pending.value = []
  input.value = ''
  try {
    let photoIds: string[] = []
    if (files.length) {
      const uploaded = await photoApi.upload(files)
      photoIds = (uploaded.data?.items || []).map((item: { id: string }) => item.id).filter(Boolean)
    }
    messages.value.push({
      role: 'user',
      content: text || (photoIds.length ? '请看看这些照片' : ''),
      photo_ids: photoIds,
      kind: 'chat'
    })
    await scrollBottom()
    const binding = parseModelId(modelId.value)
    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      kind: 'chat'
    }
    messages.value.push(assistantMsg)
    await scrollBottom()
    await chatApi.sendStream(
      {
        message: text || '请看看这些照片',
        photo_ids: photoIds,
        provider: binding.provider || undefined,
        model_name: binding.model_name || undefined,
        top_k: 5
      },
      {
        onStatus: (status) => {
          assistantMsg.status = status
        },
        onToken: (token) => {
          assistantMsg.content += token
          scrollBottom()
        },
        onDone: (data) => {
          assistantMsg.content = data.reply || assistantMsg.content
          assistantMsg.status = ''
          assistantMsg.kind = (data.kind as ChatMessage['kind']) || 'chat'
          assistantMsg.intent = data.intent
          assistantMsg.photos = data.photos || []
          assistantMsg.albums = data.albums || []
          assistantMsg.total = data.total || 0
          assistantMsg.has_more = data.has_more || false
          assistantMsg.query_id = data.query_id
          assistantMsg.reminder = data.reminder
          assistantMsg.poster = data.poster
          assistantMsg.guide = data.guide
          if (data.poster?.image_data_url) {
            assistantMsg.posterPreview = data.poster.image_data_url
          } else if (data.poster) {
            ensurePosterPreview(assistantMsg)
          }
          lastInboxAt = new Date().toISOString()
          if (data.reminder) scheduleReminderPolls(data.reminder)
          scrollBottom()
        },
        onError: () => {
          assistantMsg.status = ''
        }
      }
    )
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

onMounted(async () => {
  const res = await chatApi.history()
  messages.value = res.data || []
  for (const msg of messages.value) {
    if (msg.poster?.id || msg.poster?.poster_id) ensurePosterPreview(msg)
  }
  if (!messages.value.length) {
    messages.value.push({ role: 'assistant', content: '你好，我是 PhotosXAgent 助手。可以上传照片咨询、搜索相册，或让我推送行程攻略。' })
  }
  const last = [...messages.value].reverse().find((m) => m.created_at)
  lastInboxAt = last?.created_at || new Date().toISOString()
  await loadModel()
  await scrollBottom()
  inboxTimer = window.setInterval(pollInbox, 5000)
})

onUnmounted(() => {
  if (inboxTimer) window.clearInterval(inboxTimer)
  if (reminderPollTimer) window.clearTimeout(reminderPollTimer)
})
</script>

<style scoped lang="scss">
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.chat-card {
  height: calc(100vh - 180px);
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 16px;
}
.messages { flex: 1; overflow: auto; padding: 12px; }
.msg { display: flex; margin-bottom: 12px; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--el-fill-color);
}
.bubble.push, .bubble.reminder { border: 1px solid var(--el-color-primary-light-5); }
.reminder-card {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  font-size: 13px;
}
.reminder-title { font-weight: 600; margin-bottom: 4px; }
.reminder-text, .reminder-time { color: var(--el-text-color-secondary); }
.stream-status { margin-top: 6px; font-size: 12px; color: var(--el-color-primary); }
.poster-card { margin-top: 10px; }
.poster-image { width: 100%; max-width: 420px; border-radius: 12px; border: 1px solid var(--el-border-color-lighter); }
.poster-actions { display: flex; gap: 8px; margin-top: 8px; }
.text { white-space: pre-wrap; }
.msg.user .bubble { background: var(--el-color-primary); color: #fff; }
.composer { display: flex; gap: 8px; align-items: center; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.model-select { width: 200px; flex-shrink: 0; }
.composer :deep(.el-input) { flex: 1; }
.photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; margin-top: 10px; }
.photo-card .thumb { height: 90px; border-radius: 8px; overflow: hidden; }
.caption { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); cursor: pointer; }
.album-row, .attach-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.mini { width: 56px; height: 56px; border-radius: 8px; overflow: hidden; }
.album-tag { cursor: pointer; }
.pending { padding: 8px 0; display: flex; gap: 8px; flex-wrap: wrap; }
.pending-item { font-size: 12px; display: flex; align-items: center; gap: 4px; }
</style>
