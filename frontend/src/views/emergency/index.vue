<template>
  <section class="page" data-module="emergency">
    <header class="page-head">
      <div>
        <h2>道路突发事件应急</h2>
        <p class="page-desc">塌陷、油污、倒树等突发事件的登记与处置概览：状态件数、班组在办量、超期件数一块看板看清。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = true">登记突发事件</button>
      </div>
    </header>

    <!-- 处置概览看板 -->
    <div class="stat-row">
      <article
        v-for="card in cards"
        :key="card.label"
        class="stat-card"
        :class="{ 'card-danger': card.label === '超期件' && card.value > 0 }"
      >
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <div class="board-grid">
      <!-- 各处置班组在办量：点击队名即按班组切换视图 -->
      <article class="panel crew-panel">
        <h3 class="panel-title">各处置班组在办量</h3>
        <div v-if="crewStats.length" class="crew-list">
          <button
            v-for="stat in crewStats"
            :key="stat.crew"
            type="button"
            class="crew-chip"
            :class="{ active: filters.crew === stat.crew }"
            @click="switchCrew(stat.crew)"
          >
            <span class="crew-name">{{ stat.crew }}</span>
            <span class="crew-nums">
              在办 <strong>{{ stat.active }}</strong>
              <em v-if="stat.overdue > 0" class="crew-overdue">超期 {{ stat.overdue }}</em>
            </span>
          </button>
        </div>
        <p v-else class="panel-empty">所选时间范围内暂无班组处置记录</p>
      </article>

      <!-- 视图切换：处置班组 + 时间范围 -->
      <article class="panel filter-panel">
        <h3 class="panel-title">视图切换</h3>
        <div class="filter-line">
          <label class="filter-item">
            <span>处置班组</span>
            <select v-model="filters.crew" @change="loadBoard">
              <option value="">全部班组</option>
              <option v-for="crew in crews" :key="crew" :value="crew">{{ crew }}</option>
            </select>
          </label>
          <label class="filter-item">
            <span>时间范围</span>
            <select v-model="filters.range" @change="onRangeChange">
              <option v-for="opt in rangeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
          <label class="filter-item">
            <span>开始日期</span>
            <input v-model="filters.start" type="date" @change="onCustomDate" />
          </label>
          <label class="filter-item">
            <span>结束日期</span>
            <input v-model="filters.end" type="date" @change="onCustomDate" />
          </label>
          <button class="btn ghost" type="button" @click="resetView">重置视图</button>
        </div>
      </article>
    </div>

    <!-- 影响范围缺失（不合规）件：不进统计，但点名说明是哪一项不合规 -->
    <article v-if="excluded.length" class="panel excluded-panel">
      <h3 class="panel-title">
        不合规件（{{ excluded.length }}）
        <span class="panel-hint">以下事件不计入上方件数，补录后自动纳入统计</span>
      </h3>
      <table class="data-table">
        <thead>
          <tr><th>事件编号</th><th>事件类型</th><th>发生位置</th><th>处置班组</th><th>上报时间</th><th>不合规项</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in excluded" :key="row.id">
            <td>{{ row.事件编号 }}</td>
            <td>{{ row.事件类型 }}</td>
            <td>{{ row.发生位置 }}</td>
            <td>{{ row.处置班组 }}</td>
            <td>{{ row.上报时间 }}</td>
            <td><span class="tag tag-danger">{{ row.message }}</span></td>
            <td><button class="link" type="button" @click="openDetail(row.id)">去补录</button></td>
          </tr>
        </tbody>
      </table>
    </article>

    <!-- 在办事件列表（点行进入详情看完整处置经过） -->
    <article class="panel">
      <h3 class="panel-title">
        事件明细
        <span class="panel-hint">当前视图共 {{ items.length }} 件 · 件数与上方卡片同源</span>
      </h3>
      <table v-if="items.length" class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>处置状态</th>
            <th>时限</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in items"
            :key="row.id"
            class="clickable-row"
            tabindex="0"
            @click="openDetail(row.id)"
            @keydown.enter="openDetail(row.id)"
          >
            <td v-for="column in columns" :key="column">{{ (row[column] as string) || '—' }}</td>
            <td>
              <span class="tag" :class="statusTagClass(row.status as string)">{{ row.status }}</span>
              <span v-if="row.overdue" class="tag tag-danger tag-inline">超期</span>
            </td>
            <td>{{ row.处置时限 as string }}</td>
          </tr>
        </tbody>
      </table>
      <!-- 没有在办件时的空态：给结论、给入口，不留整片空白 -->
      <div v-else class="rich-empty">
        <div class="rich-empty-icon">🛠️</div>
        <p class="rich-empty-title">当前视图下没有突发事件</p>
        <p class="rich-empty-desc">
          {{ hasAnyEvent ? '所选班组与时间范围内暂无登记事件，可放宽筛选条件查看其它视图。' : '目前还没有登记任何突发事件，首件可在这里登记。' }}
        </p>
        <div class="rich-empty-actions">
          <button class="btn primary" type="button" @click="showCreate = true">登记突发事件</button>
          <button v-if="isFiltered" class="btn" type="button" @click="resetView">重置视图看全部</button>
        </div>
      </div>
    </article>

    <footer class="page-foot">
      <span>{{ viewSummary }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记弹层 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <h3>登记突发事件</h3>
        <p class="modal-hint">带 * 为必填；影响范围可先缺后补，但缺失期间不进入看板统计。</p>
        <div class="form-grid">
          <label class="form-item">
            <span>*事件类型</span>
            <select v-model="form.事件类型">
              <option value="" disabled>请选择</option>
              <option v-for="kind in kinds" :key="kind" :value="kind">{{ kind }}</option>
            </select>
          </label>
          <label class="form-item">
            <span>*处置班组</span>
            <select v-model="form.处置班组">
              <option value="" disabled>请选择</option>
              <option v-for="crew in crews" :key="crew" :value="crew">{{ crew }}</option>
            </select>
          </label>
          <label class="form-item form-wide">
            <span>*发生位置</span>
            <input v-model="form.发生位置" placeholder="如：XX 路与 XX 街交口东行 150 米" />
          </label>
          <label class="form-item form-wide">
            <span>影响范围<i class="form-optional">（缺失不进看板统计）</i></span>
            <input v-model="form.影响范围" placeholder="如：东行最右侧车道封闭，约 80 米" />
          </label>
          <label class="form-item">
            <span>上报时间</span>
            <input v-model="form.上报时间" type="datetime-local" />
          </label>
          <label class="form-item">
            <span>上报人员</span>
            <input v-model="form.上报人员" placeholder="默认当前值班管理员" />
          </label>
        </div>
        <p v-if="createMessage" :class="createOk ? 'form-ok' : 'error-text'">{{ createMessage }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">确认登记</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import {
  RANGE_OPTIONS,
  rangeToDates,
  useEmergencyStore,
  type BoardData,
} from '@/stores/emergency'

const router = useRouter()
const emergencyStore = useEmergencyStore()

const columns = ['事件编号', '事件类型', '发生位置', '影响范围', '处置班组', '上报时间']
const rangeOptions = RANGE_OPTIONS

const crews = ref<string[]>([])
const kinds = ref<string[]>([])
const errorMessage = ref('')
const showCreate = ref(false)
const submitting = ref(false)
const createMessage = ref('')
const createOk = ref(false)

const emptyForm = () => ({
  事件类型: '',
  发生位置: '',
  影响范围: '',
  处置班组: '',
  上报时间: '',
  上报人员: '',
})
const form = ref(emptyForm())

const filters = emergencyStore.filters
const cards = computed(() => emergencyStore.board?.cards ?? [])
const crewStats = computed(() => emergencyStore.board?.crewStats ?? [])
const items = computed(() => emergencyStore.board?.items ?? [])
const excluded = computed(() => emergencyStore.board?.excluded ?? [])

const isFiltered = computed(() => Boolean(filters.crew || filters.start || filters.end))
const hasAnyEvent = computed(() => items.value.length > 0 || crewStats.value.length > 0)
const viewSummary = computed(() => {
  const parts = ['应急看板']
  parts.push(filters.crew ? `班组：${filters.crew}` : '全部班组')
  parts.push(filters.start || filters.end ? `上报时间：${filters.start || '不限'} ~ ${filters.end || '不限'}` : '全部时间')
  return `${parts.join(' · ')} · 共 ${items.value.length} 件入统，${excluded.value.length} 件不合规未入统`
})

function statusTagClass(status: string) {
  return {
    'tag-pending': status === '待处置',
    'tag-doing': status === '处置中',
    'tag-controlled': status === '已控制',
    'tag-done': status === '已恢复',
  }
}

function switchCrew(crew: string) {
  filters.crew = filters.crew === crew ? '' : crew
  void loadBoard()
}

function onRangeChange() {
  if (filters.range === 'custom') return
  const { start, end } = rangeToDates(filters.range)
  filters.start = start
  filters.end = end
  void loadBoard()
}

function onCustomDate() {
  filters.range = 'custom'
  void loadBoard()
}

function resetView() {
  emergencyStore.setFilters({ crew: '', range: 'all', start: '', end: '' })
  void loadBoard()
}

function openDetail(id: number) {
  void router.push({ name: 'emergency-detail', params: { id: String(id) } })
}

async function loadOptions() {
  try {
    const response = await request('/api/emergency/options')
    if (response.ok) {
      const data = await response.json()
      crews.value = data.crews ?? []
      kinds.value = data.kinds ?? []
    }
  } catch {
    // 选项加载失败不阻断看板，登记时再提示
  }
}

async function loadBoard() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (filters.crew) params.set('crew', filters.crew)
  if (filters.start) params.set('start', filters.start)
  if (filters.end) params.set('end', filters.end)
  try {
    const response = await request(`/api/emergency/board?${params.toString()}`)
    if (!response.ok) throw new Error('处置概览看板读取失败')
    const data = (await response.json()) as BoardData
    emergencyStore.setBoard(data)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '处置概览看板读取失败'
  }
}

