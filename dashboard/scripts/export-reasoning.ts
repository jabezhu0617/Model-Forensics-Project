import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { studyScope } from '../src/study-scope';
import type { Dataset, ReasoningTrace, Run } from '../src/types';

const dashboard=resolve(import.meta.dir,'..');
const dist=resolve(dashboard,'dist/data');
const sealed=resolve(dashboard,'../studies/main/sealed');
const readJson=async <T>(path:string):Promise<T>=>JSON.parse(await readFile(path,'utf8')) as T;
const dataset=await readJson<Dataset>(resolve(dist,'index.json'));
const runs=studyScope(dataset).focus.experiments.filter(e=>!e.variant).flatMap(e=>e.runs);
const out=resolve(dist,'reasoning');
const traces=new Map<string,ReasoningTrace>();

// Keep the reviewed transcript, its offsets, and its download byte-for-byte intact.
// Export only provider reasoning text, never entire responses or diagnostics.
for(const summary of runs){
  const id=summary.replaces?.id??summary.id;
  if(!/^[a-zA-Z0-9_-]+$/.test(id)||traces.has(id))throw new Error('Invalid or duplicate run ID');
  const run=await readJson<Run>(resolve(dist,'runs',`${id}.json`));
  if(run.id!==id||run.transcript_hash!==(summary.replaces?.transcript_hash??summary.transcript_hash)||run.status!=='complete')throw new Error(`Mismatched transcript: ${id}`);
  const assistant=run.display_messages.filter(m=>m.role==='assistant');
  const folder=resolve(sealed,id);
  const files=(await readdir(folder)).filter(f=>/^step-\d+\.json$/.test(f)).sort();
  if(!files.length||files.length!==assistant.length)throw new Error(`Mismatched response count: ${id}`);
  const blocks:ReasoningTrace['blocks']=[];
  for(const [step,file] of files.entries()){
    const message=assistant[step]!;
    if(file!==`step-${String(step).padStart(3,'0')}.json`||message.index!==2+2*step)throw new Error(`Mismatched response order: ${id}`);
    const response=await readJson<{choices?:{message?:{role:string;content?:unknown;reasoning?:unknown}}[]}>(resolve(folder,file));
    const source=response.choices?.[0]?.message;
    if(source?.role!=='assistant'||(source.content??'')!==(message.segments.find(s=>s.kind==='text')?.text??''))throw new Error(`Mismatched assistant response: ${id}, step ${step}`);
    if(typeof source.reasoning!=='string'||!source.reasoning.trim())throw new Error(`Missing reasoning: ${id}, step ${step}`);
    blocks.push({message:message.index,text:source.reasoning});
  }
  traces.set(id,{transcript_hash:run.transcript_hash,blocks});
}
await mkdir(out,{recursive:true});
for(const [id,trace] of traces)await writeFile(resolve(out,`${id}.json`),JSON.stringify(trace));
await writeFile(resolve(out,'index.json'),JSON.stringify([...traces.keys()]));
console.log(`Prepared ${[...traces.values()].reduce((n,t)=>n+t.blocks.length,0)} reasoning blocks for ${traces.size} baseline and H0–H4 runs.`);
