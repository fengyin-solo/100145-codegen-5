<template>
  <section class="page" data-module="emergency-detail">
    <header class="page-head">
      <div>
        <h2>突发事件处置详情</h2>
        <p class="page-desc">完整处置经过按时间留痕；推进状态与补录影响范围都会追加一条记录。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回处置概览</button>
      </div>
    </header>

    <div v-if="errorMessage" class="panel error-panel">
      <p class="error-text">{{ errorMessage }}</p>
      <button class="btn" type="button" @click="goBack">返回处置概览</button>
    </div>

    <template v-else-if="event">
      <!-- 基本信息 -->
      <article class="panel">
        <h3 class="panel-title">
          {{ event.事件编号 as string }}
          <span class="tag" :class="statusTagClass(event.status)">{{ event.status }}</span>
          <span v-if="event.overdue" class="tag tag-danger">已超期</span>
          <span v-if="!event.boardEligible" class="tag tag-danger">影响范围缺失 · 未入看板统计</span>
        </h3>
        <dl class="info-grid">
          <div v-for="field in infoFields" :key="field" class="info-item">
            <dt>{{ field }}</dt>
            <dd>{{ (event[field] as string) || '—' }}</dd>
          </div>
        </dl>
      </article>

      <!-- 影响范围缺失时的补录入口 -->
      <article v-if="!event.boardEligible" class="panel supplement-panel">
        <h3 class="panel-title">补录影响范围</h3>
        <p class="panel-hint">该事件因「影响范围」缺失未进入看板统计，补录后自动纳入，件数随之更新。</p>
        <div class="supplement-line">
          <input v-model="impactDraft" placeholder="请填写封闭车道、路段长度等影响范围" />
          <button class="btn primary" type="button" :disabled="saving" @click="submitSupplement">补录并纳入统计</button>
        </div>
        <p v-if="supplementMessage" :class="supplementOk ? 'form-ok' : 'error-text'">{{ supplementMessage }}</p>
      </article>

      <!-- 处置操作 -->
      <article class="panel">
        <h3 class="panel-title">处置操作</h3>
        <div class="action-line">
          <button
            v-if="event.status !== '已恢复'"
            class="btn primary"
            type="button"
            :disabled="saving"
            @click="advance"
          >
            推进为「{{ nextStage }}」
          </button>
          <span v-else class="done-note">该事件已恢复交通，处置闭环。</span>
          <p v-if="actionMessage" :class="actionOk ? 'form-ok' : 'error-text'" class="action-msg">{{ actionMessage }}</p>
        </div>
      </article>

      <!-- 完整处置经过 -->
      <article class="panel">
        <h3 class="panel-title">完整处置经过</h3>
        <ol class="timeline">
          <li v-for="(entry, index) in timeline" :key="index" class="timeline-item">
            <span class="timeline-dot" :class="{ current: index === timeline.length - 1 }"></span>
            <div class="timeline-body">
              <div class="timeline-head">
                <strong>{{ entry.stage }}</strong>
                <span class="timeline-time">{{ entry.time }}</span>
                <span class="timeline-crew">{{ entry.crew }}</span>
              </div>
              <p class="timeline-note">{{ entry.note }}</p>
              <p v-if="entry.operator" class="timeline-operator">操作/记录人：{{ entry.operator }}</p>
            </div>
          </li>
        </ol>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { useEmergencyStore, type BoardItem, type TimelineEntry } from '@/stores/emergency'

const route = useRoute()
const router = useRouter()
const emergencyStore = useEmergencyStore()
const sessionStore = useSessionStore()

const infoFields = ['事件类型', '发生位置', '影响范围', '处置班组', '上报时间', '上报人员', '处置时限']
const STAGES = ['待处置', '处置中', '已控制', '已恢复']

const event = ref<BoardItem | null>(null)
const errorMessage = ref('')
const saving = ref(false)
const actionMessage = ref('')
const actionOk = ref(false)
const supplementMessage = ref('')
const supplementOk = ref(false)
const impactDraft = ref('')

const timeline = computed<TimelineEntry[]>(() => {
  const value = event.value?.timeline
  return Array.isArray(value) ? (value as TimelineEntry[]) : []
})
const nextStage = computed(() => {
  const index = STAGES.indexOf(event.value?.status ?? '')
  return index >= 0 && index < STAGES.length - 1 ? STAGES[index + 1] : ''
})

