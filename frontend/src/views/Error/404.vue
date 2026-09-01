<template>
  <el-result icon="warning" title="页面不存在" sub-title="请检查地址或返回图库">
    <template #extra>
      <el-button type="primary" @click="$router.push('/gallery')">回到图库</el-button>
    </template>
  </el-result>
</template>
