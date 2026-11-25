<script setup>
import { nextTick, ref, watch } from 'vue'
const props = defineProps({ history: { type: Array, required: true } })
const log = ref(null)
watch(() => props.history.length, async () => {
  await nextTick()
  if (log.value) log.value.scrollTop = log.value.scrollHeight
})
</script>

<template>
  <section class="panel conversation"><h2>桌边的对话</h2>
    <div ref="log" class="log" aria-live="polite">
      <p v-if="!history.length" class="muted">从一个具体的是非问题开始吧。</p>
      <article v-for="(turn, index) in history" :key="index" class="turn">
        <b>{{ turn.actor === 'player' ? '你' : 'AI 队友 · 小夏' }} <small>{{ turn.kind === 'final' ? '提交还原' : '提问' }}</small></b>
        <p>{{ turn.question }}</p><span class="verdict">汤主：{{ turn.verdict }}</span>
        <p v-if="turn.feedback" class="muted">{{ turn.feedback }}</p>
      </article>
    </div>
  </section>
</template>
