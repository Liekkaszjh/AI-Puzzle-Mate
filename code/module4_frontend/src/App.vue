<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api.js'
import GameTable from './components/GameTable.vue'
import ConversationLog from './components/ConversationLog.vue'
import ScoreReport from './components/ScoreReport.vue'
import AdminUsers from './components/AdminUsers.vue'

const state = ref(null), user = ref(null), busy = ref(false), error = ref(''), notice = ref('')
const source = ref('existing'), playMode = ref('coop'), theme = ref(''), text = ref(''), answer = ref(''), name = ref('')
const authMode = ref('login'), email = ref(''), password = ref(''), currentPassword = ref(''), newPassword = ref('')
const teammateCount = ref(2), speaker = ref('')
const playing = computed(() => state.value?.status === 'playing')
const playerTurn = computed(() => playing.value && state.value.next_actor === 'player')
const signedIn = computed(() => Boolean(user.value?.email))
const isAdmin = computed(() => user.value?.role === 'admin')

async function run(task) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try { await task() } catch (e) {
    error.value = e.message
    try { state.value = await api('state') } catch { /* Keep the last usable state when offline. */ }
  } finally { busy.value = false; speaker.value = '' }
}
async function teammate() {
  // One request per named teammate: every completed turn is persisted and visible.
  while (state.value?.status === 'playing' && state.value.next_actor === 'teammate') {
    speaker.value = state.value.next_teammate?.id || ''
    state.value = await api('teammate', {})
  }
}
async function ask() {
  await run(async () => {
    speaker.value = 'host'
    state.value = await api('question', { text: text.value })
    text.value = ''
    if (state.value.next_actor === 'teammate') await teammate()
  })
}
async function submitAuth() {
  await run(async () => {
    const payload = { email: email.value, password: password.value }
    if (authMode.value === 'register') payload.display_name = name.value
    const result = await api(`users/${authMode.value}`, payload)
    user.value = result.user
    name.value = result.user.display_name
    state.value = await api('state')
    password.value = ''
  })
}
async function signOut() {
  await run(async () => {
    const result = await api('users/logout', {})
    user.value = result.user
    name.value = result.user.display_name
    authMode.value = 'login'
    email.value = ''
    password.value = ''
    currentPassword.value = ''
    newPassword.value = ''
    state.value = await api('state')
  })
}
async function updatePassword() {
  await run(async () => {
    await api('users/password', { current_password: currentPassword.value, new_password: newPassword.value })
    currentPassword.value = ''
    newPassword.value = ''
    notice.value = '密码已更新，其他设备需要重新登录。'
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
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="!state && !error">正在准备推理桌……</p>
    <template v-if="state">
      <section class="panel account">
        <h2>{{ !signedIn ? '登录或注册' : isAdmin ? '管理员账户' : '玩家账户' }}</h2>
        <p v-if="signedIn">已登录：{{ user.email }}</p>
        <p v-else>请先注册或登录，登录后才能开始游戏。</p>
        <form v-if="!signedIn" class="account-form" @submit.prevent="submitAuth">
          <div class="auth-switch">
            <button type="button" :aria-pressed="authMode === 'login'" :disabled="busy" @click="authMode = 'login'">登录</button>
            <button type="button" :aria-pressed="authMode === 'register'" :disabled="busy" @click="authMode = 'register'">注册</button>
          </div>
          <label>邮箱<input v-model.trim="email" type="email" autocomplete="email" maxlength="254" required :disabled="busy"></label>
          <label v-if="authMode === 'register'">注册昵称<input v-model.trim="name" maxlength="30" required :disabled="busy"></label>
          <label>密码<input v-model="password" type="password" :autocomplete="authMode === 'register' ? 'new-password' : 'current-password'" :minlength="authMode === 'register' ? 8 : undefined" maxlength="128" required :disabled="busy"></label>
          <button class="primary" :disabled="busy">{{ authMode === 'register' ? '创建账号' : '邮箱登录' }}</button>
        </form>
        <template v-else>
          <form class="profile" @submit.prevent="run(async () => { user = await api('users/me', { display_name: name }, 'PATCH') })">
            <label>{{ isAdmin ? '管理员昵称' : '玩家昵称' }}<input v-model="name" maxlength="30" required :disabled="busy"></label>
            <button :disabled="busy">保存我的昵称</button>
          </form>
          <button :disabled="busy" @click="signOut">退出登录</button>
          <form class="account-form password-form" @submit.prevent="updatePassword">
            <label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" required :disabled="busy"></label>
            <label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" minlength="8" maxlength="128" required :disabled="busy"></label>
            <button :disabled="busy">修改密码</button>
          </form>
        </template>
      </section>
      <AdminUsers v-if="isAdmin"/>
      <template v-if="signedIn && !isAdmin">
      <section class="panel setup">
        <form class="options" @submit.prevent="run(async () => { speaker = 'host'; state = await api('new', { source, play_mode: playMode, theme, teammate_count: teammateCount }); text = ''; answer = '' })">
          <label>推理方式<select v-model="playMode" :disabled="busy"><option value="coop">和 AI 队友一起玩</option><option value="solo">我自己来</option></select></label>
          <label v-if="playMode === 'coop'">AI 队友人数<select v-model.number="teammateCount" :disabled="busy"><option :value="1">1 位队友</option><option :value="2">2 位队友</option><option :value="3">3 位队友</option></select></label>
          <label>题目来源<select v-model="source" :disabled="busy"><option value="existing">随机已有题目</option><option value="new" :disabled="state.mode === 'demo'">生成并审核新题</option></select></label>
          <label v-if="source === 'new'">故事主题<input v-model="theme" maxlength="100" required :disabled="busy" placeholder="例如：校园里的误会"></label>
          <button class="primary" :disabled="busy">{{ busy ? '处理中……' : '开始新的一局' }}</button>
        </form>
        <small v-if="state.mode === 'demo'">演示模式使用内置题和关键词判定，评分仅供体验。</small>
      </section>
      <template v-if="state.puzzle">
        <div class="game-grid"><div class="table-column"><GameTable :state="state" :busy="busy" :speaker="speaker"/>
        <section v-if="playing" class="panel controls">
          <template v-if="state.next_actor === 'teammate'"><p>轮到 {{ state.next_teammate?.name || 'AI 队友' }} 提问。若上次失败，可继续此回合。</p><button class="primary" :disabled="busy" @click="run(teammate)">继续队友回合</button></template>
          <form @submit.prevent="ask"><label for="question">你的问题（是 / 否 / 无关）</label><textarea id="question" v-model="text" maxlength="300" required :disabled="busy || !playerTurn" placeholder="这与他的身高有关吗？"/><button class="primary" :disabled="busy || !playerTurn">提问</button></form>
          <details><summary>我要提交完整还原</summary><form @submit.prevent="run(async () => { speaker = 'host'; state = await api('final', { text: answer }) })"><label for="answer">请写出完整故事与原因</label><textarea id="answer" v-model="answer" maxlength="1500" required :disabled="busy || !playerTurn"/><button :disabled="busy || !playerTurn">提交答案并评分</button></form></details>
          <button class="subtle" :disabled="busy" @click="run(async () => { state = await api('reveal', {}) })">结束本局并揭晓汤底</button>
        </section>
        </div><ConversationLog :history="state.history"/></div>
        <ScoreReport v-if="state.report" :report="state.report"/>
      </template>
      </template>
    </template>
  </main>
</template>