async function submitCreate() {
  createMessage.value = ''
  submitting.value = true
  try {
    const values: Record<string, string> = { ...form.value }
    // datetime-local 带 T，统一成后端解析的 'YYYY-MM-DD HH:MM'
    if (values.上报时间) values.上报时间 = values.上报时间.replace('T', ' ')
    const response = await request('/api/emergency', {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      createOk.value = false
      createMessage.value = payload.message || '突发事件登记失败'
      return
    }
    createOk.value = true
    const withoutImpact = !form.value.影响范围.trim()
    createMessage.value = withoutImpact
      ? '已登记，但影响范围缺失，该件暂不进入看板统计'
      : '突发事件已登记，已纳入看板统计'
    form.value = emptyForm()
    emergencyStore.markStale()
    await loadBoard()
  } catch (error) {
    createOk.value = false
    createMessage.value = error instanceof Error ? error.message : '突发事件登记失败'
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await loadOptions()
  // 从详情返回：已有快照先展示同一份件数；若详情里推进过处置则静默刷新
  if (!emergencyStore.loaded || emergencyStore.stale) {
    await loadBoard()
  }
})
</script>

<style scoped>
.board-grid {
  display: grid;
  grid-template-columns: minmax(280px, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.panel-title {
  margin: 0 0 10px;
  font-size: 14px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.panel-hint {
  font-size: 12px;
  font-weight: normal;
  color: var(--muted);
}
.panel-empty {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.card-danger .stat-value {
  color: #b42318;
}
.crew-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.crew-chip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  border: 1px solid var(--border);
  background: #f8fafc;
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 13px;
}
.crew-chip:hover { border-color: var(--brand); }
.crew-chip.active {
  border-color: var(--brand);
  background: #eff5ff;
  box-shadow: inset 0 0 0 1px var(--brand);
}
.crew-name { font-weight: 600; }
.crew-nums { color: var(--muted); display: flex; align-items: center; gap: 6px; }
.crew-nums strong { color: #1f2937; }
.crew-overdue {
  font-style: normal;
  color: #b42318;
  background: #fef3f2;
  border-radius: 4px;
  padding: 0 6px;
  font-size: 12px;
}
.filter-line {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
}
.filter-item select,
.filter-item input {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  min-width: 130px;
}
.excluded-panel { border-color: #f0b7b2; background: #fffafa; }
.tag {
  display: inline-block;
  border-radius: 4px;
  padding: 1px 8px;
  font-size: 12px;
  background: #eef2f6;
}
.tag-inline { margin-left: 6px; }
.tag-pending { background: #fef3c7; color: #92400e; }
.tag-doing { background: #dbeafe; color: #1e40af; }
.tag-controlled { background: #ede9fe; color: #5b21b6; }
.tag-done { background: #dcfce7; color: #166534; }
.tag-danger { background: #fee4e2; color: #b42318; }
.clickable-row { cursor: pointer; }
.clickable-row:hover { background: #f5f9ff; }
.rich-empty {
  text-align: center;
  padding: 36px 20px;
  background: #f8fafc;
  border: 1px dashed var(--border);
  border-radius: 8px;
}
.rich-empty-icon { font-size: 32px; }
.rich-empty-title { font-size: 15px; font-weight: 600; margin: 8px 0 4px; }
.rich-empty-desc { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
.rich-empty-actions { display: flex; justify-content: center; gap: 10px; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 560px;
  max-width: calc(100vw - 40px);
  background: #fff;
  border-radius: 10px;
  padding: 20px 22px;
}
.modal h3 { margin: 0 0 4px; }
.modal-hint { color: var(--muted); font-size: 12px; margin: 0 0 14px; }
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.form-item { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-wide { grid-column: 1 / -1; }
.form-item input,
.form-item select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 9px;
  font-size: 13px;
  color: #1f2937;
}
.form-optional { font-style: normal; color: #b42318; }
.form-ok { color: #166534; font-size: 12px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
</style>
