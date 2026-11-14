<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { api, downloadJson, listNotes } from '../data';
import type { Annotation, Run } from '../types';
const props=defineProps<{run:Run;selectedQuote:string;selectedDisplay:string}>();
const emit=defineEmits<{notes:[Annotation[]];clear:[];focusQuote:[string]}>();
const notes=ref<Annotation[]>([]),error=ref(''),message=ref(''),ready=ref(false),saving=ref(false),note=ref(''),reviewer=ref(''),outcome=ref(''),editing=ref<Annotation|null>(null),showRemoved=ref(false),history=ref<Annotation[]>([]),historyId=ref('');
try{reviewer.value=localStorage.getItem('viewer.reviewer')??'';}catch{}
const quote=computed(()=>editing.value?.quote??props.selectedQuote);
const currentNotes=computed(()=>notes.value.filter(n=>n.transcript_hash===props.run.transcript_hash));
let generation=0;
async function refresh(silent=false){
  const target=props.run.id,version=generation;
  try{const result=await listNotes(target,showRemoved.value);if(version!==generation)return;notes.value=result.annotations;emit('notes',result.annotations.filter(n=>!n.deleted&&n.transcript_hash===props.run.transcript_hash));ready.value=true;if(!silent)error.value='';}
  catch(e){if(version===generation){ready.value=false;error.value=e instanceof Error?e.message:'Shared review is unavailable.';}}
}
function reset(){editing.value=null;note.value='';outcome.value='';emit('clear');}
watch(()=>props.run.id,()=>{generation++;notes.value=[];history.value=[];ready.value=false;reset();void refresh();},{immediate:true});
watch(showRemoved,()=>void refresh());
const timer=setInterval(()=>void refresh(true),15000);onUnmounted(()=>clearInterval(timer));
async function save(){
  saving.value=true;error.value='';message.value='';
  try{
    const body={run_id:props.run.id,transcript_hash:props.run.transcript_hash,quote:quote.value,note:note.value,reviewer:reviewer.value||'Anonymous',outcome:outcome.value||null,...(editing.value?{revision:editing.value.revision}:{})};
    await api(editing.value?`annotations/${editing.value.id}`:'annotations',editing.value?'PATCH':'POST',body);
    try{localStorage.setItem('viewer.reviewer',reviewer.value);}catch{}
    reset();await refresh();message.value='Saved. This note is now shared with other visitors.';
  }catch(e){error.value=e instanceof Error?e.message:'Could not save note.';}finally{saving.value=false;}
}
function edit(item:Annotation){editing.value=item;note.value=item.note;outcome.value=item.outcome??'';message.value='';}
async function remove(item:Annotation){
  if(!window.confirm('Remove this shared note? Its history will remain available.'))return;
  try{await api(`annotations/${item.id}`,'DELETE',{revision:item.revision});await refresh();}catch(e){error.value=String(e);}
}
async function versions(item:Annotation){
  if(historyId.value===item.id){historyId.value='';return;}
  try{history.value=(await api<{history:Annotation[]}>(`annotations/${item.id}/history`)).history;historyId.value=item.id;}catch(e){error.value=String(e);}
}
async function restore(version:Annotation,current:Annotation){
  try{await api(`annotations/${current.id}`,'PATCH',{revision:current.revision,quote:version.quote,note:version.note,reviewer:reviewer.value||'Anonymous',outcome:version.outcome});historyId.value='';await refresh();}catch(e){error.value=String(e);}
}
const date=(value:string)=>new Intl.DateTimeFormat('en-US',{dateStyle:'medium',timeStyle:'short',timeZone:'America/Los_Angeles'}).format(new Date(value));
function exportNotes(){downloadJson({run:props.run.id,transcript_hash:props.run.transcript_hash,annotations:notes.value},`${props.run.id}-shared-notes.json`);}
</script>
<template><aside class="annotation-panel"><div class="annotation-heading"><div><p class="eyebrow">PUBLIC REVIEW</p><h2>Shared notes <span class="count-pill">{{currentNotes.filter(n=>!n.deleted).length}}</span></h2></div><button class="icon-button" @click="refresh()" title="Refresh shared notes" aria-label="Refresh shared notes">↻</button></div><p class="helper">Select a passage to highlight it, or add a note about this {{run.temporary?'transcript':'trial'}}. Anyone can read and edit shared notes.</p><div v-if="error" role="alert" class="notice error">{{error}}</div><div v-if="message" role="status" class="notice success">{{message}}</div>
<form class="note-form" @submit.prevent="save"><div v-if="quote" class="selected-quote"><span>Selected passage</span><p>{{editing?editing.quote:(selectedDisplay||selectedQuote)}}</p><button v-if="!editing" type="button" class="text-button" @click="emit('clear')">Clear selection</button></div><label>Your note<textarea v-model="note" required maxlength="8000" rows="4" :placeholder="run.temporary?'What stands out in this transcript?':'What does this trial tell us?'" /></label><label>Display name <span class="muted">(optional, unverified)</span><input v-model="reviewer" maxlength="80" placeholder="Anonymous" /></label><label v-if="!run.temporary">Suggest an outcome <span class="muted">(optional)</span><select v-model="outcome"><option value="">No suggestion</option><option value="concealed">Concealed</option><option value="reported">Reported</option><option value="unresolved">Unresolved</option></select></label><div class="form-actions"><button type="submit" class="button" :disabled="!ready||saving||!note.trim()">{{saving?'Saving…':editing?'Save changes':'Share note'}}</button><button v-if="editing" type="button" class="text-button" @click="reset">Cancel edit</button></div></form>
<div class="notes-controls"><label class="check-label"><input type="checkbox" v-model="showRemoved"> Show removed</label><button class="text-button" @click="exportNotes" :disabled="!notes.length">Export</button></div><p v-if="!currentNotes.length&&ready" class="empty-note">No shared notes yet. Add the first observation.</p><article v-for="item in currentNotes" :key="item.id" class="shared-note" :class="{removed:!!item.deleted}"><div class="note-meta"><strong>{{item.reviewer}}</strong><span>{{item.deleted?'Removed':`v${item.revision}`}}</span></div><small class="muted">{{date(item.updated_at)}} Pacific</small><button v-if="item.quote" class="quote-link" @click="emit('focusQuote',item.quote)">{{item.quote}}</button><p class="note-text">{{item.note}}</p><span v-if="item.outcome" class="suggestion">Suggests: {{item.outcome}}</span><div class="note-actions"><button v-if="!item.deleted" @click="edit(item)">Edit</button><button v-if="!item.deleted" @click="remove(item)">Remove</button><button @click="versions(item)">{{historyId===item.id?'Hide history':'History'}}</button></div><div v-if="historyId===item.id" class="note-history"><div v-for="version in history" :key="version.revision"><strong>Revision {{version.revision}} {{version.deleted?'· removed':''}}</strong><p>{{version.note}}</p><button v-if="version.revision!==item.revision&&!version.deleted" class="text-button" @click="restore(version,item)">Restore this revision</button><button v-if="item.deleted&&version.revision===item.revision" class="text-button" @click="restore(version,item)">Restore note</button></div></div></article><p v-if="notes.some(n=>n.transcript_hash!==run.transcript_hash)" class="helper">Some notes refer to an earlier transcript version and are excluded from this view.</p></aside></template>
