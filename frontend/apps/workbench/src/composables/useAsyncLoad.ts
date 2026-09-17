import { ref } from 'vue'

/** 页面级加载：统一 loading / error，避免每个视图手写同一套 try/finally。 */
export function useAsyncLoad() {
  const loading = ref(false)
  const error = ref('')

  async function run(task: () => Promise<void>) {
    loading.value = true
    try {
      await task()
      error.value = ''
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  return { loading, error, run }
}
