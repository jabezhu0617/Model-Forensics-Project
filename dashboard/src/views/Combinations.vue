<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { dataset } from '../data';
import { studyScope } from '../study-scope';
import type { Dataset } from '../types';
import HypothesisComparisons from '../components/HypothesisComparisons.vue';
const data=ref<Dataset|null>(null);
onMounted(async()=>{data.value=await dataset();});
const archive=computed(()=>data.value?studyScope(data.value).archive:null);
</script>
<template><template v-if="data&&archive">
  <RouterLink to="/" class="back-link">← Baseline and H0–H4</RouterLink>
  <div class="page-heading"><div><p class="eyebrow">HISTORICAL EVIDENCE</p><h1>Combination archive</h1><p class="lead">Preserved pairs, triples, and larger combinations.<br class="desktop-only"> These experiments are outside the current five-hypothesis focus.</p></div><a href="/downloads/combination-archive-results.json" class="button secondary" download>↓ Download archive results</a></div>
  <div class="stat-grid three"><div class="stat"><span>Archived combinations</span><strong>{{archive.hypotheses.length}}</strong><small>Four completed rounds</small></div><div class="stat"><span>Archived trials</span><strong>{{archive.totalRuns}}</strong><small>10 trials per positive and negative arm</small></div><div class="stat"><span>Reference baseline</span><strong>33.3%</strong><small>The original 20/60 baseline</small></div></div>
  <HypothesisComparisons :data="data" :hypotheses="archive.hypotheses" archived/>
  <div class="method-note"><span>ⓘ</span><p>Original prompts, scores and transcripts remain available for historical review. <RouterLink to="/methods?scope=archive">Read archived reports →</RouterLink> · <a href="/downloads/viewer-laptop.zip" download>Download the full historical study ZIP</a></p></div>
</template></template>
