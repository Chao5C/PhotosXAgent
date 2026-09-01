<template>
  <div class="studio-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">自媒体工作台 <el-tag size="small" type="warning">Agent Beta</el-tag></h2>
        <p class="sub">选题 → 调研写入 content.md（唯一真相源）→ 派生稿 → TTS/字幕/画面 → 成片占位</p>
      </div>
      <div class="header-actions">
        <el-button @click="showGuide = true">框架说明</el-button>
        <el-button type="primary" @click="openCreate">新建选题</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :md="7">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="card-head">选题文件夹</div>
          </template>
          <el-empty v-if="!topics.length" description="还没有选题" />
          <div
            v-for="item in topics"
            :key="item.id"
            class="topic-item"
            :class="{ active: item.id === activeId }"
            @click="selectTopic(item.id)"
          >
            <div class="title">{{ item.title }}</div>
            <div class="meta">{{ item.status }} · {{ item.id }}</div>
          </div>
        </el-card>
      </el-col>

      <el-col :md="17">
        <el-empty v-if="!detail" description="选择或新建一个选题开始" />
        <template v-else>
          <el-card shadow="never" class="panel">
            <div class="toolbar">
              <div>
                <h3>{{ detail.meta?.title || detail.id }}</h3>
                <div class="muted">hash {{ detail.content_hash?.slice(0, 10) }} · {{ detail.path }}</div>
              </div>
              <div class="ops">
                <el-button :loading="busy === 'research'" @click="runResearch">① 调研</el-button>
                <el-button :loading="busy === 'derive'" @click="runDerive">② 派生稿</el-button>
                <el-button :loading="busy === 'produce'" @click="runProduce">③ 制作</el-button>
                <el-button type="primary" :loading="busy === 'pipeline'" @click="runPipeline">一键流水线</el-button>
                <el-button type="danger" plain @click="removeTopic">删除</el-button>
              </div>
            </div>

            <el-steps :active="stepActive" finish-status="success" align-center style="margin: 12px 0 20px">
              <el-step title="调研" description="联网取证 → content.md" />
              <el-step title="派生" description="口播/朋友圈/小红书/PPT" />
              <el-step title="制作" description="字幕·声线·画面·成片" />
            </el-steps>

            <el-tabs v-model="tab">
              <el-tab-pane label="content.md（SSOT）" name="content">
                <el-alert
                  type="info"
                  :closable="false"
                  show-icon
                  title="改这一份，点保存后下游产物会标为 stale；再点派生/制作即可增量更新。"
                  style="margin-bottom: 12px"
                />
                <el-input v-model="contentDraft" type="textarea" :rows="18" class="mono" />
                <div style="margin-top: 10px">
                  <el-button type="primary" :loading="busy === 'save'" @click="saveContent">保存 content.md</el-button>
                </div>
              </el-tab-pane>

              <el-tab-pane label="派生稿" name="scripts">
                <el-radio-group v-model="scriptKey" style="margin-bottom: 10px">
                  <el-radio-button label="speech">口播</el-radio-button>
                  <el-radio-button label="moments">朋友圈</el-radio-button>
                  <el-radio-button label="xhs">小红书</el-radio-button>
                  <el-radio-button label="wechat">公众号</el-radio-button>
                  <el-radio-button label="one_liner">播客分镜</el-radio-button>
                  <el-radio-button label="podcast">podcast.txt</el-radio-button>
                </el-radio-group>
                <el-button size="small" @click="loadScript" :loading="busy === 'file'">刷新</el-button>
                <el-button size="small" @click="copyScript">复制</el-button>
                <pre class="preview">{{ scriptText || '尚未生成，请先点「派生稿」' }}</pre>
              </el-tab-pane>

              <el-tab-pane label="HTML-PPT" name="ppt">
                <el-button size="small" @click="openDeck" :disabled="!detail.files?.html_ppt">新窗口打开 Deck</el-button>
                <iframe v-if="deckUrl" class="deck-frame" :src="deckUrl" title="deck" />
                <el-empty v-else description="派生后可预览 HTML-PPT" />
              </el-tab-pane>

              <el-tab-pane label="产物 / Manifest" name="manifest">
                <el-table :data="artifactRows" size="small">
                  <el-table-column prop="name" label="产物" width="120" />
                  <el-table-column prop="status" label="状态" width="120" />
                  <el-table-column prop="path" label="路径" />
                  <el-table-column prop="updated_at" label="更新时间" width="200" />
                </el-table>
                <pre class="preview" style="margin-top: 12px">{{ JSON.stringify(detail.manifest, null, 2) }}</pre>
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </template>
      </el-col>
    </el-row>

    <el-dialog v-model="createVisible" title="新建选题" width="480px">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="createForm.title" placeholder="例如：AI自媒体工具怎么选" />
        </el-form-item>
        <el-form-item label="种子">
          <el-input v-model="createForm.seed" type="textarea" :rows="3" placeholder="可选：你的初步想法" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy === 'create'" @click="createTopic">创建</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showGuide" title="Beta 框架与风险" size="420px">
      <ol class="guide">
        <li><b>调研层</b>：联网检索 + LLM 整理事实/金句，写入 <code>content.md</code>。</li>
        <li><b>SSOT</b>：只改 content.md；<code>.manifest.json</code> 记录指纹，实现增量。</li>
        <li><b>派生层</b>：官方 skills（humanizer / html-ppt / video-podcast-maker）→ 口播与多平台文案 / Deck / podcast.txt。</li>
        <li><b>制作层</b>：SRT 字幕、画面静帧、TTS/ffmpeg 成片（beta 多为占位）。</li>
      </ol>
      <h4>可能出现的问题</h4>
      <ul class="guide">
        <li>DuckDuckGo 检索被墙/限流 → sources 为空，需人工补 research/</li>
        <li>改 content.md 未再派生 → 下游仍是旧稿（看 manifest stale）</li>
        <li>TTS/ffmpeg 未装 → output 仅有 STATUS.md，不会出 mp4</li>
        <li>LLM 幻觉数字 → 以 sources 为准，风险写在 content.md</li>
        <li>HTML-PPT iframe 需登录态；可点「新窗口打开」</li>
      </ul>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { studioApi, type StudioTopicBrief, type StudioTopicDetail } from '@/api/studio'
