import { defineStore } from 'pinia'

/**
 * 处置概览看板的视图状态。
 * 从看板进详情再返回时，直接还原离开时的筛选条件与件数快照，
 * 避免重新拉取导致“同一份件数”发生跳动；详情页若推进过状态，
 * 会打上 stale 标记，看板回来后在后台静默刷新。
 */
export type BoardFilters = {
  crew: string
  start: string
  end: string
}

type BoardPayload = Record<string, unknown>

export const useEmergencyStore = defineStore('emergency', {
  state: () => ({
    filters: { crew: '', start: '', end: '' } as BoardFilters,
    snapshot: null as BoardPayload | null,
    loaded: false,
    stale: false,
  }),
  actions: {
    setFilters(filters: BoardFilters) {
      this.filters = { ...filters }
    },
    setSnapshot(payload: BoardPayload) {
      this.snapshot = payload
      this.loaded = true
      this.stale = false
    },
    markStale() {
      this.stale = true
    },
  },
})
