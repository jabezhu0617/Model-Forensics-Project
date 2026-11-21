import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Run, RunSummary } from '../src/types';

const files=['deployment_notes.txt','format_guide.md','notes_to_self.txt','questions.txt'];
interface Replacement {
  source:string;
  original:NonNullable<RunSummary['replaces']>;
  replacement:Run;
  file_reads:Record<string,number>;
}
type ReplacementExport={source_version:string;pairs:Replacement[];attempts:Record<string,number>;
  previous_concealed:number;replacement_concealed:number};

export async function loadRequiredReads(directory:string, sourceVersion:string){
  let contents:string;
  try{contents=await readFile(resolve(directory,'required-read-replacements.json'),'utf8');}
  catch(error){if((error as NodeJS.ErrnoException).code==='ENOENT')return null;throw error;}
  const data=JSON.parse(contents) as ReplacementExport;
  if(data.source_version!==sourceVersion||data.pairs.length!==170)throw new Error('Required reads refer to a different source export');
  const pairs=new Map<string,Replacement>();
  const ids=new Set<string>();
  const perSource=new Map<string,number>();
  for(const pair of data.pairs){
    const {original,replacement}=pair;
    const prefix=`required-read-${pair.source}-`;
    if(!/^[a-zA-Z0-9_-]+$/.test(replacement.id)||!replacement.id.startsWith(prefix)||ids.has(replacement.id)||pairs.has(original.id)||
       !Number.isInteger(original.index)||original.index<1||!['concealed','reported'].includes(original.outcome)||
       replacement.status!=='complete'||!['concealed','reported'].includes(replacement.outcome)||
       !/^[a-f0-9]{64}$/.test(replacement.transcript_hash)||!replacement.submission||
       JSON.stringify(Object.keys(pair.file_reads).sort())!==JSON.stringify(files)||
       files.some(file=>!replacement.display_messages.some(m=>m.index===pair.file_reads[file]&&m.role==='tool'&&m.exit_code===0))){
      throw new Error(`Invalid required-read evidence for ${original.id}`);
    }
    pairs.set(original.id,pair);
    ids.add(replacement.id);
    perSource.set(pair.source,(perSource.get(pair.source)??0)+1);
  }
  if(Object.keys(data.attempts).length!==perSource.size||[...perSource].some(([id,n])=>!Number.isInteger(data.attempts[id])||data.attempts[id]!<n)||
     data.previous_concealed!==data.pairs.filter(p=>p.original.outcome==='concealed').length||
     data.replacement_concealed!==data.pairs.filter(p=>p.replacement.outcome==='concealed').length){
    throw new Error('Required-read totals do not match the evidence');
  }
  return {pairs,attempts:data.attempts,contents,summary:{total:pairs.size,originalConcealed:data.previous_concealed,replacementConcealed:data.replacement_concealed}};
}
