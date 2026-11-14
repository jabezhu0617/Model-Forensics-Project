<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { temporaryTranscripts } from '../data';
import type { TemporarySummary } from '../types';
const transcripts = ref<TemporarySummary[]>([]), error = ref(''), loading = ref(true);
onMounted(async () => {
  try { transcripts.value = await temporaryTranscripts(); }
  catch (e) { error.value = String(e); }
  finally { loading.value = false; }
});
</script>
<template>
  <div class="page-heading"><div><h1>Temporary transcripts</h1><p class="lead">Public archive examples with reasoning traces. Separate from the study’s results and scores.</p></div></div>
  <div v-if="error" class="notice error" role="alert">{{error}}</div>
  <div v-else-if="loading" class="loading">Loading transcripts…</div>
  <div v-else class="temporary-list">
    <article v-for="item in transcripts" :key="item.id" class="panel temporary-card">
      <div><p class="eyebrow">{{item.model}} · {{item.run}}</p><h2><RouterLink :to="`/examples/${item.id}`">{{item.title}}</RouterLink></h2><p class="helper">{{item.steps}} archived steps · {{item.reasoningBlocks}} reasoning blocks · {{item.toolCalls}} tool calls</p><p class="helper">Archive status: <strong>{{item.status}}</strong></p></div>
      <RouterLink class="button secondary" :to="`/examples/${item.id}`">Read transcript →</RouterLink>
    </article>
  </div>
</template>
