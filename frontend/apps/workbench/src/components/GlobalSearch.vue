<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'

export interface SearchEntry {
  path: string
  title: string
  group: string
  keywords?: string[]
}

const props = defineProps<{
  entries: SearchEntry[]
}>()

const emit = defineEmits<{
  navigate: [entry: SearchEntry]
}>()

const router = useRouter()
const open = ref(false)
const query = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

const filtered = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return props.entries.slice(0, 8)
  return props.entries.filter((item) => {
    const hay = [item.title, item.group, item.path, ...(item.keywords || [])].join(' ').toLowerCase()
    return hay.includes(term)
  })
})

watch(query, () => {
  activeIndex.value = 0
})

function openPalette() {
  open.value = true
  activeIndex.value = 0
  requestAnimationFrame(() => inputRef.value?.focus())
}

function closePalette() {
  open.value = false
  query.value = ''
  activeIndex.value = 0
}

function go(entry: SearchEntry) {
  if (entry.path.startsWith('__')) {
    emit('navigate', entry)
  } else {
    void router.push(entry.path)
  }
  closePalette()
}

function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    if (open.value) closePalette()
    else openPalette()
    return
  }
  if (!open.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closePalette()
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, Math.max(filtered.value.length - 1, 0))
    return
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
    return
  }
  if (event.key === 'Enter' && filtered.value[activeIndex.value]) {
    event.preventDefault()
    go(filtered.value[activeIndex.value])
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="global-search">
    <button type="button" class="global-search__trigger" @click="openPalette">
      <el-icon><Search /></el-icon>
      <span class="global-search__placeholder">搜索页面、功能…</span>
      <kbd class="global-search__kbd">{{ isMac ? '⌘' : 'Ctrl' }} K</kbd>
    </button>

    <Teleport to="body">
      <div v-if="open" class="global-search__backdrop" @click="closePalette" />
      <div v-if="open" class="global-search__panel" role="dialog" aria-label="全局搜索">
        <div class="global-search__input-wrap">
          <el-icon class="global-search__input-icon"><Search /></el-icon>
          <input
            ref="inputRef"
            v-model="query"
            class="global-search__input"
            type="search"
            placeholder="搜索页面、功能…"
            autocomplete="off"
          />
          <kbd class="global-search__kbd global-search__kbd--sm">Esc</kbd>
        </div>

        <ul v-if="filtered.length" class="global-search__results">
          <li
            v-for="(item, idx) in filtered"
            :key="item.path"
            class="global-search__item"
            :class="{ 'global-search__item--active': idx === activeIndex }"
            @click="go(item)"
            @mouseenter="activeIndex = idx"
          >
            <span class="global-search__item-title">{{ item.title }}</span>
            <span class="global-search__item-group">{{ item.group }}</span>
          </li>
        </ul>
        <p v-else class="global-search__empty">未找到匹配项</p>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.global-search {
  display: flex;
  align-items: center;
}

.global-search__trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 280px;
  max-width: 36vw;
  padding: 9px 14px;
  border: 1px solid var(--cc-border-light);
  border-radius: 12px;
  background: linear-gradient(135deg, #ffffff 0%, var(--cc-bg-subtle) 100%);
  color: var(--cc-text-muted);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.global-search__trigger:hover {
  border-color: var(--cc-brand-muted);
  background: linear-gradient(135deg, #ffffff 0%, var(--cc-brand-soft) 100%);
  box-shadow: var(--cc-shadow-xs);
}

.global-search__placeholder {
  flex: 1;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-search__kbd {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border: 1px solid var(--cc-border-color);
  border-radius: 6px;
  background: #fff;
  color: var(--cc-text-secondary);
  font-family: inherit;
  font-size: 11px;
  line-height: 1.4;
}

.global-search__kbd--sm {
  padding: 2px 6px;
  font-size: 10px;
}

.global-search__backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgb(18 36 29 / 35%);
  backdrop-filter: blur(2px);
}

.global-search__panel {
  position: fixed;
  z-index: 2001;
  top: 18%;
  left: 50%;
  width: min(520px, calc(100vw - 32px));
  padding: 12px;
  border: 1px solid var(--cc-border-light);
  border-radius: 16px;
  background: #fff;
  box-shadow: var(--cc-shadow-md);
  transform: translateX(-50%);
}

.global-search__input-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 12px;
  border-bottom: 1px solid var(--cc-border-light);
}

.global-search__input-icon {
  color: var(--cc-text-muted);
  font-size: 18px;
}

.global-search__input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--cc-text-primary);
  font-family: inherit;
  font-size: 15px;
}

.global-search__results {
  max-height: 320px;
  margin: 8px 0 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.global-search__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.12s;
}

.global-search__item--active,
.global-search__item:hover {
  background: var(--cc-brand-soft);
}

.global-search__item-title {
  color: var(--cc-text-primary);
  font-size: 14px;
  font-weight: 500;
}

.global-search__item-group {
  flex-shrink: 0;
  color: var(--cc-text-muted);
  font-size: 12px;
}

.global-search__empty {
  margin: 16px 8px;
  color: var(--cc-text-muted);
  font-size: 13px;
  text-align: center;
}

@media (max-width: 768px) {
  .global-search__trigger {
    width: 44px;
    justify-content: center;
    padding: 9px;
  }

  .global-search__placeholder,
  .global-search__kbd {
    display: none;
  }
}
</style>
