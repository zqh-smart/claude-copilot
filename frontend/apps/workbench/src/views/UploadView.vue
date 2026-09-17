<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import PageToolbar from '@/components/PageToolbar.vue'
import { uploadDocumentAsync, type IngestionJob } from '@/api/http'

const router = useRouter()
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const submitting = ref(false)
const submitted = ref<IngestionJob | null>(null)
const form = reactive({
  company: '',
  year: '',
  doc_type: 'annual_report',
  industry: '',
  company_aliases: '',
  source: 'workbench_upload',
})

const accepted = '.pdf,.doc,.docx,.xls,.xlsx,.csv,.html,.htm,.md,.txt,.ppt,.pptx'

function selectFile(event: Event) {
  takeFile((event.target as HTMLInputElement).files?.[0])
}

function chooseFile() {
  fileInput.value?.click()
}

function takeFile(next: File | undefined) {
  if (!next) return
  file.value = next
  submitted.value = null
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  takeFile(event.dataTransfer?.files?.[0])
}

async function submit() {
  if (!file.value) {
    ElMessage.warning('请先选择文档')
    return
  }
  submitting.value = true
  try {
    submitted.value = await uploadDocumentAsync(file.value, { ...form })
    ElMessage.success('文档已进入异步处理队列')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '上传失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="cc-page">
    <PageToolbar kicker="文档入库" subtitle="提交后进入解析、清洗、结构化、切片、索引与图谱流水线。">
      <el-button @click="router.push('/jobs')">查看任务队列</el-button>
    </PageToolbar>

    <div class="upload-grid">
      <el-card shadow="never">
        <template #header><strong>选择文件</strong></template>
        <input ref="fileInput" type="file" :accept="accepted" hidden @change="selectFile" />
        <button
          class="drop-zone"
          type="button"
          @click="chooseFile"
          @dragover.prevent
          @drop="onDrop"
        >
          <el-icon size="34"><UploadFilled /></el-icon>
          <strong>{{ file?.name || '拖入或点击选择文档' }}</strong>
          <span>{{ file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : accepted }}</span>
        </button>
        <el-alert
          title="年报建议补充公司、年份和行业信息，可提升结构化事实与图谱实体质量。"
          type="info"
          show-icon
          :closable="false"
          class="upload-tip"
        />
      </el-card>

      <el-card shadow="never">
        <template #header><strong>文档元数据</strong></template>
        <el-form label-position="top">
          <el-form-item label="公司名称"><el-input v-model="form.company" placeholder="例如：北京指南针科技发展股份有限公司" /></el-form-item>
          <div class="form-columns">
            <el-form-item label="报告年份"><el-input v-model="form.year" inputmode="numeric" placeholder="2025" /></el-form-item>
            <el-form-item label="文档类型">
              <el-select v-model="form.doc_type">
                <el-option label="年度报告" value="annual_report" />
                <el-option label="财务报告" value="financial_report" />
                <el-option label="公司公告" value="announcement" />
                <el-option label="行业研报" value="research_report" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="所属行业"><el-input v-model="form.industry" placeholder="例如：金融信息服务" /></el-form-item>
          <el-form-item label="公司别名"><el-input v-model="form.company_aliases" placeholder="多个别名使用逗号分隔" /></el-form-item>
          <el-button type="primary" size="large" :loading="submitting" :disabled="!file" class="submit-upload" @click="submit">提交异步处理</el-button>
        </el-form>
      </el-card>
    </div>

    <el-result v-if="submitted" icon="success" title="任务已创建" :sub-title="submitted.filename">
      <template #extra>
        <el-space>
          <el-tag>{{ submitted.status }} · {{ submitted.stage }}</el-tag>
          <el-button type="primary" @click="router.push('/jobs')">跟踪任务 {{ submitted.job_id.slice(0, 10) }}</el-button>
        </el-space>
      </template>
    </el-result>
  </section>
</template>
