<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { dataset } from './data';
import type { Dataset } from './types';
const data=ref<Dataset|null>(null),error=ref('');
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
      </nav>
      <div class="sidebar-study"><p class="eyebrow">THIS STUDY</p><strong>Evaluation tampering</strong><p>DeepSeek R1 · 4 rounds</p><span class="live-dot"></span> {{data?.totalRuns??'…'}} recorded trials</div>
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
