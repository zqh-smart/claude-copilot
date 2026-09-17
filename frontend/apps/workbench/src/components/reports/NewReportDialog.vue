<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import type { ReportLanguage, ReportLength, ReportType } from '@/types/report'
import { PRODUCT_TEMPLATES } from '@/types/report'
import ReportSourceSelector from '@/components/reports/ReportSourceSelector.vue'
import ReportTemplateSelector from '@/components/reports/ReportTemplateSelector.vue'
import { useWorkspaceStore } from '@/stores/workspace'

const open = defineModel<boolean>({ default: false })

const emit = defineEmits<{
  create: [payload: {
    type: ReportType
    templateId: string
    company: string
    sourceIds: string[]
    prompt: string
    language: ReportLanguage
    length: ReportLength
  }]
}>()

const workspace = useWorkspaceStore()
const { documents } = storeToRefs(workspace)
const step = ref(0)
const reportType = ref<ReportType>('earnings')
const company = ref('宁德时代')
const sourceIds = ref<string[]>([])
const prompt = ref('重点分析：盈利能力、现金流、海外业务、风险因素')
const language = ref<ReportLanguage>('zh')
const length = ref<ReportLength>('standard')
const creating = ref(false)

const backendTemplateId = computed(
  () => PRODUCT_TEMPLATES.find((item) => item.id === reportType.value)?.backendTemplateId || 'comprehensive_financial',
)

watch(open, async (value) => {
  if (!value) return
  step.value = 0
  creating.value = false
  await workspace.ensureDocuments().catch(() => undefined)
})

async function submit() {
  creating.value = true
  emit('create', {
    type: reportType.value,
    templateId: backendTemplateId.value,
    company: company.value.trim(),
    sourceIds: sourceIds.value,
    prompt: prompt.value.trim(),
    language: language.value,
    length: length.value,
  })
}
</script>

<template>
  <el-drawer v-model="open" title="新建金融报告" size="520px" destroy-on-close>
    <el-steps :active="step" simple>
      <el-step title="模板" />
      <el-step title="对象" />
      <el-step title="材料" />
      <el-step title="重点" />
      <el-step title="创建" />
    </el-steps>

    <div class="new-report-body">
      <section v-show="step === 0">
        <h3>选择报告模板</h3>
        <ReportTemplateSelector v-model="reportType" />
      </section>
      <section v-show="step === 1">
        <h3>研究对象</h3>
        <el-input v-model="company" placeholder="例如：宁德时代" />
      </section>
      <section v-show="step === 2">
        <h3>选择研究材料</h3>
        <ReportSourceSelector :documents="documents" v-model:selected-ids="sourceIds" />
      </section>
      <section v-show="step === 3">
        <h3>重点关注</h3>
        <el-input v-model="prompt" type="textarea" :rows="5" maxlength="2000" show-word-limit />
        <div class="new-report-advanced">
          <span>高级设置</span>
          <el-radio-group v-model="language" size="small">
            <el-radio-button value="zh">中文</el-radio-button>
            <el-radio-button value="en">English</el-radio-button>
          </el-radio-group>
          <el-radio-group v-model="length" size="small">
            <el-radio-button value="brief">精简</el-radio-button>
            <el-radio-button value="standard">标准</el-radio-button>
            <el-radio-button value="long">详细</el-radio-button>
          </el-radio-group>
        </div>
      </section>
      <section v-show="step === 4">
        <h3>确认创建</h3>
        <p>将立即打开在线文档。若后端生成可用，会写入初稿；否则先进入本地可编辑文档并逐章生成。</p>
        <ul>
          <li>模板：{{ PRODUCT_TEMPLATES.find((item) => item.id === reportType)?.name }}</li>
          <li>对象：{{ company || '未填写' }}</li>
          <li>材料：{{ sourceIds.length }} 份</li>
        </ul>
      </section>
    </div>

    <template #footer>
      <el-button v-if="step > 0" @click="step -= 1">上一步</el-button>
      <el-button v-if="step < 4" type="primary" @click="step += 1">下一步</el-button>
      <el-button v-else type="primary" :loading="creating" @click="submit">创建报告</el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.new-report-body {
  padding-top: 18px;
}
.new-report-body h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.new-report-body p,
.new-report-body li {
  color: var(--cc-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.new-report-advanced {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-top: 14px;
}
.new-report-advanced span {
  color: var(--cc-text-muted);
  font-size: 12px;
}
</style>
