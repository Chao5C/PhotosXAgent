<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <img src="/logo.svg" alt="PhotosXAgent" class="logo" />
        <h1>PhotosXAgent</h1>
        <p>多智能体图片管理 · 行程模拟 · 智能相册</p>
      </div>
      <el-card shadow="always">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" prefix-icon="User" placeholder="请输入用户名" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password prefix-icon="Lock" placeholder="请输入密码" @keyup.enter="handleLogin" />
          </el-form-item>
          <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleLogin">登录</el-button>
          <p class="tip">默认账号：admin / admin123</p>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: 'admin', password: 'admin123' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  await formRef.value?.validate()
  loading.value = true
  const ok = await authStore.login(form)
  loading.value = false
  if (ok) {
    ElMessage.success('登录成功')
    router.push(authStore.getAndClearRedirectPath())
  } else {
    ElMessage.error('用户名或密码错误')
  }
}
</script>

<style scoped lang="scss">
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #3a7bd5 0%, #00d2ff 100%);
  padding: 24px;
}
.login-container { width: 100%; max-width: 400px; }
.login-header {
  text-align: center;
  color: #fff;
  margin-bottom: 24px;
  .logo { width: 64px; height: 64px; }
  h1 { margin: 12px 0 6px; }
  p { opacity: 0.9; margin: 0; }
}
.tip { text-align: center; color: var(--el-text-color-secondary); margin: 16px 0 0; }
</style>
