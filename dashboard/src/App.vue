<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { dataset } from './data';
import { studyScope } from './study-scope';
import type { Dataset } from './types';
const data=ref<Dataset|null>(null),error=ref('');
const focusedTrials=computed(()=>data.value?studyScope(data.value).focus.totalRuns:'…');
onMounted(async()=>{try{data.value=await dataset();}catch(e){error.value=String(e);}});
</script>
<template>
  <div class="app-shell">
    <aside class="sidebar">
      <nav class="primary-nav" aria-label="Main navigation">
        <RouterLink to="/" :class="{active:$route.path==='/'}"><span>◫</span> Results overview</RouterLink>
        <RouterLink to="/experiment/r1-baseline" :class="{active:$route.path.includes('r1-baseline')}"><span>◷</span> Baseline study</RouterLink>
        <RouterLink to="/examples" :class="{active:$route.path.startsWith('/examples')}"><span>≋</span> Temp transcripts</RouterLink>
        <RouterLink to="/methods" :class="{active:$route.path==='/methods'}"><span>≡</span> Methods & exports</RouterLink>
        <RouterLink to="/combinations" class="archive-link" :class="{active:$route.path==='/combinations'}"><span>▤</span> Combination archive</RouterLink>
      </nav>
      <div class="sidebar-study"><p class="eyebrow">CURRENT FOCUS</p><strong>Baseline + H0–H4</strong><p>DeepSeek R1 · five hypotheses</p><span class="live-dot"></span> {{focusedTrials}} trials in focus</div>
    </aside>
    <div class="main-shell">
      <main id="main-content" class="content">
        <div v-if="error" role="alert" class="notice error">{{error}}</div>
        <RouterView v-else-if="data" />
        <div v-else class="loading">Loading the research index…</div>
      </main>
      <footer class="page-footer" v-if="data"><span>Model Forensics · Data {{data.version.slice(0,8)}} · Source {{data.sourceCommit}}</span><span>Observable behavior. Preserved evidence.</span></footer>
    </div>
  </div>
</template>
