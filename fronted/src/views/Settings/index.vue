<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">配置管理</h2>
        <p class="sub">管理厂家、模型目录、大模型，以及三个 Agent 各自使用的模型。</p>
      </div>
      <el-button type="success" :loading="reloading" @click="reload">重载配置</el-button>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="厂家管理" name="providers">
        <div class="toolbar">
          <h3>大模型厂家管理</h3>
          <el-button type="primary" @click="openProvider()">添加厂家</el-button>
        </div>
        <el-table :data="providers" v-loading="loading.providers" style="width: 100%">
          <el-table-column label="厂家信息" min-width="160">
            <template #default="{ row }">
              <div class="name">{{ row.display_name }}</div>
              <div class="muted">{{ row.name }}</div>
            </template>
          </el-table-column>
          <el-table-column label="API 密钥" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.extra_config?.has_api_key ? 'success' : 'danger'" size="small">
                {{ row.extra_config?.has_api_key ? '已配置' : '未配置' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="描述" min-width="280">
            <template #default="{ row }">{{ row.description || '暂无描述' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
              <el-tag v-if="row.extra_config?.has_api_key" size="small" :type="row.extra_config?.source === 'environment' ? 'warning' : 'success'" class="ml">
                {{ row.extra_config?.source === 'environment' ? 'ENV' : 'DB' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="支持功能" min-width="200">
            <template #default="{ row }">
              <el-tag v-for="f in row.supported_features || []" :key="f" size="small" class="mr">{{ f }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openProvider(row)">编辑</el-button>
              <el-button v-if="row.extra_config?.has_api_key" size="small" type="info" :loading="testing === row.name" @click="testProvider(row)">测试</el-button>
              <el-button size="small" :type="row.is_active ? 'warning' : 'success'" @click="toggleProvider(row)">{{ row.is_active ? '禁用' : '启用' }}</el-button>
              <el-button size="small" type="danger" @click="removeProvider(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="模型目录" name="catalog">
        <div class="toolbar">
          <h3>模型目录管理</h3>
          <el-button type="primary" @click="openCatalog()">添加厂家模型目录</el-button>
        </div>
        <el-alert title="说明" type="info" :closable="false" show-icon style="margin-bottom: 16px">
          模型目录用于在添加大模型配置时提供可选的模型列表。
        </el-alert>
        <el-table :data="catalogs" v-loading="loading.catalogs" border>
          <el-table-column prop="provider" label="厂家标识" width="140" />
          <el-table-column prop="provider_name" label="厂家名称" width="160" />
          <el-table-column label="模型数量" width="120">
            <template #default="{ row }">
              <el-tag>{{ (row.models || []).length }} 个模型</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="模型列表">
            <template #default="{ row }">
              <el-tag v-for="m in (row.models || []).slice(0, 3)" :key="m.name" size="small" class="mr">{{ m.display_name || m.name }}</el-tag>
              <span v-if="(row.models || []).length > 3">... 还有 {{ row.models.length - 3 }} 个</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="openCatalog(row)">编辑</el-button>
              <el-button type="danger" size="small" @click="removeCatalog(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="大模型配置" name="models">
        <div class="toolbar">
          <h3>大模型配置</h3>
          <el-button type="primary" @click="openModel()">添加模型</el-button>
        </div>
        <el-empty v-if="modelGroups.length === 0" description="暂无大模型配置">
          <el-button type="primary" @click="openModel()">添加第一个模型</el-button>
        </el-empty>
        <div v-for="group in modelGroups" :key="group.provider" class="provider-group">
          <div class="provider-header">
            <div>
              <el-tag type="primary" size="large">{{ group.display_name }}</el-tag>
              <span class="muted"> {{ group.models.length }} 个模型 </span>
              <el-tag :type="group.is_active ? 'success' : 'danger'" size="small">{{ group.is_active ? '已启用' : '已禁用' }}</el-tag>
            </div>
            <div>
              <el-button size="small" type="primary" @click="openModelForProvider(group.provider)">添加模型</el-button>
              <el-button size="small" :type="group.is_active ? 'warning' : 'success'" @click="toggleProviderByName(group.provider, !group.is_active)">
                {{ group.is_active ? '禁用' : '启用' }}
              </el-button>
            </div>
          </div>
          <el-table :data="group.models" stripe>
            <el-table-column label="模型名称" min-width="180">
              <template #default="{ row }">
                <div class="name">{{ row.model_display_name || row.model_name }}</div>
                <div class="muted">{{ row.model_name }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'danger'" size="small">{{ row.enabled ? '启用' : '禁用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="基础配置" width="200">
              <template #default="{ row }">
                <div>Token: {{ row.max_tokens }}</div>
                <div class="muted">温度: {{ row.temperature }} | 超时: {{ row.timeout }}s</div>
              </template>
            </el-table-column>
            <el-table-column label="模型能力" min-width="220">
              <template #default="{ row }">
                <el-tag v-if="row.capability_level" type="danger" size="small" class="mr">{{ row.capability_level }}级</el-tag>
                <el-tag v-for="role in row.suitable_roles || []" :key="role" type="info" size="small" class="mr">{{ roleLabel(role) }}</el-tag>
                <el-tag v-for="d in row.recommended_depths || []" :key="d" type="success" size="small" class="mr">{{ d }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openModel(row)">编辑</el-button>
                <el-button size="small" type="primary" :loading="testing === row.model_name" @click="testModel(row)">测试</el-button>
                <el-button size="small" :type="row.enabled ? 'warning' : 'success'" @click="toggleModel(row)">{{ row.enabled ? '禁用' : '启用' }}</el-button>
                <el-button size="small" type="danger" @click="removeModel(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Agent 模型配置" name="agents">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
          仅可选择已启用且厂家已配置密钥的模型。Agent3 与「助手」页面共用同一模型，任一处修改都会同步。
        </el-alert>
        <el-empty v-if="enabledGroups.length === 0" description="暂无可用模型，请先在厂家管理中配置密钥并启用模型" />
        <el-form v-else :model="agentForm" label-width="160px" style="max-width: 640px">
          <el-form-item label="Agent1 影像理解">
            <el-select v-model="agentForm.agent1" filterable clearable placeholder="选择视觉模型" style="width: 100%" @change="saveAgent">
              <el-option-group v-for="group in enabledGroups" :key="group.provider" :label="group.display_name">
                <el-option
                  v-for="item in group.models"
                  :key="item.id"
                  :label="modelOptionLabel(item, true)"
                  :value="item.id"
                />
              </el-option-group>
            </el-select>
            <div class="hint">建议选择带 vision 能力的模型，用于照片内容识别。</div>
          </el-form-item>
          <el-form-item label="Agent2 推荐顾问">
            <el-select v-model="agentForm.agent2" filterable clearable placeholder="选择推荐模型" style="width: 100%" @change="saveAgent">
              <el-option-group v-for="group in enabledGroups" :key="group.provider" :label="group.display_name">
                <el-option
                  v-for="item in group.models"
                  :key="item.id"
                  :label="item.model_display_name"
                  :value="item.id"
                />
              </el-option-group>
            </el-select>
            <div class="hint">用于远距离地点与天气建议。</div>
          </el-form-item>
          <el-form-item label="Agent3 助手">
            <el-select v-model="agentForm.agent3" filterable clearable placeholder="选择对话模型" style="width: 100%" @change="saveAgent">
              <el-option-group v-for="group in enabledGroups" :key="group.provider" :label="group.display_name">
                <el-option
                  v-for="item in group.models"
                  :key="item.id"
                  :label="item.model_display_name"
                  :value="item.id"
                />
              </el-option-group>
            </el-select>
            <div class="hint">与助手页面聊天栏同步。</div>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="系统" name="system">
        <el-form :model="sys" label-width="160px" style="max-width: 520px">
          <el-form-item label="远距离阈值 (km)">
            <el-input-number v-model="sys.distance_threshold_km" :min="5" :max="5000" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveSys">保存</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="providerDialog" :title="editingProvider ? '编辑厂家信息' : '添加厂家'" width="560px">
      <el-form :model="providerForm" label-width="120px">
        <el-form-item label="厂家ID"><el-input v-model="providerForm.name" :disabled="!!editingProvider" /></el-form-item>
        <el-form-item label="显示名称"><el-input v-model="providerForm.display_name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="providerForm.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="默认API地址"><el-input v-model="providerForm.default_base_url" /></el-form-item>
        <el-form-item label="测试模型"><el-input v-model="providerForm.test_model" /></el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="providerForm.api_key" type="password" show-password placeholder="已配置的密钥会显示在此；留空保存则保持不变" />
        </el-form-item>
        <el-form-item label="支持功能">
          <el-checkbox-group v-model="providerForm.supported_features">
            <el-checkbox v-for="f in featureOptions" :key="f" :label="f">{{ f }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="状态"><el-switch v-model="providerForm.is_active" active-text="启用" inactive-text="禁用" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDialog = false">取消</el-button>
        <el-button type="primary" @click="saveProvider">{{ editingProvider ? '更新' : '添加' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="catalogDialog" :title="editingCatalog ? '编辑模型目录' : '添加模型目录'" width="720px">
      <el-form :model="catalogForm" label-width="100px">
        <el-form-item label="厂家">
          <el-select v-model="catalogForm.provider" :disabled="!!editingCatalog" filterable @change="onCatalogProvider">
            <el-option v-for="p in providers" :key="p.name" :label="`${p.display_name} (${p.name})`" :value="p.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="厂家名称"><el-input v-model="catalogForm.provider_name" /></el-form-item>
        <el-form-item label="模型列表">
          <div v-for="(m, idx) in catalogForm.models" :key="idx" class="model-row">
            <el-input v-model="m.name" placeholder="模型代码" />
            <el-input v-model="m.display_name" placeholder="显示名称" />
            <el-button type="danger" text @click="catalogForm.models.splice(idx, 1)">删除</el-button>
          </div>
          <el-button @click="catalogForm.models.push({ name: '', display_name: '' })">添加一行</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="catalogDialog = false">取消</el-button>
        <el-button type="primary" @click="saveCatalog">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="modelDialog" :title="editingModel ? '编辑大模型配置' : '添加大模型配置'" width="600px">
      <el-form :model="modelForm" label-width="120px">
        <el-form-item label="供应商">
          <el-select v-model="modelForm.provider" filterable>
            <el-option v-for="p in providers" :key="p.name" :label="p.display_name" :value="p.name" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="catalogOptions.length" label="选择模型">
          <el-select v-model="pickedCatalogModel" filterable clearable @change="applyCatalogModel">
            <el-option v-for="m in catalogOptions" :key="m.name" :label="m.display_name" :value="m.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名称"><el-input v-model="modelForm.model_display_name" /></el-form-item>
        <el-form-item label="模型代码"><el-input v-model="modelForm.model_name" :disabled="!!editingModel" /></el-form-item>
        <el-form-item label="最大 Token"><el-input-number v-model="modelForm.max_tokens" :min="100" :max="128000" :step="100" /></el-form-item>
        <el-form-item label="温度"><el-input-number v-model="modelForm.temperature" :min="0" :max="2" :step="0.1" :precision="1" /></el-form-item>
        <el-form-item label="超时(秒)"><el-input-number v-model="modelForm.timeout" :min="10" :max="300" /></el-form-item>
        <el-form-item label="能力等级"><el-input-number v-model="modelForm.capability_level" :min="1" :max="5" /></el-form-item>
        <el-form-item label="角色">
          <el-checkbox-group v-model="modelForm.suitable_roles">
            <el-checkbox label="vision">视觉 / Agent1</el-checkbox>
            <el-checkbox label="assistant">助手 / Agent2-3</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="特性">
          <el-checkbox-group v-model="modelForm.features">
            <el-checkbox label="vision">vision</el-checkbox>
            <el-checkbox label="chat">chat</el-checkbox>
            <el-checkbox label="function_calling">function_calling</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="modelForm.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialog = false">取消</el-button>
        <el-button type="primary" @click="saveModel">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { configApi } from '@/api/photos'
import { llmApi as api, parseModelId, toModelId, type CatalogModel, type EnabledLLMModel, type LLMModel as M, type LLMProvider as P, type ModelCatalog as C } from '@/api/llm'

const tab = ref('providers')
const reloading = ref(false)
const testing = ref('')
const loading = reactive({ providers: false, catalogs: false, models: false })
const providers = ref<P[]>([])
const catalogs = ref<C[]>([])
const models = ref<M[]>([])
const enabledModels = ref<EnabledLLMModel[]>([])
const sys = reactive({ distance_threshold_km: 50 })
const agentForm = reactive({ agent1: '', agent2: '', agent3: '' })
const featureOptions = ['chat', 'completion', 'embedding', 'image', 'vision', 'function_calling', 'streaming']

const providerDialog = ref(false)
const catalogDialog = ref(false)
const modelDialog = ref(false)
const editingProvider = ref<P | null>(null)
const editingCatalog = ref<C | null>(null)
const editingModel = ref<M | null>(null)
const providerForm = reactive<P>({ name: '', display_name: '', description: '', default_base_url: '', test_model: '', api_key: '', is_active: true, supported_features: ['chat'] })
const catalogForm = reactive<C>({ provider: '', provider_name: '', models: [{ name: '', display_name: '' }] })
const modelForm = reactive<M>({ provider: '', model_name: '', model_display_name: '', max_tokens: 8000, temperature: 0.2, timeout: 120, enabled: true, capability_level: 3, suitable_roles: [], features: [], recommended_depths: ['标准'] })
const pickedCatalogModel = ref('')

const modelGroups = computed(() => {
  const map = new Map<string, { provider: string; display_name: string; is_active: boolean; models: M[] }>()
  for (const item of models.value) {
    const provider = providers.value.find((p) => p.name === item.provider)
    if (!map.has(item.provider)) {
      map.set(item.provider, {
        provider: item.provider,
        display_name: provider?.display_name || item.provider,
        is_active: provider?.is_active !== false,
        models: []
      })
    }
    map.get(item.provider)!.models.push(item)
  }
  return Array.from(map.values())
})

const catalogOptions = computed<CatalogModel[]>(() => {
  const found = catalogs.value.find((c) => c.provider === modelForm.provider)
  return found?.models || []
})

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

const modelOptionLabel = (item: EnabledLLMModel, markVision = false) => {
  const vision = item.features?.includes('vision') || item.suitable_roles?.includes('vision')
  return markVision && vision ? `${item.model_display_name} · 视觉` : item.model_display_name
}

const roleLabel = (role: string) => ({ vision: '视觉', assistant: '助手', both: '全能型' }[role] || role)
const formatTime = (value?: string) => (value ? value.replace('T', ' ').slice(0, 19) : '-')

const loadAll = async () => {
  loading.providers = true
  const [p, c, m, cfg, enabled] = await Promise.all([
    api.providers(),
    api.catalogs(),
    api.models(),
    configApi.get(),
    api.enabledModels()
  ])
  providers.value = p.data || []
  catalogs.value = c.data || []
  models.value = m.data || []
  enabledModels.value = enabled.data || []
  if (cfg.data?.distance_threshold_km) sys.distance_threshold_km = cfg.data.distance_threshold_km
  const agents = cfg.data?.agent_models || {}
  agentForm.agent1 = pickEnabledId(agents.agent1)
  agentForm.agent2 = pickEnabledId(agents.agent2)
  agentForm.agent3 = pickEnabledId(agents.agent3)
  loading.providers = false
}

const pickEnabledId = (binding?: { provider?: string; model_name?: string }) => {
  const id = toModelId(binding?.provider, binding?.model_name)
  return enabledModels.value.some((item) => item.id === id) ? id : ''
}

const saveAgent = async () => {
  await configApi.update({
    agent_models: {
      agent1: parseModelId(agentForm.agent1),
      agent2: parseModelId(agentForm.agent2),
      agent3: parseModelId(agentForm.agent3)
    }
  })
  ElMessage.success('已保存 Agent 模型')
}

const reload = async () => {
  reloading.value = true
  try {
    await api.reload()
    await loadAll()
    ElMessage.success('已重载配置')
  } finally {
    reloading.value = false
  }
}

const openProvider = (row?: any) => {
  editingProvider.value = row || null
  Object.assign(providerForm, {
    name: row?.name || '',
    display_name: row?.display_name || '',
    description: row?.description || '',
    default_base_url: row?.default_base_url || '',
    test_model: row?.test_model || '',
    api_key: row?.api_key || '',
    is_active: row?.is_active ?? true,
    supported_features: [...(row?.supported_features || ['chat'])]
  })
  providerDialog.value = true
}

const saveProvider = async () => {
  const payload = { ...providerForm }
  if (!payload.api_key) delete (payload as any).api_key
  if (editingProvider.value) await api.updateProvider(editingProvider.value.name, payload)
  else await api.addProvider(payload)
  providerDialog.value = false
  ElMessage.success('已保存厂家')
  await loadAll()
}

const testProvider = async (row: any) => {
  testing.value = row.name
  try {
    const res = await api.testProvider(row.name)
    ElMessage.success(res.message || '连接成功')
  } finally {
    testing.value = ''
  }
}

const toggleProvider = async (row: any) => {
  await api.toggleProvider(row.name, !row.is_active)
  await loadAll()
}

const toggleProviderByName = async (name: string, is_active: boolean) => {
  await api.toggleProvider(name, is_active)
  await loadAll()
}

const removeProvider = async (row: any) => {
  await ElMessageBox.confirm(`确定删除厂家 ${row.display_name} 吗？`, '删除')
  await api.deleteProvider(row.name)
  await loadAll()
}

const openCatalog = (row?: any) => {
  editingCatalog.value = row || null
  catalogForm.provider = row?.provider || ''
  catalogForm.provider_name = row?.provider_name || ''
  catalogForm.models = row?.models?.length ? row.models.map((m: CatalogModel) => ({ ...m })) : [{ name: '', display_name: '' }]
  catalogDialog.value = true
}

const onCatalogProvider = (name: string) => {
  const found = providers.value.find((p) => p.name === name)
  if (found) catalogForm.provider_name = found.display_name
}

const saveCatalog = async () => {
  await api.saveCatalog({
    provider: catalogForm.provider,
    provider_name: catalogForm.provider_name,
    models: catalogForm.models.filter((m) => m.name)
  })
  catalogDialog.value = false
  ElMessage.success('已保存目录')
  await loadAll()
}

const removeCatalog = async (row: any) => {
  await ElMessageBox.confirm(`确定删除厂家 ${row.provider_name} 的模型目录吗？`, '删除')
  await api.deleteCatalog(row.provider)
  await loadAll()
}

const openModelForProvider = (provider: string) => {
  openModel({ provider })
}

const openModel = (row?: Partial<M>) => {
  editingModel.value = (row && row.model_name ? row : null) as M | null
  Object.assign(modelForm, {
    provider: row?.provider || providers.value[0]?.name || '',
    model_name: row?.model_name || '',
    model_display_name: row?.model_display_name || '',
    max_tokens: row?.max_tokens || 8000,
    temperature: row?.temperature ?? 0.2,
    timeout: row?.timeout || 120,
    enabled: row?.enabled ?? true,
    capability_level: row?.capability_level || 3,
    suitable_roles: [...(row?.suitable_roles || [])],
    features: [...(row?.features || [])],
    recommended_depths: [...(row?.recommended_depths || ['标准'])]
  })
  pickedCatalogModel.value = row?.model_name || ''
  modelDialog.value = true
}

const applyCatalogModel = (name: string) => {
  const found = catalogOptions.value.find((m) => m.name === name)
  if (!found) return
  modelForm.model_name = found.name
  modelForm.model_display_name = found.display_name
}

const saveModel = async () => {
  await api.saveModel(modelForm)
  modelDialog.value = false
  ElMessage.success('已保存模型')
  await loadAll()
}

const testModel = async (row: any) => {
  testing.value = row.model_name
  try {
    const res = await api.testModel(row.provider, row.model_name)
    ElMessage.success(res.message || '模型可用')
  } finally {
    testing.value = ''
  }
}

const toggleModel = async (row: any) => {
  await api.toggleModel(row.provider, row.model_name, !row.enabled)
  await loadAll()
}

const removeModel = async (row: any) => {
  await ElMessageBox.confirm(`确定删除模型 ${row.model_display_name || row.model_name} 吗？`, '删除')
  await api.deleteModel(row.provider, row.model_name)
  await loadAll()
}

const saveSys = async () => {
  await configApi.update({ distance_threshold_km: sys.distance_threshold_km })
  ElMessage.success('已保存')
}

onMounted(loadAll)
</script>

<style scoped lang="scss">
.sub { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar h3 { margin: 0; }
.name { font-weight: 600; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.mr { margin-right: 4px; margin-bottom: 4px; }
.ml { margin-left: 4px; }
.provider-group { margin-bottom: 20px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; overflow: hidden; }
.provider-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: var(--el-fill-color-light); }
.model-row { display: flex; gap: 8px; margin-bottom: 8px; }
.hint { margin-top: 6px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.4; }
</style>
