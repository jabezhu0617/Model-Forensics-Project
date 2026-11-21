<script setup lang="ts">
import { computed, ref } from 'vue';
import { results, roundNames } from '../data';
import type { Dataset, Hypothesis } from '../types';
import RateBar from './RateBar.vue';
const props=defineProps<{data:Dataset;hypotheses:Hypothesis[];archived?:boolean}>();
const query=ref(''),strongOnly=ref(false),stage=ref(-1);
const filtered=computed(()=>props.hypotheses.filter(h=>(!props.archived||stage.value<0||h.round===stage.value)&&(!strongOnly.value||h.score===2)&&`${h.label} ${h.title}`.toLowerCase().includes(query.value.toLowerCase())));
const arms=(h:Hypothesis,sign:string)=>props.data.experiments.filter(e=>h.arms.includes(e.id)&&e.sign===sign).map(e=>({id:e.id,variant:e.variant,label:e.label,...results(e)}));
</script>
<template>
  <section class="panel comparison-panel">
    <div class="panel-heading"><div><h2>{{archived?'Archived hypothesis combinations':'H0–H4 comparisons'}}</h2><p>Concealment rates for each direction. Rate markers show the 33.3% baseline.</p></div><span class="muted">{{filtered.length}} {{archived?'combinations':'hypotheses'}}</span></div>
    <div v-if="archived" class="stage-tabs"><button @click="stage=-1" :class="{selected:stage===-1}">All combinations</button><button v-for="i in 4" :key="i" @click="stage=i" :class="{selected:stage===i}">Round {{i}}</button></div>
    <div class="table-toolbar"><input class="search" type="search" v-model="query" :aria-label="archived?'Search combinations':'Search hypotheses'" :placeholder="archived?'Search archived combinations…':'Search the five hypotheses…'"><label class="check-label"><input type="checkbox" v-model="strongOnly"> Show 2/2 only</label></div>
    <div class="table-scroll"><table class="data-table comparisons"><thead><tr><th>{{archived?'Combination':'Hypothesis'}}</th><th>− Lower direction</th><th>+ Higher direction</th><th>{{archived?'Screening score':'Original screening score'}}</th><th></th></tr></thead><tbody>
      <tr v-for="h in filtered" :key="h.id"><td><RouterLink :to="`/hypothesis/${h.id}`" class="hypothesis-label">{{h.label}}</RouterLink><p class="hypothesis-description">{{h.title}}</p><span class="round-label">{{archived?roundNames[h.round]:'Base hypothesis'}}</span></td><td v-for="sign in ['−','+'] as const" :key="sign"><div v-for="arm in arms(h,sign)" :key="arm.id"><small v-if="arms(h,sign).length>1" class="score-caption">{{arm.variant?arm.label:'Original'}}</small><RateBar :count="arm.counts.concealed" :total="arm.total" :direction="sign"/></div></td><td><span :class="['score-badge',{strong:h.score===2}]">{{h.score??'—'}} / 2</span><small class="score-caption">{{h.score===2?'Both supported':h.score===1?'One supported':'Neither supported'}}</small></td><td><RouterLink :to="`/hypothesis/${h.id}`" :aria-label="`Open ${h.label}`">→</RouterLink></td></tr>
      <tr v-if="!filtered.length"><td colspan="5" class="empty-state">No {{archived?'combinations':'hypotheses'}} match these filters.</td></tr>
    </tbody></table></div>
  </section>
</template>
