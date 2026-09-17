<script setup lang="ts">
import PageToolbar from '@/components/PageToolbar.vue'

defineProps<{ title: string; description: string }>()
</script>

<template>
  <section class="cc-page">
    <PageToolbar kicker="待接入" :subtitle="description">
      <el-tag type="warning" effect="plain">{{ title }}</el-tag>
    </PageToolbar>
    <el-empty description="该页面将在后续迁移批次接入现有 FastAPI / LangGraph 契约">
      <el-button type="primary" @click="$router.push('/')">返回工作台</el-button>
    </el-empty>
  </section>
</template>
