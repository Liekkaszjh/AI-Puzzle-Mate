<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: { type: Object, required: true },
  busy: Boolean,
  speaker: { type: String, default: '' },
})
const team = computed(() => props.state.teammates || [])
const active = computed(() => {
  if (props.state.status !== 'playing') return ''
  if (props.busy) return props.speaker
  return props.state.next_actor === 'player' ? 'player' : props.state.next_teammate?.id
})
const status = computed(() => {
  if (props.state.status !== 'playing') return '本局已结束，可以查看故事真相'
  if (props.busy) return props.speaker === 'host' ? '汤主正在核对你的发言……' : `${props.state.next_teammate?.name || '队友'}正在思考……`
  return props.state.next_actor === 'player' ? '轮到你提问了' : `轮到 ${props.state.next_teammate?.name || 'AI 队友'} 提问`
})

function speech(id) {
  if (props.busy && active.value === id) return id === 'host' ? '让我对照故事，仔细核实一下。' : '让我想一想，这次从另一个角度验证。'
  const last = [...props.state.history].reverse().find(turn => id === 'host' || (id === 'player' ? turn.actor === 'player' : turn.teammate_id === id || (!turn.teammate_id && id === 'xiaoxia' && turn.actor === 'teammate')))
  if (last) return id === 'host' ? `汤主判定：${last.verdict}${last.feedback ? ' · ' + last.feedback : ''}` : last.question
  if (id === 'host') return '欢迎入座，今天也慢慢想。'
  return id === 'player' ? '从哪里问起呢？让我想一想。' : '我会留意大家的提问，轮到我时继续验证。'
}
</script>

<template>
  <section class="panel story table-panel" aria-label="围桌推理场景">
    <div class="table-topline"><span>● {{ team.length ? `你与 ${team.length} 位 AI 的合作推理` : '一个人的推理时光' }}</span><span v-if="state.board">已确认 {{ state.board.confirmed }} 个命题 · {{ state.turns }}/{{ state.max_turns }} 次互动</span><span v-else>{{ state.turns }}/{{ state.max_turns }} 次互动</span></div>
    <div class="scene" :class="{ solo: !team.length }" :data-team-count="team.length">
      <span class="wall-detail" aria-hidden="true">✦</span>
      <div class="rug" aria-hidden="true"></div>
      <div class="seat host-seat" :class="{ active: active === 'host' }">
        <div class="speech host-speech" :title="speech('host')">{{ speech('host') }}</div>
        <img class="portrait" src="/avatars/host.svg" alt="汤主老陈" width="130" height="146">
        <div class="nameplate"><strong>老陈 <em>汤主</em></strong><span>知道真相的人</span></div>
      </div>
      <div class="wood-table" aria-hidden="true"><div class="table-inlay"></div><span class="table-mark">SLOW THINKING CLUB</span></div>
      <span class="cup cup-left" aria-hidden="true"></span><span class="cup cup-right" aria-hidden="true"></span>
      <article class="story-paper"><div class="paper-heading"><span>今日汤面</span><span>CASE / {{ state.puzzle.fact_count }} FACTS</span></div>
        <h2>{{ state.puzzle.title }}</h2><p class="surface">{{ state.puzzle.surface }}</p>
        <div class="paper-footer">◇ 答案，藏在好问题里。</div>
      </article>
      <div class="soup" aria-hidden="true"><div class="steam">∿ ∿</div><div class="soup-bowl">?</div></div>
      <div class="seat player-seat" :class="{ active: active === 'player' }">
        <div class="speech" :title="speech('player')">{{ speech('player') }}</div>
        <img class="portrait" src="/avatars/player.svg" alt="玩家" width="130" height="146">
        <div class="nameplate"><strong>你 <em>PLAYER</em></strong><span>{{ active === 'player' ? '准备好你的下一个问题' : '听听大家的想法' }}</span></div>
      </div>
      <div v-for="(mate, index) in team" :key="mate.id" class="seat teammate-seat" :class="[`mate-${index}`, { active: active === mate.id }]" :data-teammate-id="mate.id">
        <div class="speech" :title="speech(mate.id)">{{ speech(mate.id) }}</div>
        <img class="portrait" :src="`/avatars/${mate.id === 'xiaoxia' ? 'teammate' : mate.id}.svg`" :alt="`AI 队友 ${mate.name}`" width="130" height="146">
        <div class="nameplate"><strong>{{ mate.name }} <em>AI</em></strong><span>{{ mate.focus.split('：')[0] }}</span></div>
      </div>
    </div>
    <div class="turn-strip" role="status"><span class="turn-light" :class="{ thinking: busy }"></span><div><strong>{{ status }}</strong><p>{{ team.length ? `提问顺序：你 → ${team.map(m => m.name).join(' → ')} → 你` : '慢慢想，你可以连续提问。' }}</p><p v-if="state.hint" class="hint">{{ state.hint }}</p></div></div>
    <p v-if="state.notice" role="status">{{ state.notice }}</p>
    <div v-if="state.solution" class="solution"><h3>故事真相</h3><p>{{ state.solution.bottom }}</p></div>
  </section>
</template>

<style scoped src="./roundtable.css"></style>
