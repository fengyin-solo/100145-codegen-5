<template>
  <section class="page emergency-page" data-module="emergency">
    <header class="page-head">
      <div>
        <h2>道路突发事件应急处置概览</h2>
        <p class="page-desc">
          登记塌陷、油污、倒树等突发事件的发生位置、影响范围、处置班组与上报时间；
          看板只统计资料合规的在办件，点开任意一件可查看完整处置经过。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记突发事件</button>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>处置班组</span>
        <select v-model="draftFilters.crew">
          <option value="">全部班组</option>
          <option v-for="name in crewOptions" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>上报时间起</span>
        <input v-model="draftFilters.start" type="date" />
      </label>
      <label class="filter-item">
        <span>上报时间止</span>
        <input v-model="draftFilters.end" type="date" />
      </label>
      <button class="btn primary" type="submit">切换视图</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span class="filter-hint">当前视图：{{ viewSummary }}</span>
    </form>

    <div v-if="errorMessage" class="notice error">{{ errorMessage }}</div>

    <div class="stat-row">
      <article v-for="card in statCards" :key="card.label" class="stat-card" :class="card.tone">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
        <span class="stat-sub">{{ card.sub }}</span>
      </article>
    </div>

    <section class="panel">
      <header class="panel-head">
        <h3>各处置班组在办量</h3>
        <span class="panel-hint">在办 = 待处置 + 处置中 + 已控制（已恢复不计）</span>
      </header>
      <ul v-if="crewWorkload.length" class="crew-grid">
        <li v-for="crew in crewWorkload" :key="crew.crew" class="crew-card" :class="{ alert: crew.overdue > 0 }">
          <div class="crew-name">{{ crew.crew }}</div>
          <div class="crew-main">
            <strong>{{ crew.inProgress }}</strong><span>件在办</span>
          </div>
          <div class="crew-meta">
            <span>待处置 {{ crew['待处置'] }}</span>
            <span>处置中 {{ crew['处置中'] }}</span>
            <span>已控制 {{ crew['已控制'] }}</span>
            <span>已恢复 {{ crew['已恢复'] }}</span>
          </div>
          <div v-if="crew.overdue > 0" class="crew-overdue">超期 {{ crew.overdue }} 件</div>
          <div v-else class="crew-ok">无超期件</div>
        </li>
      </ul>
      <!-- 在办量为空时不留下整片空白：给出说明与引导，而不是空容器 -->
      <div v-else class="inline-empty">
        <span class="inline-empty-icon">🛠️</span>
        <p class="inline-empty-title">当前视图下没有在办件</p>
        <p class="inline-empty-desc">所有合规事件均已恢复通行，或筛选条件把在办件都过滤掉了。</p>
        <button class="btn ghost" type="button" @click="resetFilters">查看全部班组与时间范围</button>
      </div>
    </section>

    <section v-if="invalidItems.length" class="panel invalid-panel">
      <header class="panel-head">
        <h3>未进入看板统计的事件（{{ invalidItems.length }}）</h3>
        <span class="panel-hint">以下事件资料不合规，不计入上方任何件数</span>
      </header>
      <ul class="invalid-list">
        <li v-for="item in invalidItems" :key="String(item.id)" class="invalid-item">
          <RouterLink :to="`/emergency/${item.id}`" class="link invalid-link">
            {{ item['事件编号'] }}
          </RouterLink>
          <span class="invalid-tag" v-for="field in item['不合规项']" :key="field">
            不合规项：{{ field }}缺失
          </span>
          <span class="invalid-meta">{{ item['突发事件类型'] }} · {{ item['发生位置'] }} · {{ item['处置班组'] }} · 上报 {{ item['上报时间'] }}</span>
          <button class="link" type="button" @click="openDetail(item.id as number)">去补录</button>
        </li>
      </ul>
    </section>

    <section class="panel">
      <header class="panel-head">
        <h3>事件清单</h3>
        <span class="panel-hint">{{ loading ? '正在读取最新件数…' : `共 ${total} 件纳入统计，按上报时间倒序` }}</span>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>事件编号</th>
            <th>类型</th>
            <th>发生位置</th>
            <th>影响范围</th>
            <th>处置班组</th>
            <th>上报时间</th>
            <th>处置期限</th>
            <th>状态</th>
            <th>时效</th>
            <th>处置经过</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in items" :key="String(row.id)">
            <td>{{ row['事件编号'] }}</td>
            <td>{{ row['突发事件类型'] }}</td>
            <td>{{ row['发生位置'] }}</td>
            <td>{{ row['影响范围'] }}</td>
            <td>{{ row['处置班组'] }}</td>
            <td>{{ row['上报时间'] }}</td>
            <td>{{ row['处置期限'] }}</td>
            <td><span class="status-pill" :data-status="row.status">{{ row.status }}</span></td>
            <td>
              <span v-if="isOverdue(row)" class="overdue-text">已超期</span>
              <span v-else-if="row.status === '已恢复'" class="muted-text">已办结</span>
              <span v-else class="muted-text">办理中</span>
            </td>
            <td><button class="link" type="button" @click="openDetail(row.id as number)">查看经过</button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="!items.length" class="inline-empty table-empty">
        <span class="inline-empty-icon">📋</span>
        <p class="inline-empty-title">当前视图下暂无合规突发事件</p>
        <p class="inline-empty-desc">
          影响范围缺失的事件不会进入看板统计；如果刚登记过事件，请在上方“未进入统计”区域核对，或放宽班组与时间条件。
        </p>
        <button class="btn primary" type="button" @click="openCreate">登记一件突发事件</button>
      </div>
    </section>

    <!-- 登记弹层 -->
    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <div class="modal">
        <header class="modal-head">
          <h3>登记道路突发事件</h3>
          <button class="link" type="button" @click="creating = false">关闭</button>
        </header>
        <form class="modal-body" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.key" class="form-item" :class="{ required: field.required }">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <input v-model="createForm[field.key]" :placeholder="field.placeholder" />
          </label>
          <label class="form-item">
            <span>影响范围</span>
            <textarea
              v-model="createForm['影响范围']"
              rows="2"
              placeholder="如：占东向西两车道，约 30 平方米；暂无法核实可留空"
            ></textarea>
            <small class="form-hint">影响范围可后补，但缺失期间该件不进入看板统计，并标记为不合规件。</small>
          </label>
          <p v-if="createMessage" class="notice" :class="createOk ? 'ok' : 'error'">{{ createMessage }}</p>
          <footer class="modal-foot">
            <button class="btn" type="button" @click="creating = false">取消</button>
            <button class="btn primary" type="submit">确认登记</button>
          </footer>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useEmergencyStore } from '@/stores/emergency'

