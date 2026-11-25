<script setup>
defineProps({ state: { type: Object, required: true } })
</script>

<template>
  <section class="panel story">
    <span class="eyebrow">汤主 · 老陈</span>
    <h2>{{ state.puzzle.title }}</h2>
    <p class="surface">{{ state.puzzle.surface }}</p>
    <small>共 {{ state.puzzle.fact_count }} 条关键事实 · {{ state.turns }}/{{ state.max_turns }} 次互动</small>
    <p v-if="state.notice" role="status">{{ state.notice }}</p>
    <div v-if="state.solution" class="solution"><h3>故事真相</h3><p>{{ state.solution.bottom }}</p></div>
  </section>
</template>
