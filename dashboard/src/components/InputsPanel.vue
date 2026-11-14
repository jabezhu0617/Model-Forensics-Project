<script setup lang="ts">
import DOMPurify from 'dompurify';
import type { Experiment } from '../types';
defineProps<{experiments:Experiment[]}>();
const sanitize=(html:string)=>DOMPurify.sanitize(html,{ALLOWED_TAGS:['p','pre','code','mark','div','span','h3','h4','ul','ol','li','strong','em','br'],ALLOWED_ATTR:['class']});
</script>
<template><div class="input-columns" :class="{single:experiments.length===1}"><article v-for="e in experiments" :key="e.id" class="input-column"><header><span class="eyebrow">{{e.sign==='−'?'DECREASE CONCEALMENT':e.sign==='+'?'INCREASE CONCEALMENT':'BASELINE PROMPT'}}</span><h2>{{e.sign?`${e.sign} intervention`:'Original inputs'}}</h2><a class="text-link" :href="`/downloads/${e.id}-inputs.html`" target="_blank" rel="noopener">Open original input export ↗</a></header><details v-for="section in e.inputs" :key="section.title" :open="/scratchpad|notes_to_self|deployment|user prompt/i.test(section.title)"><summary>{{section.title}}</summary><div class="prompt-content" v-html="sanitize(section.html)"></div></details></article></div></template>
