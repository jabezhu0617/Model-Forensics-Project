import { chromium } from 'playwright-core';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Dataset, ReasoningTrace, Run, TemporarySummary } from '../src/types';
const base=process.argv[2]??'http://127.0.0.1:8788';
const out=resolve(import.meta.dir,'../screenshots');await mkdir(out,{recursive:true});
const manifest=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/manifest.json'),'utf8')) as {worstRun:{id:string;bytes:number}};
const d=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/index.json'),'utf8')) as Dataset;
const browser=process.env.CHROME_CDP_URL
  ?await chromium.connectOverCDP(process.env.CHROME_CDP_URL)
  :await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE??'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const annotationRequests:string[]=[];page.on('request',request=>{if(request.url().includes('/api/annotations'))annotationRequests.push(request.url());});
const errors:string[]=[];const capture=(p:typeof page)=>{p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});p.on('pageerror',e=>errors.push(e.message));};capture(page);
async function visit(path:string,name:string){const start=Date.now();await page.goto(base+path,{waitUntil:'networkidle'});await page.locator('.page-heading h1').waitFor();await page.screenshot({path:resolve(out,`${name}.png`)});console.log(`${name}: ${Date.now()-start}ms`);}
function assert(condition:unknown,message:string):asserts condition{if(!condition)throw new Error(message);}
async function assertReadOnlyTranscript(){
  assert(await page.locator('.annotation-panel,.selection-note').count()===0,'Note panel still displayed');
  assert(await page.getByRole('button',{name:/Add note|Share note|Annotate selected/}).count()===0,'Note control still displayed');
  const widths=await page.evaluate(()=>({column:document.querySelector('.transcript-column')!.getBoundingClientRect().width,layout:document.querySelector('.transcript-layout')!.getBoundingClientRect().width}));
  assert(Math.abs(widths.column-widths.layout)<1,'Transcript does not use the full available width');
}
async function verifyPublishedReasoning(){
  const liveIds=(await (await context.request.get(`${base}/data/reasoning/index.json`)).json()) as string[];
  assert(liveIds.length===360&&new Set(liveIds).size===360,'Expected 360 published reasoning traces');
  const publicPage=await context.newPage();
  const requests:string[]=[];
  publicPage.on('request',request=>{if(/\/data\/reasoning\/(?!index\.json)[^/]+\.json$/.test(request.url()))requests.push(request.url());});
  const requestCount=()=>requests.length;
  try{
    await publicPage.goto(`${base}/#/run/r1-baseline-0001`,{waitUntil:'networkidle'});
    const control=publicPage.getByRole('checkbox',{name:'Reasoning',exact:true});
    const blocks=publicPage.locator('.message-segment.kind-reasoning');
    assert(!(await control.isChecked())&&await blocks.count()===0&&requestCount()===0,'Public reasoning loaded before the toggle');
    assert(await publicPage.getByRole('button',{name:'Connect reasoning folder'}).count()===0,'Public reasoning still requires a folder');
    await control.check();
    await blocks.first().waitFor();
    assert(await blocks.count()>0&&requestCount()===1,'Reasoning did not load from the published supplement');
    await control.uncheck();
    assert(await blocks.count()===0,'Public reasoning did not hide');
    await publicPage.getByRole('link',{name:/^Next/}).click();
    await publicPage.waitForURL('**/r1-baseline-0002');
    await control.waitFor();
    assert(!(await control.isChecked())&&requestCount()===1,'Next run loaded reasoning without opt-in');
    console.log('PASS: 360 public reasoning traces indexed; no folder required; toggle starts off on each run.');
  }finally{await publicPage.close();}
}
async function verifyPromptDrafts(){
  const index=await (await context.request.get(base+'/data/prompt-drafts/index.json')).json() as {id:string}[];
  const artemis='Contact: J. Morrison, Evaluation Program Coordinator | j.morrison@ng-artemis.mil';
  const draftContacts:Record<string,string>={
    'h1-minus-b':'elena.ruiz@civilian-mission-review.org',
    'h4-minus-b':'liu.jing@casc-evaluation.cn',
  };
  const contacts=await Promise.all(index.map(async ({id})=>{
    const draft=await (await context.request.get(base+'/data/prompt-drafts/'+id+'.json')).json() as import('../src/types').PromptDraft;
    const notes=draft.sections.find(section=>section.key==='deployment_notes.txt')?.text??'';
    const contact=notes.match(/^Contact:.*$/gm);
    const expected=draftContacts[id];
    assert(contact?.length===1&&(expected?contact[0]?.endsWith(' | '+expected):contact[0]===artemis),`Invalid preview contact: ${id}`);
    assert(draft.previewContact,`Missing preview contact disclosure: ${id}`);
    const comparison=draft.comparison;
    if(draft.kind==='rewrite'){
      assert(comparison&&comparison.originalTrials===10&&comparison.followupTrials===20,`Wrong tested trial counts: ${id}`);
      assert(!comparison.earlierScreen,`Wrong tested arm type: ${id}`);
      assert(draft.sections.length===6&&draft.sections.every(section=>typeof comparison.sections[section.key]==='string'),`Missing tested inputs: ${id}`);
    }else assert(!comparison,`New variant should not be compared to a tested arm: ${id}`);
    return [id,contact[0]] as const;
  }));
  const byId=new Map(contacts);
  const expectedIds=['h0-minus-r','h0-plus-r','h1-minus-b','h1-plus-b','h2-minus-b','h2-plus-r','h3-minus-b','h3-plus-r','h4-minus-b','h4-plus-r'];
  assert(byId.size===10&&expectedIds.every(id=>byId.has(id))&&new Set(byId.values()).size===3,'Expected one B or R draft per direction');
  assert([...byId.values()].filter(contact=>contact===artemis).length===8&&byId.get('h2-minus-b')===artemis,'Expected original email on the Artemis drafts');
  const supersededIds=['h1-minus-a','h1-plus-a','h2-minus-a','h3-minus-a','h4-minus-a'];
  for(const id of supersededIds){
    const response=await context.request.get(base+'/data/prompt-drafts/'+id+'.json?verify='+Date.now());
    assert(response.status()===404||(response.ok()&&(response.headers()['content-type']??'').startsWith('text/html')),`Superseded draft is still published: ${id}`);
  }
  await page.goto(base+'/#/prompt-drafts');
  const groups=page.locator('.draft-group');
  const links=groups.getByRole('link');
  await links.first().waitFor();
  assert(await groups.count()===5&&await links.count()===10,'Expected ten drafts under H0–H4');
  const filter=page.getByLabel('Show',{exact:true});
  await filter.selectOption('rewrite');
  assert(await links.count()===5,'Expected five wording rewrites');
  await filter.selectOption('variant');
  assert(await links.count()===5,'Expected 5 new variants');
  await page.getByRole('link',{name:/Assignment after a passing score/}).click();
  await page.getByRole('heading',{name:/Assignment after a passing score/}).waitFor();
  const details=page.locator('.prompt-draft details');
  assert(await details.count()===6,'Missing a prompt or attachment');
  const deployment=details.filter({has:page.locator('summary').getByText('deployment_notes.txt',{exact:false})});
  assert(await deployment.getAttribute('open')!==null,'The edited attachment should be open');
  assert((await deployment.locator('pre').textContent())?.includes('qualification report from synthetic records'),'Unexpected downstream assignment');
  assert((await deployment.locator('pre').textContent())?.includes(artemis),'The Artemis contact should be visible in the draft');
  const system=details.filter({has:page.locator('summary').getByText('System prompt',{exact:true})});
  await system.locator('summary').click();
  assert(await system.locator('pre').isVisible(),'Unchanged system prompt cannot be opened');
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Draft input overflows on mobile');
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(base+'/#/prompt-drafts/h1-minus-a');
  await page.getByRole('alert').filter({hasText:'This draft was not found.'}).waitFor();
  await page.goto(base+'/#/prompt-drafts/h2-plus-r');
  await page.getByRole('heading',{name:'Tested prompt',exact:true}).waitFor();
  const scratch=page.locator('.draft-comparison details').filter({has:page.locator('summary').getByText('notes_to_self.txt',{exact:false})});
  const tested=scratch.locator('.tested-input pre'), proposed=scratch.locator('.proposed-input pre');
  assert((await tested.textContent())?.includes('bear the cost of the delay'),'Expected the original tested rationale');
  assert((await proposed.textContent())?.includes('AI models should not be used to harm people.'),'Expected the new rationale on the proposed side');
  const marked=await proposed.locator('mark').allTextContents();
  assert(marked.some(text=>text.includes('AI models'))&&await tested.locator('mark').count()===0,'Highlight the revised wording only in the proposed column');
  const draft=await (await context.request.get(base+'/data/prompt-drafts/h2-plus-r.json')).json() as import('../src/types').PromptDraft;
  assert(await proposed.textContent()===draft.sections.find(section=>section.key==='notes_to_self.txt')?.text,'Highlighting changed the proposed text');
  const unchanged=page.locator('.draft-comparison details').filter({has:page.locator('summary').getByText('System prompt',{exact:false})});
  assert(await unchanged.locator('.proposed-input mark').count()===0,'Identical inputs should not be highlighted');
  const left=await tested.boundingBox(),right=await proposed.boundingBox();
  assert(left&&right&&left.x<right.x&&left.y===right.y,'Tested and proposed prompts are not side by side');
  await page.setViewportSize({width:390,height:844});
  const mobileLeft=await tested.boundingBox(),mobileRight=await proposed.boundingBox();
  assert(mobileLeft&&mobileRight&&mobileRight.y>mobileLeft.y&&await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Compared inputs should stack without mobile overflow');
  await page.setViewportSize({width:1440,height:1000});
  console.log('PASS: Ten B or R drafts, five superseded A drafts removed, and input comparisons still work.');
}
async function verifyVariantResults(){
  const variants=d.experiments.filter(e=>e.variant);
  if(!variants.length)return;
  assert([5,10].includes(variants.length),'Expected five B variant results, with or without the five rewrites');
  for(const group of ['H0','H1','H2','H3','H4']){
    const original=d.hypotheses.find(h=>h.id===group);
    const added=variants.filter(e=>e.group===group);
    assert(original?.arms.length===2+added.length,'Expected one result per distinct prompt');
    await page.goto(base+'/#/hypothesis/'+group);
    const cards=page.locator('.arm-card');
    await cards.first().waitFor();
    assert(await cards.count()===2+added.length,'Wrong number of cards for '+group);
    for(const arm of added){
      const card=cards.filter({has:page.getByRole('heading',{name:arm.label+' · '+arm.title,exact:true})});
      assert((await card.textContent())?.includes(arm.counts.concealed+' / 30 concealed'),'Wrong variant count for '+arm.label);
      assert(!((await card.textContent())?.includes('Original screen:')),'Prompt edit reused the historical score');
    }
  }
  for(const variant of variants){
    await page.goto(base+'/#/prompt-drafts/'+variant.variant);
    await page.getByRole('link',{name:/View results and transcripts/}).click();
    const rows=page.locator('.run-table tbody tr');
    await rows.first().waitFor();
    const heading=page.locator('.page-heading h1');
    assert(await heading.textContent()===variant.label+' · '+variant.title,'Draft link opened the wrong trial batch');
    assert(await rows.count()===30,'Expected thirty transcripts for '+variant.label);
  }
  console.log(`PASS: ${variants.length} separate prompt-edit results and transcript batches across H0–H4.`);
}
async function verifyRequiredReads(){
  if(!d.requiredReads)return;
  const replacements=d.experiments.flatMap(e=>e.runs).filter(r=>r.replaces);
  assert(replacements.length===170,'Expected exactly 170 replaced slots in the viewer');
  await page.goto(base+'/#/');
  await page.getByText('170 unread trials rerun.',{exact:true}).waitFor();
  await page.getByRole('link',{name:/See the rerun protocol and trial mapping/}).click();
  await page.getByRole('heading',{name:'Required-read replacements',exact:true}).waitFor();
  const sample=replacements[0]!;
  await page.goto(base+'/#/run/'+sample.id);
  await page.getByText('Required-read replacement.',{exact:true}).waitFor();
  const proof=page.getByRole('link',{name:'deployment_notes.txt',exact:true});
  await proof.click();
  await page.waitForURL(/\?message=\d+$/);
  const message=new URLSearchParams(new URL(page.url()).hash.split('?')[1]).get('message');
  await page.locator('#message-'+message).waitFor();
  await page.getByRole('link',{name:/View the original transcript/}).click();
  await page.waitForURL('**/run/'+sample.replaces!.id);
  const replacement=page.getByRole('link',{name:/required-read replacement/});
  await replacement.click();
  await page.waitForURL('**/run/'+sample.id);
  console.log('PASS: 170 counted replacements, with file-read evidence and working links to the original transcripts.');
}
try{
  if(process.argv.includes('--public-reasoning'))await verifyPublishedReasoning();
  if(process.argv.includes('--prompt-drafts'))await verifyPromptDrafts();
  await verifyVariantResults();
  await verifyRequiredReads();
  await visit('/#/','overview');assert(await page.locator('.comparisons tbody tr').count()===5,'Expected only H0-H4 on the main overview');
  const plot=page.locator('.matplotlib-chart');
  await plot.waitFor();
  await plot.evaluate((img:HTMLImageElement)=>img.decode());
  const plotSrc=await plot.getAttribute('src');assert(plotSrc,'Missing Matplotlib image');
  const svg=await (await context.request.get(new URL(plotSrc,base).href)).text();
  assert(svg.includes('Matplotlib 3.9.4'),'Graph was not generated by Matplotlib');
  const variantCount=d.experiments.filter(e=>e.variant).length;
  assert((svg.match(/id="bar-[^"]+"/g)??[]).length===11+variantCount,'Incorrect number of Matplotlib bars');
  assert((svg.match(/id="errorbar-[^"]+"/g)??[]).length===11+variantCount&&svg.includes('id="errorbar-Baseline-baseline"'),'Expected an interval per bar');
  assert(svg.includes('95% Wilson confidence intervals'),'Missing error bar explanation');
  assert((await plot.getAttribute('alt'))?.includes('22.7–45.9%'),'Missing accessible confidence interval');
  assert(svg.includes('Concealment rate')&&(await plot.getAttribute('alt'))?.includes('33.3%')&&
    (variantCount?svg.includes('20/60'):svg.includes('33.3%')),'Missing graph axes or baseline');
  assert(svg.includes('id="baseline-reference"'),'Missing dotted baseline reference');
  await visit('/#/combinations','combination-archive');assert(await page.locator('.comparisons tbody tr').count()===26,'Expected all 26 archived combinations');
  await page.getByRole('button',{name:'Round 4',exact:true}).click();assert(await page.locator('.comparisons tbody tr').count()===1,'Archive round filtering failed');
  await visit('/#/hypothesis/r1-combined-round4-pair1','hypothesis');await page.locator('.arm-card').first().waitFor();assert(await page.locator('.arm-card').count()===2,'Missing paired arms');
  await page.getByRole('link',{name:'Prompt comparison',exact:true}).click();assert(await page.locator('.input-column').count()===2,'Missing paired prompt inputs');await page.screenshot({path:resolve(out,'inputs.png')});
  await visit('/#/experiment/r1-baseline','baseline');assert(await page.locator('.run-table tbody tr').count()===60,'Missing baseline runs');
  await visit('/#/methods','methods');
  const examples=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/temporary/index.json'),'utf8')) as TemporarySummary[];
  await visit('/#/examples','temporary-index');
  if(examples.length)await page.locator('.temporary-card').first().waitFor();
  assert(await page.locator('.temporary-card').count()===examples.length,'Temporary transcript index count changed');
  for(const example of examples){
    const raw=await readFile(resolve(import.meta.dir,`../public/data/runs/${example.id}.json`),'utf8');
    const imported=JSON.parse(raw) as Run;
    await visit(`/#/examples/${example.id}`,example.id);
    const reasoning=page.getByRole('checkbox',{name:'Reasoning',exact:true});
    assert(!(await reasoning.isChecked())&&await page.locator('.message-card.kind-reasoning').count()===0,'Example reasoning should start hidden');
    await reasoning.check();
    assert(await page.locator('.message-card').count()===imported.messageCount,'Missing archive blocks');
    assert(await page.locator('.message-card.kind-reasoning').count()===example.reasoningBlocks,'Missing reasoning traces');
    assert(await page.locator('.message-card.kind-tool-call').count()===example.toolCalls,'Missing tool calls');
    await assertReadOnlyTranscript();
    const colors=await page.locator('.transcript-legend .kind-key').evaluateAll(nodes=>nodes.map(node=>getComputedStyle(node).color));
    assert(new Set(colors).size===colors.length,'Message types need distinct colors');
    const firstCall=page.locator('.message-card.kind-tool-call').first();
    assert(await firstCall.locator('.message-text').count()===0,'Tool calls should start collapsed');
    await firstCall.getByRole('button',{name:/Show full text/}).click();
    assert(await firstCall.locator('.message-text').count()===1,'Tool call expansion failed');
    const log=await context.request.get(base+example.downloadUrl);
    assert((await log.text())===imported.text,'Full log download differs from imported source');
    const largest=imported.display_messages.reduce((a,b)=>a.segments[0]!.text.length>b.segments[0]!.text.length?a:b);
    const phrase=largest.segments[0]!.text.split('\n').filter(line=>line.length>35).at(-1)!.slice(0,45);
    await page.getByRole('searchbox',{name:'Find in transcript'}).fill(phrase);
    assert(await page.locator(`#message-${largest.index} .message-text`).count()===1,'Search did not expand the matching long result');
    await page.getByRole('searchbox',{name:'Find in transcript'}).fill('');
    await page.setViewportSize({width:390,height:844});await visit(`/#/examples/${example.id}`,`${example.id}-mobile`);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Temporary mobile page overflows');
    await page.setViewportSize({width:1440,height:1000});
  }
  await visit(`/#/run/${manifest.worstRun.id}`,'largest-transcript');
  const expand=page.getByRole('button',{name:/Show full text/});if(await expand.count())await expand.first().click();
  await page.getByRole('searchbox',{name:'Find in transcript'}).fill('questions');assert((await page.locator('.message-card.matched').count())>0,'Transcript search failed');
  await page.screenshot({path:resolve(out,'transcript-search.png')});
  await visit('/#/run/r1-baseline-0001','review');await assertReadOnlyTranscript();
  assert(await page.locator('.transcript-toolbar + .submission-panel').count()===1,'Section controls should precede the submission and transcript');
  {
    const id='r1-baseline-0001';
    const raw=JSON.parse(await readFile(resolve(out,`../public/data/runs/${id}.json`),'utf8')) as Run;
    const phrase='Synthetic reasoning marker used to verify transcript search';
    const trace:ReasoningTrace={transcript_hash:raw.transcript_hash,blocks:[{message:2,text:phrase}]};
    const folder=resolve(out,'synthetic-reasoning');
    await mkdir(folder,{recursive:true});
    await writeFile(resolve(folder,`${id}.json`),JSON.stringify(trace));
    await writeFile(resolve(folder,'r1-baseline-0002.json'),JSON.stringify(trace));
    await page.route('**/data/reasoning/index.json',route=>route.fulfill({json:[]}));
    const requested:string[]=[];
    page.on('request',request=>{if(/\/data\/reasoning\/(?!index\.json)[^/]+\.json$/.test(request.url()))requested.push(request.url());});
    const requestCount=()=>requested.length;
    await page.reload({waitUntil:'networkidle'});
    const control=page.getByRole('checkbox',{name:'Reasoning',exact:true});
    await control.waitFor();
    const segments=page.locator('.message-segment.kind-reasoning');
    const search=page.getByRole('searchbox',{name:'Find in transcript'});
    assert(!(await control.isChecked())&&await segments.count()===0&&requestCount()===0,'Study reasoning rendered or loaded before opting in');
    const chooser=page.waitForEvent('filechooser');
    await control.click();
    await (await chooser).setFiles(folder);
    await page.getByText('Connected 2 runs. Check Reasoning to show it.').waitFor();
    await page.reload({waitUntil:'networkidle'});
    await page.getByRole('button',{name:'Connect reasoning folder'}).waitFor({state:'hidden'});
    await search.fill(phrase);
    assert(await page.locator('.match-count').textContent()==='0 matches','Hidden reasoning leaked into search');
    await control.check();await segments.first().waitFor();
    assert(await segments.count()===trace.blocks.length&&requestCount()===0,'Expected locally stored reasoning with no reasoning request');
    assert((await page.locator('.message-card.matched').count())>0,'Visible reasoning is not searchable');
    await control.uncheck();
    assert(await segments.count()===0&&await page.locator('.match-count').textContent()==='0 matches','Turning reasoning off did not hide it');
    await search.fill('');
    for(const [label,selector] of [['System prompt','.message-segment.kind-system'],['User prompt','.message-segment.kind-user'],['Assistant output','.message-segment.kind-assistant'],['Tool call','.message-segment.kind-tool-call'],['Tool result','.message-segment.kind-tool'],['Final submission','.submission-panel,.message-segment.kind-submission']]){
      const checkbox=page.getByRole('checkbox',{name:label!,exact:true});
      const content=page.locator(selector!);
      assert(await content.count()>0,`Missing ${label} before filtering`);
      await checkbox.uncheck();assert(await content.count()===0,`${label} was not hidden`);
      await checkbox.check();assert(await content.count()>0,`${label} was not restored`);
    }
    await control.check();await segments.first().waitFor();
    await page.getByRole('link',{name:/^Next/}).click();
    await page.waitForURL('**/r1-baseline-0002');await control.waitFor();
    assert(!(await control.isChecked())&&await segments.count()===0,'Study reasoning stayed on for the next run');
  }
  await page.setViewportSize({width:390,height:844});await visit('/#/','mobile-overview');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Chart causes mobile page overflow');
  const scrollArea=page.locator('.chart-scroll');await scrollArea.evaluate(el=>el.scrollLeft=el.scrollWidth);await page.screenshot({path:resolve(out,'mobile-chart-scrolled.png')});
  await visit('/#/run/r1-baseline-0001','mobile-review');await assertReadOnlyTranscript();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Mobile page overflows horizontally');
  assert(!annotationRequests.length,'Viewer still requests shared annotations');
  assert(!errors.length,`Browser errors: ${errors.join('\n')}`);
  console.log(`PASS: ${d.totalRuns} study runs, ${examples.length} temporary transcripts; page types, search, full-width read-only transcripts, no annotation requests, and mobile. Largest transcript: ${manifest.worstRun.bytes} bytes.`);
}finally{await browser.close();}
