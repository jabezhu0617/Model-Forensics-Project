<script setup lang="ts">
import { computed } from 'vue';
import { percent } from '../data';
const props=defineProps<{count:number;total:number;direction?:string}>();
const width=computed(()=>props.total?props.count/props.total*156:0);
</script>
<template><div class="rate-cell"><svg viewBox="0 0 160 20" role="img" :aria-label="`${percent(count,total)} concealed; baseline 33.3 percent`"><rect x="0" y="6" width="156" height="8" rx="3" fill="#eef1f5"/><rect x="0" y="6" :width="width" height="8" rx="3" :fill="direction==='−'?'#8193b0':'#4167cc'"/><line x1="52" x2="52" y1="1" y2="19" stroke="#94a3b8" stroke-dasharray="2 2"/></svg><span>{{percent(count,total)}}<small>{{count}}/{{total}}</small></span></div></template>
