<script setup lang="ts">
defineProps<{ title: string; description: string }>()
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div><p class="eyebrow">MIGRATION IN PROGRESS</p><h1>{{ title }}</h1><p>{{ description }}</p></div>
      <el-tag type="warning" effect="plain">待迁移</el-tag>
    </div>
    <el-empty description="该页面将在后续迁移批次接入现有 FastAPI / LangGraph 契约">
      <el-button type="primary" @click="$router.push('/')">返回工作台</el-button>
    </el-empty>
  </section>
</template>