import { useAuthStore } from '@/stores/auth'

const topics = ref<StudioTopicBrief[]>([])
const detail = ref<StudioTopicDetail | null>(null)
const activeId = ref('')
const contentDraft = ref('')
const tab = ref('content')
const scriptKey = ref('speech')
const scriptText = ref('')
const busy = ref('')
const createVisible = ref(false)
const showGuide = ref(false)
const createForm = ref({ title: '', seed: '' })
const authStore = useAuthStore()

const scriptPath: Record<string, string> = {
  speech: 'scripts/speech.md',
  moments: 'scripts/moments.md',
  xhs: 'scripts/xhs.md',
  wechat: 'scripts/wechat.md',
  one_liner: 'scripts/one_liner.md',
  podcast: 'scripts/podcast.txt'
}

const stepActive = computed(() => {
  const s = detail.value?.meta?.status || ''
  if (s === 'produced') return 3
  if (s === 'derived') return 2
  if (s === 'researched') return 1
  return 0
})

const artifactRows = computed(() => {
  const arts = detail.value?.manifest?.artifacts || {}
  return Object.keys(arts).map((name) => ({ name, ...arts[name] }))
})

const deckBlob = ref('')

const revokeDeck = () => {
  if (deckBlob.value) URL.revokeObjectURL(deckBlob.value)
  deckBlob.value = ''
}

const loadDeck = async () => {
  if (!activeId.value || !detail.value?.files?.html_ppt) {
    revokeDeck()
    return
  }
  const res = await fetch(`/api/studio/topics/${activeId.value}/deck`, {
    headers: { Authorization: `Bearer ${authStore.token || ''}` }
  })
  if (!res.ok) {
    revokeDeck()
    return
  }
  const html = await res.text()
  revokeDeck()
  deckBlob.value = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
}

const deckUrl = computed(() => deckBlob.value)

const refreshList = async () => {
  const res = await studioApi.list()
  topics.value = res.data || []
}

const selectTopic = async (id: string) => {
  activeId.value = id
  const res = await studioApi.get(id)
  detail.value = res.data
  contentDraft.value = res.data.content_md
  await loadScript()
}

