<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { dataset, reasoningRuns, reasoningTrace, temporaryTranscripts, run as loadRun, downloadJson } from '../data';
import type { Message, ReasoningTrace, Run, Segment } from '../types';
import { kindLabel, segmentKind, transcriptKinds, type TranscriptKind } from '../transcript';
import { studyScope } from '../study-scope';
import { connectReasoningFolder, hasPrivateReasoning, privateReasoning } from '../private-reasoning';
import OutcomeBadge from '../components/OutcomeBadge.vue';
const route=useRoute(),router=useRouter(),run=ref<Run|null>(null),error=ref(''),query=ref(''),activeHit=ref(0),onlyMatches=ref(false),expanded=ref(new Set<string>());
const nearby=ref<{id:string;outcome:string}[]>([]),archived=ref(false);
const hiddenKinds=ref<Set<string>>(new Set(['reasoning']));
const traceAvailable=ref(false),trace=ref<ReasoningTrace|null>(null),tracePending=ref(false),traceError=ref('');
const focused=ref(false),connected=ref(false),fileInput=ref<HTMLInputElement|null>(null);
const connecting=ref(false),connectionStatus=ref('');
let eligible=new Set<string>();
let generation=0;
watch(()=>route.params.id,async id=>{
  const version=++generation;
  run.value=null; nearby.value=[]; archived.value=false; expanded.value=new Set(); query.value=''; onlyMatches.value=false; error.value='';
  hiddenKinds.value=new Set(['reasoning']); trace.value=null; traceAvailable.value=false; tracePending.value=false; traceError.value='';
  focused.value=false; connected.value=false; connectionStatus.value='';
  try{
    const item=await loadRun(String(id));
    if(version!==generation)return;
    const [study,examples]=await Promise.all([item.temporary?null:dataset(),item.temporary?temporaryTranscripts():[]]);
    if(version!==generation)return;
    const source=study?.experiments.find(e=>e.id===item.experiment);
    archived.value=(source?.round??0)>0;
    nearby.value=item.temporary?examples.map(t=>({id:t.id,outcome:'unresolved'})):source?.runs??[];
    eligible=new Set(study?studyScope(study).focus.experiments.flatMap(e=>e.runs.flatMap(r=>r.replaces?[r.id,r.replaces.id]:[r.id])):[]);
    const inFocus=eligible.has(item.id)&&item.reasoning_available;
    if(inFocus){
      const [publicIds,local]=await Promise.all([reasoningRuns().catch(():string[]=>[]),hasPrivateReasoning(item.id).catch(()=>false)]);
      if(version!==generation)return;
      traceAvailable.value=publicIds.includes(item.id);
      connected.value=local;
    }
    focused.value=inFocus;
    run.value=item;
    await nextTick();
    if(version!==generation)return;
    const anchor=Number(route.query.message);
    if(Number.isInteger(anchor)&&anchor>=0)document.getElementById(`message-${anchor}`)?.scrollIntoView();
  }catch(e){if(version===generation)error.value=String(e);}
},{immediate:true});
function isShown(kind:string){return !hiddenKinds.value.has(kind);}
function onKindClick(kind:TranscriptKind,event:MouseEvent){
  if(kind==='reasoning'&&focused.value&&!connected.value&&!traceAvailable.value){
    event.preventDefault();
    chooseReasoningFolder();
  }
}
async function setKind(kind:TranscriptKind,shown:boolean){
  const item=run.value;
  if(kind==='reasoning'&&shown&&focused.value&&!connected.value&&!traceAvailable.value&&!trace.value){
    chooseReasoningFolder();
    return;
  }
  const hidden=new Set(hiddenKinds.value);
  if(shown)hidden.delete(kind);else hidden.add(kind);
  hiddenKinds.value=hidden;
  if(kind!=='reasoning'||!shown||!item||!focused.value||trace.value||tracePending.value)return;
  const version=generation;
  tracePending.value=true;
  traceError.value='';
  try{
    const result=traceAvailable.value?await reasoningTrace(item.id):await privateReasoning(item.id);
    if(!result||result.transcript_hash!==item.transcript_hash||!Array.isArray(result.blocks)||!result.blocks.length)
      throw new Error('Transcript version mismatch');
    if(version===generation)trace.value=result;
  }catch{
    if(version===generation){
      hiddenKinds.value=new Set([...hiddenKinds.value,'reasoning']);
      traceError.value='Reasoning could not be loaded. Check Reasoning to try again.';
    }
  }finally{if(version===generation)tracePending.value=false;}
}
function chooseReasoningFolder(){
  if(connecting.value)return;
  const input=fileInput.value;
  if(input){input.setAttribute('webkitdirectory','');input.click();}
}
async function connectFolder(event:Event){
  const input=event.target as HTMLInputElement;
  if(!input.files?.length||connecting.value)return;
  const version=generation;
  connecting.value=true; connectionStatus.value='';
  try{
    const saved=await connectReasoningFolder(input.files,eligible);
    if(version!==generation)return;
    const item=run.value;
    connected.value=!!item&&(connected.value||saved.has(item.id));
    trace.value=null;
    hiddenKinds.value=new Set([...hiddenKinds.value,'reasoning']);
    connectionStatus.value=connected.value?`Connected ${saved.size} runs. Check Reasoning to show it.`:`Connected ${saved.size} runs. This run isn’t in that folder.`;
  }catch{
    if(version===generation)connectionStatus.value='Could not open the prepared reasoning folder. Select it and try again.';
  }finally{connecting.value=false;input.value='';}
}
const filteredMessages=computed(()=>{
  const byMessage=new Map(isShown('reasoning')?trace.value?.blocks.map(b=>[b.message,b.text]):[]);
  return (run.value?.display_messages??[]).flatMap(m=>{
    const segments=m.segments.map((segment,index)=>({segment,index,kind:segmentKind(m,segment)})).filter(s=>isShown(s.kind));
    const reasoning=byMessage.get(m.index);
    if(reasoning){
      segments.unshift({segment:{text:reasoning,anchors:[],label:'Provider reasoning',kind:'reasoning'},index:-1,kind:'reasoning'});
    }
    if(!segments.length&&(m.segments.length||!isShown(m.role)))return [];
    const kinds=new Set(segments.map(s=>s.kind));
    return [{...m,parts:segments,kind:kinds.size===1?segments[0]!.kind:m.role}];
  });
});
const searchTerm=computed(()=>query.value.toLowerCase());
const matches=computed(()=>searchTerm.value.length>=2?filteredMessages.value.filter(m=>m.parts.some(({segment})=>segment.text.toLowerCase().includes(searchTerm.value))).map(m=>m.index):[]);
const visible=computed(()=>!onlyMatches.value||searchTerm.value.length<2?filteredMessages.value:filteredMessages.value.filter(m=>matches.value.includes(m.index)));
const runIndex=computed(()=>nearby.value.findIndex(r=>r.id===(run.value?.supersededBy??run.value?.id)));
const rangeAt=(segment:Segment,offset:number)=>{let selected=segment.anchors[0]!;for(const a of segment.anchors){if(a[0]>offset)break;selected=a;}return selected[1]+offset-selected[0];};
function highlights(segment:Segment){
  const ranges:[number,number][]=[];
  const text=segment.text;
  if(query.value.length>=2){let i=text.toLowerCase().indexOf(query.value.toLowerCase());while(i>=0){ranges.push([i,i+query.value.length]);i=text.toLowerCase().indexOf(query.value.toLowerCase(),i+query.value.length);}}
  const quotes=segment.anchors.length?(run.value?.annotation.highlights??[]).map(h=>h.quote).filter(Boolean):[];
  for(const quote of quotes){let offset=run.value?.text.indexOf(quote)??-1;while(offset>=0){let from=-1,to=-1;for(let i=0;i<text.length;i++){const raw=rangeAt(segment,i);if(raw>=offset&&raw<offset+quote.length){if(from<0)from=i;to=i+1;}}if(from>=0)ranges.push([from,to]);offset=run.value?.text.indexOf(quote,offset+quote.length)??-1;}}
  ranges.sort((a,b)=>a[0]-b[0]);const merged:[number,number][]=[];for(const r of ranges){const prev=merged.at(-1);if(prev&&r[0]<=prev[1])prev[1]=Math.max(prev[1],r[1]);else merged.push([...r]);}
  const parts:{text:string;highlight:boolean}[]=[];let cursor=0;for(const [from,to]of merged){if(cursor<from)parts.push({text:text.slice(cursor,from),highlight:false});parts.push({text:text.slice(from,to),highlight:true});cursor=to;}if(cursor<text.length)parts.push({text:text.slice(cursor),highlight:false});return parts;
}
function toggle(key:string){const copy=new Set(expanded.value);if(copy.has(key))copy.delete(key);else copy.add(key);expanded.value=copy;}
function nextHit(delta:number){if(!matches.value.length)return;activeHit.value=(activeHit.value+delta+matches.value.length)%matches.value.length;document.getElementById(`message-${matches.value[activeHit.value]}`)?.scrollIntoView({block:'center'});}
watch(matches,()=>{activeHit.value=0;});
function permalink(index:number){void router.replace({query:{message:index}});void navigator.clipboard?.writeText(`${location.origin}${location.pathname}#${route.path}?message=${index}`);}
async function showFileRead(index:number){
  await setKind('tool',true);
  await nextTick();
  document.getElementById(`message-${index}`)?.scrollIntoView({block:'start'});
}
const trial=computed(()=>run.value?.replaces?.index??run.value?.id.match(/-(\d{4})(?:-retry\d+)?$/)?.[1]?.replace(/^0+/,''));
const runPath=(id:string)=>`${run.value?.temporary?'/examples':'/run'}/${id}`;
const availableKinds=computed(()=>{
  const found=new Set(run.value?.display_messages.flatMap(m=>m.segments.length?m.segments.map(s=>segmentKind(m,s)):[m.role]));
  if(focused.value)found.add('reasoning');
  if(run.value?.submission)found.add('submission');
  return transcriptKinds.filter(k=>found.has(k.id));
});
function isExpanded(message:Message,index:number,segment:Segment){return expanded.value.has(`${message.index}-${index}`)||(query.value.length>=2&&segment.text.toLowerCase().includes(query.value.toLowerCase()))||(segment.kind!=='command'&&segment.text.length<=4000);}
</script>
<template>
  <div v-if="error" class="notice error" role="alert">{{error}}</div>
  <template v-else-if="run">
    <RouterLink :to="run.temporary?'/examples':`/experiment/${run.experiment}`" class="back-link">← {{run.temporary?'Temporary transcripts':'Experiment transcripts'}}</RouterLink>
    <p v-if="archived" class="helper">Archived combination transcript · <RouterLink to="/combinations">Combination archive</RouterLink></p><div class="page-heading compact">
      <div>
        <p class="eyebrow">{{run.temporary?`${run.temporary.model} · ${run.temporary.run}`:'TRANSCRIPT REVIEW · DEEPSEEK R1'}}</p>
        <h1 v-if="run.temporary">{{run.temporary.title}}</h1>
        <h1 v-else>Trial {{trial}} <OutcomeBadge :outcome="run.outcome"/></h1>
        <p v-if="run.temporary" class="helper">Temporary archive example · Excluded from study scores</p>
        <p v-else class="helper mono">{{run.id}}</p>
      </div>
      <div class="header-actions">
        <RouterLink v-if="runIndex>0" :to="runPath(nearby[runIndex-1]!.id)" class="button secondary">← Previous</RouterLink>
        <RouterLink v-if="runIndex<nearby.length-1" :to="runPath(nearby[runIndex+1]!.id)" class="button secondary">Next →</RouterLink>
        <a v-if="run.temporary" class="button secondary" :href="run.temporary.downloadUrl" download>↓ Full log</a>
        <button v-else class="button secondary" @click="downloadJson(run,`${run.id}.json`)">↓ JSON</button>
      </div>
    </div>
    <div v-if="run.replaces" class="method-note">
      <span>ⓘ</span><p><strong>Required-read replacement.</strong> Verified reads for <template v-for="(index, file, position) in run.fileReads" :key="file">{{position?', ':''}}<RouterLink :to="{query:{message:index}}" @click="showFileRead(index)">{{file}}</RouterLink></template>. <RouterLink :to="`/run/${run.replaces.id}`">View the original transcript →</RouterLink></p>
    </div>
    <div v-else-if="run.supersededBy" class="method-note">
      <span>ⓘ</span><p><strong>Original transcript.</strong> The current results use the outcome of this slot’s <RouterLink :to="`/run/${run.supersededBy}`">required-read replacement →</RouterLink></p>
    </div>
    <div v-if="run.temporary" class="archive-context">
      <span>Archive status: <strong>{{run.temporary.status}}</strong> · {{run.temporary.steps}} archived steps · {{run.temporary.reasoningBlocks}} reasoning blocks</span>
      <a :href="run.temporary.sourceUrl.replace('/blob/main/',`/blob/${run.temporary.sourceRevision}/`)" target="_blank" rel="noopener noreferrer">Original source ↗</a>
      <p v-if="run.temporary.status==='INCOMPLETE'">The entire published log is included. The archived run ended before the task was completed.</p>
    </div>
    <div class="transcript-layout">
      <div class="transcript-column">
        <div class="transcript-toolbar">
          <fieldset class="transcript-legend">
            <legend>Show transcript sections</legend>
            <label v-for="kind in availableKinds" :key="kind.id" :class="['kind-key',`kind-${kind.id}`]">
              <input type="checkbox" :checked="isShown(kind.id)" @click="onKindClick(kind.id, $event)" @change="setKind(kind.id, ($event.target as HTMLInputElement).checked)"> {{kind.label}}
            </label>
          </fieldset>
          <template v-if="focused">
            <input ref="fileInput" type="file" hidden aria-label="Prepared reasoning folder" @change="connectFolder">
            <p v-if="!connected&&!traceAvailable" class="transcript-filter-status"><button type="button" class="reasoning-connect" :disabled="connecting" @click="chooseReasoningFolder">Connect reasoning folder</button> · Files stay in this browser.</p>
            <p v-if="connectionStatus" class="transcript-filter-status" role="status">{{connectionStatus}}</p>
          </template>
          <p v-if="tracePending&&isShown('reasoning')" class="transcript-filter-status" role="status">Loading reasoning…</p>
          <p v-if="traceError" class="transcript-filter-status" role="status">{{traceError}}</p>
          <div class="search-row">
            <input class="search" v-model="query" type="search" placeholder="Find in transcript…" aria-label="Find in transcript" @keydown.enter.prevent="nextHit(1)">
            <span class="match-count">{{matches.length?`${activeHit+1}/${matches.length}`:'0 matches'}}</span>
            <button @click="nextHit(-1)" class="icon-button" aria-label="Previous match">↑</button><button @click="nextHit(1)" class="icon-button" aria-label="Next match">↓</button>
          </div>
          <div class="transcript-toolbar-bottom"><span>{{visible.length}} of {{run.messageCount}} {{run.temporary?'blocks':'messages'}}<template v-if="run.support"> · {{run.support}}</template></span><label class="check-label"><input type="checkbox" v-model="onlyMatches"> Only matches</label></div>
        </div>
        <section v-if="!run.temporary&&isShown('submission')" class="submission-panel">
          <p class="eyebrow">FINAL SUBMISSION</p><h2>Suspicious observations</h2><p>{{run.submission?.suspicious_observations??'No submission recorded.'}}</p>
          <details><summary>Answers and technical difficulties</summary><dl><dt>Answers</dt><dd>{{run.submission?.answers}}</dd><dt>Technical difficulties</dt><dd>{{run.submission?.technical_difficulties}}</dd></dl></details>
        </section>
        <div class="messages">
          <p v-if="!visible.length" class="empty-state">No messages match the selected sections and search.</p>
          <article v-for="m in visible" :key="m.index" :id="`message-${m.index}`" :class="['message-card',`kind-${m.kind}`,{matched:matches.includes(m.index),current:matches[activeHit]===m.index&&matches.length}]" :style="{'content-visibility':'auto','contain-intrinsic-size':'auto 200px'}">
            <header>
              <span class="role-label">{{kindLabel(m.kind)}}</span>
              <span v-if="m.step!==undefined">Step {{m.step}}</span>
              <span v-if="m.exit_code!==undefined" :class="{'error-text':m.exit_code!==0}">Exit {{m.exit_code}}</span>
              <button class="message-anchor" :aria-label="`Copy link to message ${m.index+1}`" @click="permalink(m.index)">#{{m.index+1}}</button>
            </header>
            <div v-for="{segment:s,index:i,kind} in m.parts" :key="i" :class="['message-segment',`kind-${kind}`,{'mixed-segment':kind!==m.kind}]">
              <div v-if="s.label||kind!==m.kind" class="segment-label">{{kind==='tool-call'&&s.kind==='command'?'Tool call':s.label||kindLabel(kind)}}</div>
              <button v-if="s.kind==='command'||s.text.length>4000" class="expand-block" :aria-expanded="isExpanded(m,i,s)" @click="toggle(`${m.index}-${i}`)">{{isExpanded(m,i,s)?'Hide full text ↑':'Show full text ↓'}} · {{(s.text.length/1024).toFixed(1)}} kB</button>
              <pre v-if="isExpanded(m,i,s)" class="message-text" :data-message="m.index" :data-part="i"><template v-for="(part,n) in highlights(s)" :key="n"><mark v-if="part.highlight">{{part.text}}</mark><template v-else>{{part.text}}</template></template></pre>
              <pre v-else class="message-preview">{{s.kind==='command'?s.text.replace(/\s+/g,' ').slice(0,140):s.text.slice(0,800)}}{{s.text.length>(s.kind==='command'?140:800)?'…':''}}</pre>
            </div>
            <p v-if="!m.segments.length" class="muted">No public message content.</p>
          </article>
        </div>
      </div>
    </div>
  </template>
  <div v-else class="loading">Loading transcript…</div>
</template>
