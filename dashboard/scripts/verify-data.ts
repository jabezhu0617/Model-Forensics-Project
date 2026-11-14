import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { load } from 'cheerio';
import type { Dataset, Run } from '../src/types';
const root=resolve(import.meta.dir,'..');
const d=JSON.parse(await readFile(resolve(root,'public/data/index.json'),'utf8')) as Dataset;
const source=load(await readFile(resolve(root,'../studies/main/reports/viewer.html'),'utf8'));
const entries=JSON.parse(source('script#data').text()) as {experiment:string;pages:Record<string,string>}[];
let verified=0;
for(const e of entries){
  const records=JSON.parse(load(e.pages.transcripts??'')('script#records').text()) as Run[];
  for(const r of records){
    const exported=JSON.parse(await readFile(resolve(root,'public/data/runs',`${r.id}.json`),'utf8')) as Run;
    for(const field of ['text','transcript_hash','outcome','display_messages','submission'] as const){
      if(JSON.stringify(r[field])!==JSON.stringify(exported[field]))throw new Error(`Changed ${field}: ${r.id}`);
    }
    verified++;
  }
}
if(verified!==d.totalRuns||entries.length!==d.totalExperiments)throw new Error('Counts do not match');
const baseline=d.experiments.find(e=>e.id==='r1-baseline');
if(!baseline||baseline.counts.concealed!==20||baseline.runs.length!==60)throw new Error('Baseline changed');
if(d.hypotheses.length!==31||d.counts.concealed!==113||d.counts.reported!==567)throw new Error('Unexpected aggregate counts');
console.log(`Verified all ${verified} transcripts, source hashes, message content, submissions and outcomes against the original export.`);
