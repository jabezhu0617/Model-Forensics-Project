import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { load } from 'cheerio';
import type { Dataset, Experiment, PromptComparison, PromptDraft, PromptDraftSummary } from '../src/types';
import { promptDrafts } from './prompt-drafts';

const dashboard=resolve(import.meta.dir,'..');
const output=resolve(dashboard,'dist/data/prompt-drafts');
const indexPath=resolve(output,'../index.json');
const dataset=JSON.parse(await readFile(indexPath,'utf8')) as Dataset;
const keys=['system','user','questions.txt','format_guide.md','deployment_notes.txt','notes_to_self.txt'];
const cached=new Map<string,Map<string,string>>();
const drafts=new Map<string,PromptDraft>();
const defaultContact='J. Morrison, Evaluation Program Coordinator | j.morrison@ng-artemis.mil';
const contacts:Record<string,string>={
  'H1−A':'Dr. Maya Chen, Aerospace Engineering Course Lead | mchen@alderwick-aero.org',
  'H1−B':'Elena Ruiz, Civilian Mission Review Coordinator | elena.ruiz@civilian-mission-review.org',
  'H4−A':'Lin Wei, Evaluation Program Coordinator | lin.wei@avic-evaluation.cn',
  'H4−B':'Liu Jing, Evaluation Program Coordinator | liu.jing@casc-evaluation.cn',
};
const titleFor=(key:string)=>key==='system'?'System prompt':key==='user'?'User prompt':`/agent/${key}`;

async function publishedSections(id:string){
  const existing=cached.get(id);
  if(existing)return existing;
  const experiment=JSON.parse(await readFile(resolve(output,'../experiments',`${id}.json`),'utf8')) as Experiment;
  if(experiment.id!==id||!experiment.inputs)throw new Error(`Missing published inputs: ${id}`);
  const sections=new Map<string,string>();
  for(const key of keys){
    const inputs=experiment.inputs.filter(section=>section.title===titleFor(key));
    const nodes=load(inputs[0]?.html??'')('pre.input-content');
    if(inputs.length!==1||nodes.length!==1)throw new Error(`Invalid published input: ${id} (${key})`);
    sections.set(key,nodes.text());
  }
  cached.set(id,sections);
  return sections;
}

function testedComparison(sourceId:string, group:string, sign:string, original:Map<string,string>):PromptComparison{
  const source=dataset.experiments.find(e=>e.id===sourceId);
  if(!source||source.group!==group||source.sign!==sign||source.round!==0||!source.runs.length||
     !dataset.hypotheses.find(h=>h.id===group)?.arms.includes(sourceId)){
    throw new Error(`Unexpected tested arm: ${sourceId}`);
  }
  const originalTrials=source.runs.length;
  const followupTrials=source.pooled?source.pooled.total-originalTrials:0;
  return {title:source.title,originalTrials,followupTrials,earlierScreen:false,sections:Object.fromEntries(original)};
}

const draftId=(label:string)=>label.toLowerCase().replace('−','-minus-').replace('+','-plus-');
const variantArms=new Set(promptDrafts.filter(([label,,kind])=>kind==='variant'&&label.endsWith('B')).map(([label])=>label.slice(0,-1)));
const superseded=([label,,kind]:typeof promptDrafts[number])=>kind==='rewrite'&&label.endsWith('A')&&variantArms.has(label.slice(0,-1));
const active=promptDrafts.filter(draft=>!superseded(draft));
const expectedArms=new Set(dataset.hypotheses.filter(h=>h.round===0).flatMap(h=>[h.id+'−',h.id+'+']));

for(const [label,title,kind,sourceId,edits] of active){
  const id=draftId(label);
  const group=label.slice(0,2);
  if(!/^H[0-4][−+][BR]$/.test(label)||!label.endsWith(kind==='rewrite'?'R':'B')||!expectedArms.delete(label.slice(0,-1))){
    throw new Error(`Expected one active B or R draft per direction: ${label}`);
  }
  const originalSections=await publishedSections(sourceId);
  const sections=new Map(originalSections);
  const changed=new Set<string>();
  for(const [section,before,after] of edits){
    const text=sections.get(section);
    if(!text||!before||before===after||text.indexOf(before)<0||text.indexOf(before)!==text.lastIndexOf(before)){
      throw new Error(`${label}: edit must match exactly once in ${section}`);
    }
    sections.set(section,text.replace(before,()=>after));
    changed.add(section);
  }
  // Keep the same contact across drafts with the same setting, outside the edit list.
  const deployment='deployment_notes.txt';
  const rawNotes=sections.get(deployment)!;
  const contactLines=rawNotes.match(/^Contact:.*$/gm);
  if(contactLines?.length!==1)throw new Error(`${label}: expected one contact line`);
  const contact=contacts[label]??defaultContact;
  const safeNotes=rawNotes.replace(/^Contact:.*$/m,()=>`Contact: ${contact}`);
  sections.set(deployment,safeNotes);
  const tested=dataset.experiments.find(e=>e.variant===id);
  if(tested){
    const exported=await publishedSections(tested.id);
    for(const [key,text] of sections){
      if(exported.get(key)!==text.replace(/\r\n/g,'\n')){
        throw new Error(`Draft differs from tested inputs: ${label} (${key})`);
      }
    }
  }
  drafts.set(id,{id,label,title,kind,group,sourceId,
    previewContact:rawNotes!==safeNotes,
    sections:[...sections].map(([key,text])=>({key,text,changed:changed.has(key)})),
    ...(kind==='rewrite'?{comparison:testedComparison(sourceId,group,label[2]!,originalSections)}:{}),
  });
}

if(drafts.size!==10||expectedArms.size)throw new Error('Expected ten drafts, one per direction for H0–H4');
const index:PromptDraftSummary[]=[...drafts.values()].map(({sections,previewContact,comparison,...summary})=>summary);
await mkdir(output,{recursive:true});
// Remove old public detail files as well as their index entries on repeated builds.
for(const [label] of promptDrafts.filter(superseded)){
  if(!/^H[0-4][−+]A$/.test(label))throw new Error(`Unexpected superseded draft: ${label}`);
  try{await unlink(resolve(output,`${draftId(label)}.json`));}
  catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
}
for(const draft of drafts.values())await writeFile(resolve(output,`${draft.id}.json`),JSON.stringify(draft));
await writeFile(resolve(output,'index.json'),JSON.stringify(index));
console.log(`Prepared ${drafts.size} read-only prompt draft previews. No experiment records were changed.`);