type Row = Record<string, string | number | null> & {
  id: number
  status: string
  timeline?: { 时间: string; 动作: string; 记录人: string; 说明: string }[]
}
type InvalidItem = Row & { 不合规项: string[]; 原因: string }
type CrewWorkload = {
  crew: string
  inProgress: number
  overdue: number
  待处置: number
  处置中: number
  已控制: number
  已恢复: number
}
type BoardPayload = {
  filters: { crew: string; start: string; end: string; crewOptions: string[] }
  counts: Record<string, number>
  overdueCount: number
  total: number
  crewWorkload: CrewWorkload[]
  items: Row[]
  invalid: InvalidItem[]
}

const ENDPOINT = '/api/emergency'
const STATUS_LIST = ['待处置', '处置中', '已控制', '已恢复']

const router = useRouter()
const route = useRoute()
const emergencyStore = useEmergencyStore()

const emptyBoard = (): BoardPayload => ({
  filters: { crew: '', start: '', end: '', crewOptions: [] },
  counts: { 待处置: 0, 处置中: 0, 已控制: 0, 已恢复: 0 },
  overdueCount: 0,
  total: 0,
  crewWorkload: [],
  items: [],
  invalid: [],
})

const board = ref<BoardPayload>(emptyBoard())
const loading = ref(false)
const errorMessage = ref('')
const draftFilters = reactive({ ...emergencyStore.filters })

const createFields = [
  { key: '突发事件类型', label: '突发事件类型', placeholder: '道路塌陷 / 路面油污 / 倒伏树木', required: true },
  { key: '发生位置', label: '发生位置', placeholder: '如：中山路与和平路交口东侧 50 米', required: true },
  { key: '处置班组', label: '处置班组', placeholder: '如：道桥抢险一班', required: true },
  { key: '上报时间', label: '上报时间', placeholder: 'YYYY-MM-DD HH:MM，留默认现在', required: true },
] as const

const creating = ref(false)
const createForm = reactive<Record<string, string>>({
  突发事件类型: '',
  发生位置: '',
  处置班组: '',
  上报时间: '',
  影响范围: '',
})
const createMessage = ref('')
const createOk = ref(false)

const counts = computed(() => board.value.counts)
const items = computed(() => board.value.items)
const invalidItems = computed(() => board.value.invalid)
const crewWorkload = computed(() => board.value.crewWorkload)
const crewOptions = computed(() => board.value.filters.crewOptions ?? [])
const total = computed(() => board.value.total)

