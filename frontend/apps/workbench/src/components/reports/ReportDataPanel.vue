<script setup lang="ts">
import { MOCK_METRICS } from '@/services/reportMock'

defineEmits<{
  chart: []
  table: []
}>()
</script>

<template>
  <div class="data-panel">
    <p class="data-panel__hint">
      数据助手将承接财务指标、同比环比、结构化表格与图表生成。当前为 UI + mock。
    </p>
    <el-table :data="MOCK_METRICS" size="small" stripe>
      <el-table-column prop="name" label="指标" min-width="120" />
      <el-table-column prop="current" label="本期" width="88" />
      <el-table-column prop="previous" label="上年" width="88" />
      <el-table-column prop="yoy" label="同比" width="80" />
    </el-table>
    <div class="data-panel__actions">
      <el-button @click="$emit('table')">插入指标表</el-button>
      <el-button type="primary" plain @click="$emit('chart')">生成趋势图</el-button>
    </div>
  </div>
</template>

<style scoped>
.data-panel {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  gap: 12px;
}
.data-panel__hint {
  margin: 0;
  color: var(--cc-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.data-panel__actions {
  display: flex;
  gap: 8px;
}
</style>
