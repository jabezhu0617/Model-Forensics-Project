<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { dataset, percent } from '../data';
import { studyScope } from '../study-scope';
import type { Dataset } from '../types';
import ResultsChart from '../components/ResultsChart.vue';
import HypothesisComparisons from '../components/HypothesisComparisons.vue';
const data=ref<Dataset|null>(null);
onMounted(async()=>{data.value=await dataset();});
const focus=computed(()=>data.value?studyScope(data.value).focus:null);
const baseline=computed(()=>data.value?.experiments.find(e=>e.id==='r1-baseline'));
</script>
<template><template v-if="data&&focus">
  <div class="page-heading"><div><p class="eyebrow">EVALUATION TAMPERING · DEEPSEEK R1</p><h1>What changes concealment?</h1><p class="lead">Focus on the baseline and H0–H4, tested in both directions.<br class="desktop-only"> Compare both directions and review the evidence.</p></div><a href="/downloads/baseline-h0-h4-results.json" class="button secondary" download>↓ Download results</a></div>
  <div class="stat-grid">
    <div class="stat"><span>Baseline concealment</span><strong>{{baseline?percent(baseline.counts.concealed,baseline.runs.length):'—'}}</strong><small>20 of 60 trials · 95% CI 22.7–45.9%</small></div>
    <div class="stat"><span>Trials in focus</span><strong>{{focus.totalRuns}}</strong><small>60 baseline + 300 hypothesis trials</small></div>
    <div class="stat"><span>Base hypotheses</span><strong>{{focus.hypotheses.length}}</strong><small>30 trials in each positive and negative direction</small></div>
    <div class="stat"><span>Original screens scoring 2/2</span><strong>{{focus.hypotheses.filter(h=>h.score===2).length}}<em>/ {{focus.hypotheses.length}}</em></strong><small>Scores from the first ten trials per direction</small></div>
  </div>
  <ResultsChart/>
  <HypothesisComparisons :data="data" :hypotheses="focus.hypotheses"/>
  <div class="method-note"><span>ⓘ</span><p><strong>Current focus: baseline and H0–H4.</strong> Rates pool the original 10 trials and 20 follow-up trials per direction. The original ten-trial screening scores are preserved. These exploratory results do not establish a causal explanation or statistical significance. <RouterLink to="/methods">Read the protocol →</RouterLink></p></div>
</template></template>
