<template>
  <section class="page emergency-detail" data-module="emergency">
    <header class="page-head">
      <div>
        <h2>突发事件处置详情</h2>
        <p class="page-desc">查看一件突发事件的完整处置经过，并推进处置状态。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回处置概览</button>
      </div>
    </header>

    <div v-if="errorMessage" class="notice error">{{ errorMessage }}</div>

    <template v-if="entry">
      <section class="panel">
        <header class="panel-head">
          <h3>{{ entry['事件编号'] }} · {{ entry['突发事件类型'] }}</h3>
          <span class="status-pill" :data-status="entry.status">{{ entry.status }}</span>
        </header>
        <dl class="detail-grid">
          <div><dt>发生位置</dt><dd>{{ entry['发生位置'] }}</dd></div>
          <div>
            <dt>影响范围</dt>
            <dd>
              <template v-if="entry['影响范围']">{{ entry['影响范围'] }}</template>
              <span v-else class="overdue-text">缺失（不合规，不进入看板统计）</span>
            </dd>
          </div>
          <div><dt>处置班组</dt><dd>{{ entry['处置班组'] }}</dd></div>
          <div><dt>上报时间</dt><dd>{{ entry['上报时间'] }}</dd></div>
          <div><dt>处置期限</dt><dd>{{ entry['处置期限'] }}（时限 {{ entry['处置时限小时'] }} 小时）</dd></div>
          <div><dt>上报人员</dt><dd>{{ entry['上报人员'] }}</dd></div>
        </dl>
        <div v-if="missingFields.length" class="notice warn">
          该件不合规项：{{ missingFields.join('、') }}缺失，补齐前不进入处置概览统计。
        </div>
        <div v-if="missingFields.includes('影响范围')" class="scope-form">
          <label class="form-item">
            <span>补录影响范围<em>*</em></span>
            <textarea v-model="scopeDraft" rows="2" placeholder="如：占东向西两车道，约 30 平方米"></textarea>
          </label>
          <button class="btn primary" type="button" :disabled="!scopeDraft.trim()" @click="saveScope">补录并纳入统计</button>
        </div>
        <div class="action-bar">
          <span class="action-label">处置推进：</span>
          <button
            v-for="action in availableActions"
            :key="action"
            class="btn primary"
            type="button"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
          <span v-if="!availableActions.length" class="muted-text">事件已恢复通行，无需再推进</span>
          <span v-if="actionMessage" class="notice-inline" :class="actionOk ? 'ok' : 'error'">{{ actionMessage }}</span>
        </div>
      </section>

      <section class="panel">
        <header class="panel-head">
          <h3>处置经过</h3>
          <span class="panel-hint">共 {{ timeline.length }} 条记录，按时间顺序排列</span>
        </header>
        <ol v-if="timeline.length" class="timeline">
          <li v-for="(step, index) in timeline" :key="index" class="timeline-item">
            <span class="timeline-dot"></span>
            <div class="timeline-body">
              <div class="timeline-head">
                <strong>{{ step['动作'] }}</strong>
                <span class="muted-text">{{ step['时间'] }} · {{ step['记录人'] }}</span>
              </div>
              <p class="timeline-note">{{ step['说明'] }}</p>
            </div>
          </li>
        </ol>
        <div v-else class="inline-empty">
          <span class="inline-empty-icon">🕒</span>
          <p class="inline-empty-title">暂无处置经过</p>
          <p class="inline-empty-desc">登记或推进处置后，这里会按时间顺序记录每一步。</p>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useEmergencyStore } from '@/stores/emergency'

type TimelineStep = { 时间: string; 动作: string; 记录人: string; 说明: string }
type Entry = Record<string, string | number | null | string[] | TimelineStep[]> & {
  id: number
  status: string
  timeline?: TimelineStep[]
  不合规项?: string[]
}

const ENDPOINT = '/api/emergency'
const NEXT_ACTIONS: Record<string, string[]> = {
  待处置: ['开始处置'],
  处置中: ['态势控制'],
  已控制: ['恢复通行'],
  已恢复: [],
}

const route = useRoute()
const router = useRouter()
const emergencyStore = useEmergencyStore()

const entry = ref<Entry | null>(null)
const errorMessage = ref('')
const actionMessage = ref('')
const actionOk = ref(false)
const scopeDraft = ref('')

const timeline = computed(() => entry.value?.timeline ?? [])
const missingFields = computed(() => entry.value?.['不合规项'] ?? [])
const availableActions = computed(() => (entry.value ? NEXT_ACTIONS[entry.value.status] ?? [] : []))

async function loadEntry() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || '突发事件详情读取失败')
    }
    entry.value = (await response.json()) as Entry
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '突发事件详情读取失败'
  }
}

async function runAction(action: string) {
  if (!entry.value) return
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, operator: '值班长' } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      actionOk.value = false
      actionMessage.value = payload.message || '处置动作未生效'
      return
    }
    actionOk.value = true
    actionMessage.value = payload.message
    entry.value = payload.entry as Entry
    // 件数会变：标记看板快照过期，返回时后台静默刷新，保证同一份件数
    emergencyStore.markStale()
  } catch (error) {
    actionOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '处置动作未生效'
  }
}

function goBack() {
  // 沿来路把筛选条件带回看板，保证看到同一份件数
  void router.push({ path: '/emergency', query: { ...route.query } })
}

async function saveScope() {
  if (!entry.value || !scopeDraft.value.trim()) return
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ values: { 影响范围: scopeDraft.value.trim(), operator: '值班长' } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      actionOk.value = false
      actionMessage.value = payload.message || '影响范围补录失败'
      return
    }
    actionOk.value = true
    actionMessage.value = payload.message
    entry.value = payload.entry as Entry
    scopeDraft.value = ''
    // 件数口径会变（该件重新纳入统计），返回看板时静默刷新
    emergencyStore.markStale()
  } catch (error) {
    actionOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '影响范围补录失败'
  }
}

onMounted(loadEntry)
</script>