const openCreate = () => {
  createForm.value = { title: '', seed: '' }
  createVisible.value = true
}

const createTopic = async () => {
  if (!createForm.value.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  busy.value = 'create'
  try {
    const res = await studioApi.create(createForm.value.title.trim(), createForm.value.seed)
    createVisible.value = false
    await refreshList()
    await selectTopic(res.data.id)
    ElMessage.success('已创建选题文件夹')
  } finally {
    busy.value = ''
  }
}

const saveContent = async () => {
  if (!activeId.value) return
  busy.value = 'save'
  try {
    const res = await studioApi.updateContent(activeId.value, contentDraft.value)
    detail.value = res.data
    ElMessage.success('已保存，下游标为 stale')
  } finally {
    busy.value = ''
  }
}

const applyDetail = (data: StudioTopicDetail) => {
  detail.value = data
  contentDraft.value = data.content_md
  if (tab.value === 'ppt') loadDeck()
}

const runResearch = async () => {
  if (!activeId.value) return
  busy.value = 'research'
  try {
    const res = await studioApi.research(activeId.value)
    applyDetail(res.data)
    ElMessage.success(res.message || '调研完成')
  } finally {
    busy.value = ''
  }
}

const runDerive = async () => {
  if (!activeId.value) return
  busy.value = 'derive'
  try {
    const res = await studioApi.derive(activeId.value, true)
    applyDetail(res.data)
    await loadScript()
    ElMessage.success(res.message || '派生完成')
  } finally {
    busy.value = ''
  }
}

const runProduce = async () => {
  if (!activeId.value) return
  busy.value = 'produce'
  try {
    const res = await studioApi.produce(activeId.value)
    applyDetail(res.data)
    ElMessage.success(res.message || '制作层完成')
  } finally {
    busy.value = ''
  }
}

const runPipeline = async () => {
  if (!activeId.value) return
  busy.value = 'pipeline'
  try {
    const res = await studioApi.pipeline(activeId.value)
    applyDetail(res.data)
    await loadScript()
    ElMessage.success('流水线完成')
  } finally {
    busy.value = ''
  }
}

const removeTopic = async () => {
  if (!activeId.value) return
  await ElMessageBox.confirm('删除后选题文件夹不可恢复', '删除选题')
  await studioApi.remove(activeId.value)
  detail.value = null
  activeId.value = ''
  await refreshList()
}

const loadScript = async () => {
  if (!activeId.value) return
  const path = scriptPath[scriptKey.value]
  if (!path) return
  busy.value = 'file'
  try {
    const res = await studioApi.readFile(activeId.value, path)
    scriptText.value = res.data.content
  } catch {
    scriptText.value = ''
  } finally {
    busy.value = ''
  }
}

const copyScript = async () => {
  if (!scriptText.value) return
  await navigator.clipboard.writeText(scriptText.value)
  ElMessage.success('已复制')
}

const openDeck = async () => {
  await loadDeck()
  if (deckBlob.value) window.open(deckBlob.value, '_blank')
}

watch(scriptKey, loadScript)
watch(tab, (name) => {
  if (name === 'ppt') loadDeck()
})

onMounted(async () => {
  await refreshList()
  if (topics.value[0]) await selectTopic(topics.value[0].id)
})

onUnmounted(() => revokeDeck())
</script>

<style scoped lang="scss">
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.header-actions { display: flex; gap: 8px; }
.panel { margin-bottom: 12px; }
.card-head { font-weight: 600; }
.topic-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 6px;
  border: 1px solid transparent;
}
.topic-item:hover, .topic-item.active {
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color);
}
.topic-item .title { font-weight: 600; }
.topic-item .meta { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.toolbar { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.ops { display: flex; gap: 8px; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.mono :deep(textarea) { font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
.preview {
  margin-top: 10px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  white-space: pre-wrap;
  max-height: 420px;
  overflow: auto;
  font-size: 13px;
}
.deck-frame {
  width: 100%;
  height: 480px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-top: 10px;
  background: #0f1419;
}
.guide { line-height: 1.7; color: var(--el-text-color-regular); }
.guide code { font-size: 12px; }
</style>
