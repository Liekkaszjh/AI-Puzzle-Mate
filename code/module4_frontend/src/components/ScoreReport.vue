<script setup>
defineProps({ report: { type: Object, required: true } })
const labels = { matched: '完整命中', partial: '部分命中', missing: '未提及', contradicted: '存在矛盾' }
</script>

<template>
  <section class="panel score"><h2>本局评分 <strong>{{ report.score }} / 100</strong></h2>
    <p>完整命中 {{ report.matched_count }} / {{ report.total_facts }} 条事实；部分命中计半分，各事实等权。</p>
    <article v-for="(fact, index) in report.facts" :key="index"><b>{{ fact.fact }}</b><span>{{ labels[fact.status] }}</span><p>{{ fact.reason }}</p></article>
    <details><summary>我的还原</summary><p>{{ report.answer }}</p></details>
  </section>
</template>
