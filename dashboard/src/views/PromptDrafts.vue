<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { dataset, promptDraft, promptDraftIndex } from '../data';
import { proposedDiff } from '../prompt-diff';
import type { Experiment, PromptDraft, PromptDraftSummary } from '../types';

const route=useRoute();
const drafts=ref<PromptDraftSummary[]>([]), current=ref<PromptDraft|null>(null);
const testedVariants=ref(new Map<string,Experiment>());
const testedVariant=computed(()=>current.value?testedVariants.value.get(current.value.id):undefined);
const loading=ref(true), detailLoading=ref(false), error=ref(''), detailError=ref('');
const filter=ref('all'), groups=['H0','H1','H2','H3','H4'];
const sections:Record<string,string>={system:'System prompt',user:'User prompt'};
const comparisons=computed(()=>{
  const draft=current.value;
  if(!draft?.comparison)return [];
  const testedSections=draft.comparison.sections;
  return draft.sections.map(section=>{
    const tested=testedSections[section.key]??'';
    const parts=proposedDiff(tested,section.text);
    return {...section,tested,parts,removedOnly:tested!==section.text&&!parts.some(part=>part.added)};
  });
});
const visibleGroups=computed(()=>groups.filter(group=>drafts.value.some(d=>d.group===group&&(filter.value==='all'||filter.value===d.kind))));
const kindLabel=(kind:PromptDraftSummary['kind'])=>kind==='rewrite'?'Wording rewrite':'New variant';
onMounted(async()=>{
  try{
    const [index,study]=await Promise.all([promptDraftIndex(),dataset()]);
    drafts.value=index;
    testedVariants.value=new Map(study.experiments.flatMap(e=>e.variant?[[e.variant,e] as const]:[]));
  }
  catch{error.value='The draft index could not be loaded.';}
  finally{loading.value=false;}
});
watch([()=>route.params.id,loading],async ([id,isLoading],_,onCleanup)=>{
  current.value=null; detailError.value=''; detailLoading.value=false;
  if(!id||isLoading)return;
  if(!drafts.value.some(d=>d.id===id)){detailError.value='This draft was not found.';return;}
  let active=true;
  onCleanup(()=>{active=false;});
  detailLoading.value=true;
  try{const draft=await promptDraft(String(id));if(active)current.value=draft;}
  catch{if(active)detailError.value='The draft could not be loaded.';}
  finally{if(active)detailLoading.value=false;}
},{immediate:true});
</script>

<template>
  <RouterLink v-if="route.params.id" to="/prompt-drafts" class="back-link">← All prompt drafts</RouterLink>
  <div class="page-heading">
    <div>
      <p class="eyebrow">DEEPSEEK R1 · H0–H4<template v-if="current"> · {{testedVariant?'TESTED':'NOT RUN'}}</template></p>
      <h1>{{ current ? current.label+' · '+current.title : 'Proposed prompt edits' }}</h1>
      <p class="lead" v-if="current">
        {{kindLabel(current.kind)}} · Source: <span class="mono">{{current.sourceId}}</span>
      </p>
      <p class="lead" v-else>Review each prompt and its four attachments. Tested variants link to their results.</p>
    </div>
  </div>
  <p v-if="error||detailError" class="notice error" role="alert">{{error||detailError}}</p>
  <p v-else-if="loading||detailLoading" class="loading">Loading prompt drafts…</p>
  <template v-else-if="current">
    <div class="method-note draft-note">
      <p v-if="testedVariant"><strong>{{testedVariant.counts.concealed}} / {{testedVariant.runs.length}} concealed.</strong> <RouterLink :to="'/experiment/'+testedVariant.id">View results and transcripts →</RouterLink></p>
      <p v-else>{{current.comparison?'Compare the exact tested inputs with the proposed wording.':'This changes the setup and is a separate test.'}}
        </p>
      <p v-if="current.previewContact&&!testedVariant">The contact in the deployment notes is for the study scenario.</p>
    </div>
    <article v-if="current.comparison" :key="current.id" class="input-column prompt-draft draft-comparison">
      <header class="draft-comparison-pair">
        <div>
          <h2>Tested prompt</h2>
          <p>{{current.comparison.title}}</p>
          <p class="helper">
            {{current.comparison.originalTrials}} completed {{current.comparison.earlierScreen?'earlier':'original'}} trials<template v-if="current.comparison.followupTrials"> + {{current.comparison.followupTrials}} follow-up trials</template>
          </p>
          <RouterLink v-if="!current.comparison.earlierScreen" :to="{path:'/experiment/'+current.sourceId,query:{tab:'inputs'}}" class="text-link">Open the tested arm →</RouterLink>
          <RouterLink v-else :to="{path:'/experiment/r1-h1-tutor-selection',query:{tab:'inputs'}}" class="text-link">Current H1− arm: supervised tutor selection →</RouterLink>
        </div>
        <div>
          <h2>Proposed rewrite</h2>
          <p>{{current.label}} · {{current.title}}</p>
          <p class="helper">{{testedVariant?'30 completed trials':'No trials run'}}</p>
          <p class="helper"><mark class="draft-diff-mark">Highlight</mark> marks added or rewritten text.</p>
        </div>
      </header>
      <details v-for="section in comparisons" :key="section.key" :open="section.changed||section.key==='deployment_notes.txt'">
        <summary>
          {{sections[section.key]??section.key}}
          <small v-if="section.removedOnly" class="draft-edited">Removed text or spacing changes</small>
          <small v-else-if="section.changed" class="draft-edited">Edited</small>
          <small v-else-if="section.tested!==section.text" class="draft-edited">Preview contact</small>
          <small v-else class="muted">Same text</small>
        </summary>
        <div class="draft-comparison-pair">
          <div class="prompt-content tested-input"><h3>Tested</h3><pre>{{section.tested}}</pre></div>
          <div class="prompt-content proposed-input"><h3>Proposed</h3><pre><template v-for="(part,i) in section.parts" :key="i"><mark v-if="part.added" class="draft-diff-mark">{{part.text}}</mark><template v-else>{{part.text}}</template></template></pre></div>
        </div>
      </details>
    </article>
    <article v-else :key="current.id" class="input-column prompt-draft">
      <details v-for="section in current.sections" :key="section.key" :open="section.changed||section.key==='deployment_notes.txt'">
        <summary>{{sections[section.key]??section.key}} <small v-if="section.changed" class="draft-edited">Edited</small></summary>
        <div class="prompt-content"><pre>{{section.text}}</pre></div>
      </details>
    </article>
  </template>
  <template v-else-if="drafts.length">
    <div class="draft-filter">
      <label for="draft-kind">Show</label>
      <select id="draft-kind" v-model="filter">
        <option value="all">All {{drafts.length}} drafts</option>
        <option value="rewrite">Wording rewrites</option>
        <option value="variant">New variants</option>
      </select>
    </div>
    <section v-for="group in visibleGroups" :key="group" class="panel draft-group">
      <h2>{{group}}</h2>
      <ul>
        <li v-for="draft in drafts.filter(d=>d.group===group&&(filter==='all'||d.kind===filter))" :key="draft.id">
          <RouterLink :to="'/prompt-drafts/'+draft.id"><strong>{{draft.label}}</strong> · {{draft.title}}</RouterLink>
          <small>{{testedVariants.has(draft.id)?(draft.kind==='rewrite'?'Tested rewrite':'Tested variant'):kindLabel(draft.kind)}}</small>
        </li>
      </ul>
    </section>
  </template>
  <p v-else class="notice">No prompt drafts are included in this build.</p>
</template>
