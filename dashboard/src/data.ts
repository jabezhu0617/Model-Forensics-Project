import type { Annotation, Dataset, Experiment, PromptDraft, PromptDraftSummary, ReasoningTrace, Run, TemporarySummary } from './types';
const cache=new Map<string,Promise<unknown>>();
async function get<T>(path:string):Promise<T>{
  let pending=cache.get(path);
  if(!pending){
    pending=fetch(path).then(async response=>{if(!response.ok)throw new Error('The requested research data could not be loaded.');return response.json() as Promise<T>;});
    cache.set(path,pending);pending.catch(()=>cache.delete(path));
  }
  return pending as Promise<T>;
}
export const dataset=()=>get<Dataset>('/data/index.json');
export const experiment=(id:string)=>get<Experiment>(`/data/experiments/${encodeURIComponent(id)}.json`);
export const run=(id:string)=>get<Run>(`/data/runs/${encodeURIComponent(id)}.json`);
export const reasoningRuns=()=>get<string[]>('/data/reasoning/index.json');
export const reasoningTrace=(id:string)=>get<ReasoningTrace>(`/data/reasoning/${encodeURIComponent(id)}.json`);
export const temporaryTranscripts=()=>get<TemporarySummary[]>('/data/temporary/index.json');
export const promptDraftIndex=()=>get<PromptDraftSummary[]>('/data/prompt-drafts/index.json');
export const promptDraft=(id:string)=>get<PromptDraft>(`/data/prompt-drafts/${encodeURIComponent(id)}.json`);
export async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{
  const response=await fetch(`/api/${path}`,{method,headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const result=await response.json() as T&{error?:string};
  if(!response.ok)throw new Error(result.error??'Shared review is temporarily unavailable.');
  return result;
}
export const listNotes=(runId:string,includeDeleted=false)=>api<{annotations:Annotation[]}>(`annotations?run=${encodeURIComponent(runId)}${includeDeleted?'&include_deleted=1':''}`);
export const percent=(n:number,total:number)=>total?`${(n/total*100).toFixed(1).replace(/\.0$/,'')}%`:'—';
export const results=(e:Experiment)=>e.pooled??{counts:e.counts,total:e.runs.length,attempts:e.attempts,interval95:e.interval95};
export const roundNames=['Individual hypotheses','Round 1 · Pairs','Round 2 · Triples','Round 3 · Four hypotheses','Round 4 · Five hypotheses'];
export function downloadJson(value:unknown,name:string){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
