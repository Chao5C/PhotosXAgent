<template>
  <div class="chat-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">助手 Agent</h2>
        <p class="sub">用自然语言查照片、问行程、了解推荐。由 Agent3 对接你的需求。</p>
      </div>
    </div>
    <div class="chat-card">
      <div ref="listRef" class="messages">
        <div v-for="(msg, idx) in messages" :key="idx" class="msg" :class="msg.role">
          <div class="bubble">{{ msg.content }}</div>
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
        <el-input
          v-model="input"
          :placeholder="enabledGroups.length ? '例如：帮我找去年杭州的风景照' : '请先在配置管理中启用并配置模型'"
          @keyup.enter="send"
        />
        <el-button type="primary" :loading="sending" :disabled="!modelId" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { chatApi, configApi } from '@/api/photos'
import { llmApi, parseModelId, toModelId, type EnabledLLMModel } from '@/api/llm'
import type { ChatMessage } from '@/types'

const messages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const listRef = ref<HTMLElement | null>(null)
const modelId = ref('')
const enabledModels = ref<EnabledLLMModel[]>([])

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

const send = async () => {
  const text = input.value.trim()
  if (!text || sending.value) return
  if (!modelId.value) {
    ElMessage.warning('请先选择对话模型')
    return
  }
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true
  await scrollBottom()
  try {
    const binding = parseModelId(modelId.value)
    const res = await chatApi.send(text, binding.provider ? binding : undefined)
    messages.value.push({ role: 'assistant', content: res.data.reply })
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

onMounted(async () => {
  const res = await chatApi.history()
  messages.value = res.data || []
  if (!messages.value.length) {
    messages.value.push({ role: 'assistant', content: '你好，我是 PhotosXAgent 助手。可以帮你找照片、讲行程、解释推荐。' })
  }
  await loadModel()
  await scrollBottom()
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
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--el-fill-color);
  white-space: pre-wrap;
}
.msg.user .bubble { background: var(--el-color-primary); color: #fff; }
.composer { display: flex; gap: 8px; align-items: center; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.model-select { width: 240px; flex-shrink: 0; }
.composer :deep(.el-input) { flex: 1; }
</style>
