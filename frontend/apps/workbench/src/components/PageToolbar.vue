<script setup lang="ts">
defineProps<{
  kicker?: string
  subtitle: string
}>()
</script>

<template>
  <div class="cc-page-toolbar">
    <div>
      <p v-if="kicker" class="cc-page-kicker">{{ kicker }}</p>
      <p class="cc-page-sub">{{ subtitle }}</p>
    </div>
    <div class="cc-page-actions">
      <slot />
    </div>
  </div>
</template>
