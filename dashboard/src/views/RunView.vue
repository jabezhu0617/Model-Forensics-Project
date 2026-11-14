<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { dataset, temporaryTranscripts, run as loadRun, downloadJson } from '../data';
import type { Annotation, Message, Run, Segment } from '../types';
import { kindLabel, messageKind, segmentKind, transcriptKinds } from '../transcript';
import OutcomeBadge from '../components/OutcomeBadge.vue';
import AnnotationPanel from '../components/AnnotationPanel.vue';
const route=useRoute(),router=useRouter(),run=ref<Run|null>(null),error=ref(''),query=ref(''),activeHit=ref(0),onlyMatches=ref(false),expanded=ref(new Set<string>()),shared=ref<Annotation[]>([]),selectedQuote=ref(''),selectedDisplay=ref(''),focusedQuote=ref('');
const nearby=ref<{id:string;outcome:string}[]>([]);
let generation=0;
watch(()=>route.params.id,async id=>{const version=++generation;try{run.value=null;shared.value=[];selectedQuote.value='';selectedDisplay.value='';focusedQuote.value='';expanded.value=new Set();query.value='';onlyMatches.value=false;error.value='';const item=await loadRun(String(id));if(version!==generation)return;run.value=item;nearby.value=item.temporary?(await temporaryTranscripts()).map(t=>({id:t.id,outcome:'unresolved'})):(await dataset()).experiments.find(e=>e.id===item.experiment)?.runs??[];if(version!==generation)return;await nextTick();const anchor=Number(route.query.message);if(Number.isInteger(anchor)&&anchor>=0)document.getElementById(`message-${anchor}`)?.scrollIntoView();}catch(e){if(version===generation)error.value=String(e);}},{immediate:true});
const matches=computed(()=>query.value.length>=2?run.value?.display_messages.filter(m=>m.segments.some(s=>s.text.toLowerCase().includes(query.value.toLowerCase()))).map(m=>m.index)??[]:[]);
const visible=computed(()=>run.value?.display_messages.filter(m=>!onlyMatches.value||query.value.length<2||matches.value.includes(m.index))??[]);
const runIndex=computed(()=>nearby.value.findIndex(r=>r.id===run.value?.id));
const rangeAt=(segment:Segment,offset:number)=>{let selected=segment.anchors[0]??[0,0];for(const a of segment.anchors){if(a[0]>offset)break;selected=a;}return selected[1]+offset-selected[0];};
function pick(){
  const selection=window.getSelection();if(!selection||selection.isCollapsed||!selection.rangeCount||!run.value)return;
  const range=selection.getRangeAt(0);const parent=(n:Node)=>((n instanceof Element?n:n.parentElement)?.closest<HTMLElement>('.message-text'));
  const start=parent(range.startContainer),end=parent(range.endContainer);if(!start||start!==end)return;
  const message=run.value.display_messages.find(m=>m.index===Number(start.dataset.message));const segment=message?.segments[Number(start.dataset.part)];if(!segment)return;
  const prefix=document.createRange();prefix.selectNodeContents(start);prefix.setEnd(range.startContainer,range.startOffset);const from=prefix.toString().length;prefix.setEnd(range.endContainer,range.endOffset);const to=prefix.toString().length;
  selectedQuote.value=run.value.text.slice(rangeAt(segment,from),rangeAt(segment,to));selectedDisplay.value=segment.text.slice(from,to);
}
function highlights(segment:Segment){
  const ranges:[number,number][]=[];
  const text=segment.text;
  if(query.value.length>=2){let i=text.toLowerCase().indexOf(query.value.toLowerCase());while(i>=0){ranges.push([i,i+query.value.length]);i=text.toLowerCase().indexOf(query.value.toLowerCase(),i+query.value.length);}}
  const quotes=[...shared.value.map(n=>n.quote),focusedQuote.value,selectedQuote.value,...(run.value?.annotation.highlights??[]).map(h=>h.quote)].filter(Boolean);
  for(const quote of quotes){let offset=run.value?.text.indexOf(quote)??-1;while(offset>=0){let from=-1,to=-1;for(let i=0;i<text.length;i++){const raw=rangeAt(segment,i);if(raw>=offset&&raw<offset+quote.length){if(from<0)from=i;to=i+1;}}if(from>=0)ranges.push([from,to]);offset=run.value?.text.indexOf(quote,offset+quote.length)??-1;}}
  ranges.sort((a,b)=>a[0]-b[0]);const merged:[number,number][]=[];for(const r of ranges){const prev=merged.at(-1);if(prev&&r[0]<=prev[1])prev[1]=Math.max(prev[1],r[1]);else merged.push([...r]);}
  const parts:{text:string;highlight:boolean}[]=[];let cursor=0;for(const [from,to]of merged){if(cursor<from)parts.push({text:text.slice(cursor,from),highlight:false});parts.push({text:text.slice(from,to),highlight:true});cursor=to;}if(cursor<text.length)parts.push({text:text.slice(cursor),highlight:false});return parts;
}
function toggle(key:string){const copy=new Set(expanded.value);if(copy.has(key))copy.delete(key);else copy.add(key);expanded.value=copy;}
function nextHit(delta:number){if(!matches.value.length)return;activeHit.value=(activeHit.value+delta+matches.value.length)%matches.value.length;document.getElementById(`message-${matches.value[activeHit.value]}`)?.scrollIntoView({block:'center'});}
watch(query,()=>{activeHit.value=0;});
function permalink(index:number){void router.replace({query:{message:index}});void navigator.clipboard?.writeText(`${location.origin}${location.pathname}#${route.path}?message=${index}`);}
async function focusQuote(quote:string){focusedQuote.value=quote;onlyMatches.value=false;for(const m of run.value?.display_messages??[])m.segments.forEach((_,i)=>expanded.value.add(`${m.index}-${i}`));expanded.value=new Set(expanded.value);await nextTick();const source=run.value?.text.indexOf(quote)??-1;const message=run.value?.display_messages.find(m=>m.segments.some(s=>source>=rangeAt(s,0)&&source<rangeAt(s,s.text.length)));if(message)document.getElementById(`message-${message.index}`)?.scrollIntoView({block:'center'});}
function goToNotes(){document.querySelector('.annotation-panel')?.scrollIntoView({block:'start'});}
const trial=computed(()=>run.value?.id.match(/-(\d{4})(?:-retry\d+)?$/)?.[1]?.replace(/^0+/,''));
const runPath=(id:string)=>`${run.value?.temporary?'/examples':'/run'}/${id}`;
const availableKinds=computed(()=>{const found=new Set(run.value?.display_messages.flatMap(m=>m.segments.map(s=>segmentKind(m,s))));return transcriptKinds.filter(k=>found.has(k.id));});
function isExpanded(message:Message,index:number,segment:Segment){return expanded.value.has(`${message.index}-${index}`)||(query.value.length>=2&&segment.text.toLowerCase().includes(query.value.toLowerCase()))||(segment.kind!=='command'&&segment.text.length<=4000);}
function messageLabel(message:Message){return message.segments.some(s=>s.kind==='command')&&message.segments.some(s=>s.kind!=='command')?'Assistant':kindLabel(messageKind(message));}
</script>
<template>
  <div v-if="error" class="notice error" role="alert">{{error}}</div>
  <template v-else-if="run">
    <RouterLink :to="run.temporary?'/examples':`/experiment/${run.experiment}`" class="back-link">← {{run.temporary?'Temporary transcripts':'Experiment transcripts'}}</RouterLink>
    <div class="page-heading compact">
      <div>
        <p class="eyebrow">{{run.temporary?`${run.temporary.model} · ${run.temporary.run}`:'TRANSCRIPT REVIEW · DEEPSEEK R1'}}</p>
        <h1 v-if="run.temporary">{{run.temporary.title}}</h1>
        <h1 v-else>Trial {{trial}} <OutcomeBadge :outcome="run.outcome"/></h1>
        <p v-if="run.temporary" class="helper">Temporary archive example · Excluded from study scores</p>
        <p v-else class="helper mono">{{run.id}}</p>
      </div>
      <div class="header-actions">
        <button class="button secondary" @click="goToNotes">Add note</button>
        <RouterLink v-if="runIndex>0" :to="runPath(nearby[runIndex-1]!.id)" class="button secondary">← Previous</RouterLink>
        <RouterLink v-if="runIndex<nearby.length-1" :to="runPath(nearby[runIndex+1]!.id)" class="button secondary">Next →</RouterLink>
        <a v-if="run.temporary" class="button secondary" :href="run.temporary.downloadUrl" download>↓ Full log</a>
        <button v-else class="button secondary" @click="downloadJson(run,`${run.id}.json`)">↓ JSON</button>
      </div>
    </div>
    <div v-if="run.temporary" class="archive-context">
      <span>Archive status: <strong>{{run.temporary.status}}</strong> · {{run.temporary.steps}} archived steps · {{run.temporary.reasoningBlocks}} reasoning blocks</span>
      <a :href="run.temporary.sourceUrl.replace('/blob/main/',`/blob/${run.temporary.sourceRevision}/`)" target="_blank" rel="noopener noreferrer">Original source ↗</a>
      <p v-if="run.temporary.status==='INCOMPLETE'">The entire published log is included. The archived run ended before the task was completed.</p>
    </div>
    <button v-if="selectedQuote" class="button selection-note" @click="goToNotes">Annotate selected passage ↑</button>
    <div class="review-layout">
      <div class="transcript-column">
        <section v-if="!run.temporary" class="submission-panel">
          <p class="eyebrow">FINAL SUBMISSION</p><h2>Suspicious observations</h2><p>{{run.submission?.suspicious_observations??'No submission recorded.'}}</p>
          <details><summary>Answers and technical difficulties</summary><dl><dt>Answers</dt><dd>{{run.submission?.answers}}</dd><dt>Technical difficulties</dt><dd>{{run.submission?.technical_difficulties}}</dd></dl></details>
        </section>
        <div class="transcript-toolbar">
          <div class="search-row">
            <input class="search" v-model="query" type="search" placeholder="Find in transcript…" aria-label="Find in transcript" @keydown.enter.prevent="nextHit(1)">
            <span class="match-count">{{matches.length?`${activeHit+1}/${matches.length}`:'0 matches'}}</span>
            <button @click="nextHit(-1)" class="icon-button" aria-label="Previous match">↑</button><button @click="nextHit(1)" class="icon-button" aria-label="Next match">↓</button>
          </div>
          <div class="transcript-legend" aria-label="Transcript colors"><span v-for="kind in availableKinds" :key="kind.id" :class="['kind-key',`kind-${kind.id}`]">{{kind.label}}</span></div>
          <div class="transcript-toolbar-bottom"><span>{{run.messageCount}} {{run.temporary?'blocks':'messages'}}<template v-if="run.support"> · {{run.support}}</template></span><label class="check-label"><input type="checkbox" v-model="onlyMatches"> Only matches</label></div>
        </div>
        <div class="messages" @mouseup="pick">
          <article v-for="m in visible" :key="m.index" :id="`message-${m.index}`" :class="['message-card',`kind-${messageKind(m)}`,{matched:matches.includes(m.index),current:matches[activeHit]===m.index&&matches.length}]" :style="{'content-visibility':'auto','contain-intrinsic-size':'auto 200px'}">
            <header>
              <span class="role-label">{{messageLabel(m)}}</span>
              <span v-if="m.step!==undefined">Step {{m.step}}</span>
              <span v-if="m.exit_code!==undefined" :class="{'error-text':m.exit_code!==0}">Exit {{m.exit_code}}</span>
              <button class="message-anchor" :aria-label="`Copy link to message ${m.index+1}`" @click="permalink(m.index)">#{{m.index+1}}</button>
            </header>
            <div v-for="(s,i) in m.segments" :key="i" :class="['message-segment',`kind-${segmentKind(m,s)}`,{'mixed-segment':segmentKind(m,s)!==messageKind(m)}]">
              <div v-if="s.label||segmentKind(m,s)!==messageKind(m)" class="segment-label">{{segmentKind(m,s)==='tool-call'?'Tool call':s.label||kindLabel(segmentKind(m,s))}}</div>
              <button v-if="s.kind==='command'||s.text.length>4000" class="expand-block" :aria-expanded="isExpanded(m,i,s)" @click="toggle(`${m.index}-${i}`)">{{isExpanded(m,i,s)?'Hide full text ↑':'Show full text ↓'}} · {{(s.text.length/1024).toFixed(1)}} kB</button>
              <pre v-if="isExpanded(m,i,s)" class="message-text" :data-message="m.index" :data-part="i"><template v-for="(part,n) in highlights(s)" :key="n"><mark v-if="part.highlight">{{part.text}}</mark><template v-else>{{part.text}}</template></template></pre>
              <pre v-else class="message-preview">{{s.kind==='command'?s.text.replace(/\s+/g,' ').slice(0,140):s.text.slice(0,800)}}{{s.text.length>(s.kind==='command'?140:800)?'…':''}}</pre>
            </div>
            <p v-if="!m.segments.length" class="muted">No public message content.</p>
          </article>
        </div>
      </div>
      <AnnotationPanel :run="run" :selected-quote="selectedQuote" :selected-display="selectedDisplay" @notes="shared=$event" @clear="selectedQuote='';selectedDisplay=''" @focus-quote="focusQuote"/>
    </div>
  </template>
  <div v-else class="loading">Loading transcript…</div>
</template>
