<template>
  <div class="studio">
    <el-result icon="info" title="自媒体工作台" sub-title="该功能将在后续版本完善。当前仅提供入口页面。">
      <template #extra>
        <p class="hint">规划中的能力：根据相册与标签生成文案、选题、发布日历；由助手 Agent 协助创作。</p>
        <el-button type="primary" @click="$router.push('/chat')">去问助手</el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.studio {
  min-height: 480px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hint {
  color: var(--el-text-color-secondary);
  max-width: 480px;
  margin: 0 auto 16px;
}
</style>
