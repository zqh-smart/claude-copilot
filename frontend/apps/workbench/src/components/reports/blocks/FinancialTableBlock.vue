<script setup lang="ts">
/**
 * Financial tables are native Tiptap tables so cells stay editable.
 * This wrapper exists for future specialized numeric formatting.
 */
defineProps<{
  caption?: string
}>()
</script>

<template>
  <figure class="financial-table-block">
    <figcaption v-if="caption">{{ caption }}</figcaption>
    <slot />
  </figure>
</template>
