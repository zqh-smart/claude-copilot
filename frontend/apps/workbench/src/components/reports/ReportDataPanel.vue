<template>
  <div class="data-panel">
    <p class="data-panel__hint">
      数据助手将在下一阶段接入结构化财务指标。当前不展示示例指标，也不会向正文插入模拟数据。
    </p>
    <el-empty :image-size="56" description="暂无已连接的数据查询" />
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
</style>
