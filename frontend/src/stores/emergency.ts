import { defineStore } from 'pinia'

/**
 * 突发事件看板的跨页状态。
 *
 * 看板 → 详情 → 返回时，组件重新挂载；筛选条件与最后一次看板件数放在
 * store 里而不是组件局部状态，返回后先还原同一份件数，再按同一口径静默
 * 刷新，避免值班长看到数字跳动或被重置成默认视图。
 */

export type BoardCard = { label: string; value: number }
export type CrewStat = { crew: string; active: number; overdue: number; recovered: number }
export type BoardItem = {
  id: number
  status: string
  overdue: boolean
  active: boolean
  boardEligible: boolean
  [key: string]: string | number | boolean | string[] | TimelineEntry[]
}
export type TimelineEntry = {
  stage: string
  time: string
  crew: string
  note: string
  operator?: string
}
export type ExcludedItem = {
  id: number
  事件编号: string
  事件类型: string
  发生位置: string
  处置班组: string
  上报时间: string
  reasons: string[]
  message: string
}
export type BoardData = {
  cards: BoardCard[]
  crewStats: CrewStat[]
  items: BoardItem[]
  total: number
  excluded: ExcludedItem[]
  excludedTotal: number
  filters: { crew: string; start: string; end: string }
}

export type BoardFilters = {
  crew: string
  range: string
  start: string
  end: string
}

// 快捷时间范围：值为相对今天往前的天数；custom 时用手填起止日期
export const RANGE_OPTIONS = [
  { label: '今天', value: '1' },
  { label: '近 3 天', value: '3' },
  { label: '近 7 天', value: '7' },
  { label: '全部', value: 'all' },
]

function isoDate(offsetDays = 0): string {
  const date = new Date()
  date.setDate(date.getDate() + offsetDays)
  return date.toISOString().slice(0, 10)
}

export function rangeToDates(range: string): { start: string; end: string } {
  if (range === 'all') return { start: '', end: '' }
  const days = Number(range)
  if (!Number.isFinite(days) || days <= 0) return { start: '', end: '' }
  return { start: isoDate(-(days - 1)), end: isoDate(0) }
}

export const useEmergencyStore = defineStore('emergency', {
  state: () => ({
    filters: { crew: '', range: 'all', start: '', end: '' } as BoardFilters,
    board: null as BoardData | null,
    loaded: false,
    // 进入详情后若在详情里推进过处置，返回看板需要重新拉数
    stale: false,
  }),
  actions: {
    // 原地合并：组件里持有 filters 引用时，重置视图后引用仍指向同一份状态
    setFilters(patch: Partial<BoardFilters>) {
      Object.assign(this.filters, patch)
    },
    setBoard(data: BoardData) {
      this.board = data
      this.loaded = true
      this.stale = false
    },
    markStale() {
      this.stale = true
    },
  },
})
