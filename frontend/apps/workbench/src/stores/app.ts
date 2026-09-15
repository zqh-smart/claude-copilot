import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    collapsed: false,
  }),
  actions: {
    toggleSidebar() {
      this.collapsed = !this.collapsed
    },
  },
})