function statusTagClass(status: string) {
  return {
    'tag-pending': status === '待处置',
    'tag-doing': status === '处置中',
    'tag-controlled': status === '已控制',
    'tag-done': status === '已恢复',
  }
}

function goBack() {
  void router.push({ name: 'emergency' })
}

async function loadEvent() {
  errorMessage.value = ''
  try {
    const response = await request(`/api/emergency/${route.params.id}`)
    if (response.status === 404) {
      errorMessage.value = '该突发事件不存在或已归档'
      return
    }
    if (!response.ok) throw new Error('突发事件详情读取失败')
    event.value = (await response.json()) as BoardItem
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '突发事件详情读取失败'
  }
}

async function advance() {
  actionMessage.value = ''
  saving.value = true
  try {
    const response = await request(`/api/emergency/${route.params.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '推进处置', operator: sessionStore.operator } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      actionOk.value = false
      actionMessage.value = payload.message || '处置状态推进失败'
      return
    }
    actionOk.value = true
    actionMessage.value = payload.message
    event.value = payload.entry as BoardItem
    // 件数已变化，返回看板时按同一视图口径重新拉数
    emergencyStore.markStale()
  } catch (error) {
    actionOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '处置状态推进失败'
  } finally {
    saving.value = false
  }
}

async function submitSupplement() {
  supplementMessage.value = ''
  if (!impactDraft.value.trim()) {
    supplementOk.value = false
    supplementMessage.value = '请先填写影响范围'
    return
  }
  saving.value = true
  try {
    const response = await request(`/api/emergency/${route.params.id}/supplement`, {
      method: 'POST',
      body: JSON.stringify({ values: { 影响范围: impactDraft.value.trim() } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      supplementOk.value = false
      supplementMessage.value = payload.message || '影响范围补录失败'
      return
    }
    supplementOk.value = true
    supplementMessage.value = payload.message
    event.value = payload.entry as BoardItem
    impactDraft.value = ''
    // 补录后该件从未入统变为入统，看板件数需按同一视图口径重算
    emergencyStore.markStale()
  } catch (error) {
    supplementOk.value = false
    supplementMessage.value = error instanceof Error ? error.message : '影响范围补录失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadEvent)
</script>

<style scoped>
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
  align-items: center;
  gap: 8px;
}
.panel-hint {
  font-size: 12px;
  font-weight: normal;
  color: var(--muted);
  margin: 0 0 10px;
}
.error-panel { display: flex; justify-content: space-between; align-items: center; }
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 24px;
  margin: 0;
}
.info-item dt { font-size: 12px; color: var(--muted); }
.info-item dd { margin: 2px 0 0; font-size: 13px; }
.tag {
  display: inline-block;
  border-radius: 4px;
  padding: 1px 8px;
  font-size: 12px;
  background: #eef2f6;
}
.tag-pending { background: #fef3c7; color: #92400e; }
.tag-doing { background: #dbeafe; color: #1e40af; }
.tag-controlled { background: #ede9fe; color: #5b21b6; }
.tag-done { background: #dcfce7; color: #166534; }
.tag-danger { background: #fee4e2; color: #b42318; }
.supplement-panel { border-color: #f0b7b2; background: #fffafa; }
.supplement-line { display: flex; gap: 10px; }
.supplement-line input {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 9px;
  font-size: 13px;
}
.action-line { display: flex; align-items: center; gap: 12px; }
.action-msg { margin: 0; }
.done-note { font-size: 13px; color: #166534; }
.form-ok { color: #166534; font-size: 12px; }
.timeline {
  list-style: none;
  margin: 0;
  padding: 0 0 0 8px;
}
.timeline-item {
  position: relative;
  padding: 0 0 18px 20px;
  border-left: 2px solid var(--border);
}
.timeline-item:last-child { padding-bottom: 0; border-left-color: transparent; }
.timeline-dot {
  position: absolute;
  left: -7px;
  top: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #c2ccd8;
  border: 2px solid #fff;
}
.timeline-dot.current { background: var(--brand); }
.timeline-head { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.timeline-time { color: var(--muted); font-size: 12px; }
.timeline-crew {
  font-size: 12px;
  color: #1e40af;
  background: #eff5ff;
  border-radius: 4px;
  padding: 0 6px;
}
.timeline-note { margin: 4px 0 0; font-size: 13px; }
.timeline-operator { margin: 2px 0 0; font-size: 12px; color: var(--muted); }
</style>
