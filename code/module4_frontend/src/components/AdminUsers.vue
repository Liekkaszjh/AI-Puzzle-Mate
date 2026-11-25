<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'

const query = ref(''), users = ref([]), total = ref(0), offset = ref(0)
const busy = ref(false), error = ref(''), notice = ref('')

async function load() {
  busy.value = true
  error.value = ''
  try {
    const result = await api(`admin/users?q=${encodeURIComponent(query.value)}&limit=20&offset=${offset.value}`)
    users.value = result.users
    total.value = result.total
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function update(user, payload) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api(`admin/users/${user.id}`, payload, 'PATCH')
    notice.value = '用户资料已更新。'
    await load()
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
function search() { offset.value = 0; load() }
function page(delta) { offset.value += delta; load() }
function date(value) {
  return value ? new Date(value * 1000).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }) : '—'
}
onMounted(load)
</script>

<template>
  <section class="panel admin-users">
    <h2>注册用户管理</h2>
    <form class="admin-search" @submit.prevent="search">
      <label>搜索邮箱或昵称<input v-model="query" maxlength="100" :disabled="busy"></label>
      <button :disabled="busy">搜索</button>
    </form>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p class="muted">共 {{ total }} 位注册用户</p>
    <div class="admin-table-wrap">
      <table class="admin-table">
        <thead><tr><th>邮箱</th><th>昵称</th><th>注册时间</th><th>最近登录</th><th>游戏数</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="account in users" :key="account.id">
            <td>{{ account.email }}</td>
            <td><input v-model.trim="account.display_name" :aria-label="`${account.email} 的昵称`" maxlength="30" :disabled="busy"></td>
            <td>{{ date(account.created_at) }}</td><td>{{ date(account.last_login_at) }}</td>
            <td>{{ account.game_count }}</td><td>{{ account.is_active ? '启用' : '禁用' }}</td>
            <td class="admin-actions">
              <button :disabled="busy || !account.display_name" @click="update(account, { display_name: account.display_name })">保存昵称</button>
              <button :disabled="busy" @click="update(account, { is_active: !account.is_active })">{{ account.is_active ? '禁用账号' : '启用账号' }}</button>
            </td>
          </tr>
          <tr v-if="!users.length"><td colspan="7">没有符合条件的注册用户。</td></tr>
        </tbody>
      </table>
    </div>
    <div class="admin-pages">
      <button :disabled="busy || offset === 0" @click="page(-20)">上一页</button>
      <span>{{ total ? offset + 1 : 0 }}–{{ Math.min(offset + users.length, total) }} / {{ total }}</span>
      <button :disabled="busy || offset + users.length >= total" @click="page(20)">下一页</button>
    </div>
  </section>
</template>
