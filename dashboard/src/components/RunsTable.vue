<script setup lang="ts">
import { computed, ref } from 'vue';
import type { Experiment } from '../types';
import OutcomeBadge from './OutcomeBadge.vue';
const props=defineProps<{experiments:Experiment[]}>();
const query=ref(''),outcome=ref('all');
const all=computed(()=>props.experiments.flatMap(e=>e.runs.map(r=>({...r,arm:e.sign}))));
const filtered=computed(()=>all.value.filter(r=>(outcome.value==='all'||r.outcome===outcome.value)&&(`${r.id} ${r.excerpt}`.toLowerCase().includes(query.value.toLowerCase()))));
</script>
<template>
  <div class="section-heading"><div><h2>Recorded trials</h2><p>Open a trial to inspect its messages and submission.</p></div><span class="muted">{{filtered.length}} of {{all.length}}</span></div>
  <div class="table-toolbar"><input class="search" v-model="query" type="search" placeholder="Search trials and final submissions…" aria-label="Search trials"><div class="segmented"><button v-for="v in ['all','concealed','reported','unresolved']" :key="v" @click="outcome=v" :class="{selected:outcome===v}">{{v}}</button></div></div>
  <div class="table-scroll"><table class="data-table run-table"><thead><tr><th>Trial</th><th>Outcome</th><th>Final observation</th><th>Messages</th><th></th></tr></thead><tbody>
    <tr v-for="r in filtered" :key="r.id"><td><RouterLink :to="`/run/${r.id}`" :title="r.id" class="trial-link">{{r.arm?`${r.arm} `:''}}Trial {{r.id.match(/-(\d{4})(?:-retry\d+)?$/)?.[1]?.replace(/^0+/,'')||r.id}}<small v-if="r.id.includes('retry')">Retried · latest attempt</small><small v-else-if="r.selected">Selected review sample</small></RouterLink></td><td><OutcomeBadge :outcome="r.outcome" /></td><td class="excerpt">{{r.excerpt||'No final observation recorded.'}}</td><td class="mono muted">{{r.messageCount}}</td><td><RouterLink :to="`/run/${r.id}`" aria-label="Open transcript">↗</RouterLink></td></tr>
    <tr v-if="!filtered.length"><td colspan="5" class="empty-state">No trials match these filters.</td></tr>
  </tbody></table></div>
</template>