const statCards = computed(() => [
  { label: '待处置', value: counts.value['待处置'] ?? 0, sub: '尚未出动', tone: 'tone-wait' },
  { label: '处置中', value: counts.value['处置中'] ?? 0, sub: '班组现场作业', tone: 'tone-doing' },
  { label: '已控制', value: counts.value['已控制'] ?? 0, sub: '险情不扩大', tone: 'tone-controlled' },
  { label: '已恢复', value: counts.value['已恢复'] ?? 0, sub: '交通恢复正常', tone: 'tone-done' },
  { label: '超期件', value: board.value.overdueCount, sub: '超处置期限未恢复', tone: 'tone-overdue' },
])

const viewSummary = computed(() => {
  const crew = board.value.filters.crew || '全部班组'
  const range = board.value.filters.start || board.value.filters.end
    ? `${board.value.filters.start || '最早'} 至 ${board.value.filters.end || '至今'}`
    : '全部时间'
  return `${crew} · ${range}`
})

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function nowText() {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function isOverdue(row: Row) {
  if (row.status === '已恢复') return false
  const deadline = String(row['处置期限'] ?? '')
  if (!deadline) return false
  return new Date(deadline.replace(/-/g, '/')).getTime() < Date.now()
}

function buildQuery(filters: { crew: string; start: string; end: string }) {
  const params = new URLSearchParams()
  if (filters.crew) params.set('crew', filters.crew)
  if (filters.start) params.set('start', filters.start)
  if (filters.end) params.set('end', filters.end)
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function loadBoard(silent = false) {
  if (!silent) {
    loading.value = true
    errorMessage.value = ''
  }
  try {
    const response = await request(`${ENDPOINT}/board${buildQuery(emergencyStore.filters)}`)
    if (!response.ok) throw new Error('处置概览读取失败')
    const payload = (await response.json()) as BoardPayload
    board.value = payload
    emergencyStore.setSnapshot(payload as unknown as Record<string, unknown>)
    Object.assign(draftFilters, emergencyStore.filters)
  } catch (error) {
    if (!silent) errorMessage.value = error instanceof Error ? error.message : '处置概览读取失败'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  emergencyStore.setFilters({ ...draftFilters })
  void loadBoard()
}

function resetFilters() {
  draftFilters.crew = ''
  draftFilters.start = ''
  draftFilters.end = ''
  emergencyStore.setFilters({ crew: '', start: '', end: '' })
  void loadBoard()
}

function openDetail(id: number) {
  void router.push({ path: `/emergency/${id}`, query: { ...emergencyStore.filters } })
}

function openCreate() {
  createMessage.value = ''
  createForm.突发事件类型 = ''
  createForm.发生位置 = ''
  createForm.处置班组 = ''
  createForm.上报时间 = nowText()
  createForm.影响范围 = ''
  creating.value = true
}

async function submitCreate() {
  createMessage.value = ''
  const values: Record<string, string> = {}
  for (const key of Object.keys(createForm)) {
    const text = createForm[key].trim()
    if (text) values[key] = text
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values, remark: '' }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      createOk.value = false
      createMessage.value = payload.message || '突发事件登记失败'
      return
    }
    createOk.value = true
    createMessage.value = payload.message
    creating.value = false
    await loadBoard()
  } catch (error) {
    createOk.value = false
    createMessage.value = error instanceof Error ? error.message : '突发事件登记失败'
  }
}

onMounted(() => {
  // 详情页返回时会把筛选条件放在 query 里；有 query 以 query 为准，保证看到同一份件数。
  const queryKeys = ['crew', 'start', 'end'] as const
  const hasQuery = queryKeys.some((key) => key in route.query)
  if (hasQuery) {
    const fromQuery = {
      crew: String(route.query.crew ?? ''),
      start: String(route.query.start ?? ''),
      end: String(route.query.end ?? ''),
    }
    emergencyStore.setFilters(fromQuery)
    Object.assign(draftFilters, fromQuery)
    void loadBoard()
    return
  }
  // 从详情返回（无 query 时）：先还原离开时的同一份件数快照；若在详情里推进过处置，再后台静默刷新。
  if (emergencyStore.loaded && emergencyStore.snapshot) {
    board.value = emergencyStore.snapshot as unknown as BoardPayload
    Object.assign(draftFilters, emergencyStore.filters)
    if (emergencyStore.stale) {
      void loadBoard(true)
    }
  } else {
    void loadBoard()
  }
})
</script>
