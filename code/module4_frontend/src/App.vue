<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api.js'
import GameTable from './components/GameTable.vue'
import ConversationLog from './components/ConversationLog.vue'
import ScoreReport from './components/ScoreReport.vue'

const state = ref(null), user = ref(null), busy = ref(false), error = ref('')
const source = ref('existing'), playMode = ref('coop'), theme = ref(''), text = ref(''), answer = ref(''), name = ref('')
const playing = computed(() => state.value?.status === 'playing')
const playerTurn = computed(() => playing.value && state.value.next_actor === 'player')

async function run(task) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { await task() } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function teammate() {
  state.value = await api('teammate', {})
}
async function ask() {
  await run(async () => {
    state.value = await api('question', { text: text.value })
    text.value = ''
    if (state.value.next_actor === 'teammate') await teammate()
  })
}
onMounted(() => run(async () => {
  state.value = await api('state')
  user.value = await api('users/me')
  name.value = user.value.display_name
}))
</script>

<template>
  <main>
    <header><div><span class="eyebrow">AI PUZZLE MATE</span><h1>问渊 <small>一起还原故事的真相</small></h1></div>
      <span class="badge">{{ state?.mode === 'llm' ? 'DeepSeek 模式' : '离线演示' }}</span></header>
    <p v-if="error" role="alert" class="error">{{ error }} <button :disabled="busy" @click="run(async () => { state = await api('state') })">刷新状态</button></p>
    <p v-if="!state && !error">正在准备推理桌……</p>
    <template v-if="state">
      <section class="panel setup">
        <form class="profile" @submit.prevent="run(async () => { user = await api('users/me', { display_name: name }, 'PATCH') })">
          <label>玩家昵称<input v-model="name" maxlength="30" required :disabled="busy"></label><button :disabled="busy">保存昵称</button>
        </form>
        <form class="options" @submit.prevent="run(async () => { state = await api('new', { source, play_mode: playMode, theme }); text = ''; answer = '' })">
          <label>推理方式<select v-model="playMode" :disabled="busy"><option value="coop">和 AI 小夏一起玩</option><option value="solo">我自己来</option></select></label>
          <label>题目来源<select v-model="source" :disabled="busy"><option value="existing">随机已有题目</option><option value="new" :disabled="state.mode === 'demo'">生成并审核新题</option></select></label>
          <label v-if="source === 'new'">故事主题<input v-model="theme" maxlength="100" required :disabled="busy" placeholder="例如：校园里的误会"></label>
          <button class="primary" :disabled="busy">{{ busy ? '处理中……' : '开始新的一局' }}</button>
        </form>
        <small v-if="state.mode === 'demo'">演示模式使用内置题和关键词判定，评分仅供体验。</small>
      </section>
      <template v-if="state.puzzle">
        <div class="game-grid"><GameTable :state="state"/><ConversationLog :history="state.history"/></div>
        <section v-if="playing" class="panel controls">
          <template v-if="state.next_actor === 'teammate'"><p>轮到 AI 小夏提问。若上次失败，可继续此回合。</p><button class="primary" :disabled="busy" @click="run(teammate)">继续队友回合</button></template>
          <form @submit.prevent="ask"><label for="question">你的问题（是 / 否 / 无关）</label><textarea id="question" v-model="text" maxlength="300" required :disabled="busy || !playerTurn" placeholder="这与他的身高有关吗？"/><button class="primary" :disabled="busy || !playerTurn">提问</button></form>
          <details><summary>我要提交完整还原</summary><form @submit.prevent="run(async () => { state = await api('final', { text: answer }) })"><label for="answer">请写出完整故事与原因</label><textarea id="answer" v-model="answer" maxlength="1500" required :disabled="busy || !playerTurn"/><button :disabled="busy || !playerTurn">提交答案并评分</button></form></details>
          <button class="subtle" :disabled="busy" @click="run(async () => { state = await api('reveal', {}) })">结束本局并揭晓汤底</button>
        </section>
        <ScoreReport v-if="state.report" :report="state.report"/>
      </template>
    </template>
  </main>
</template>
