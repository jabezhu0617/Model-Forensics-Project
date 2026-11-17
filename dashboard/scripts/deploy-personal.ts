/** Publish the read-only viewer in its own account, from an isolated static bundle. */
import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { relative, resolve } from 'node:path';
import type { Dataset } from '../src/types';
import { studyScope } from '../src/study-scope';

const dashboard=resolve(import.meta.dir,'..');
const config=JSON.parse(await readFile(resolve(dashboard,'personal-hosting.json'),'utf8')) as {
  project:string; accountId:string; branch:string;
};
if(!/^[a-z0-9][a-z0-9-]{0,57}[a-z0-9]$/.test(config.project)||!/^[a-f0-9]{32}$/.test(config.accountId)||!config.branch) {
  throw new Error('Invalid personal Cloudflare hosting configuration');
}
const source=resolve(dashboard,'dist');
const data=JSON.parse(await readFile(resolve(source,'data/index.json'),'utf8')) as Dataset;
const plot=JSON.parse(await readFile(resolve(dashboard,'src/assets/plots/concealment-data.json'),'utf8')) as {
  dataset_version:string; svg_sha256:string; bars:{total:number;interval95:unknown}[];
};
if(data.version!==plot.dataset_version||data.totalRuns!==880||plot.bars.length!==11||
   plot.bars.some((bar,i)=>!bar.interval95||bar.total!==(i===0?60:30))) {
  throw new Error('Expected the verified thirty-trial follow-up dataset and eleven confidence intervals');
}
const release=new Date().toISOString().replace(/[:.]/g,'-');
const stage=resolve(dashboard,'../build/cloudflare-personal',config.project,release);
await mkdir(stage,{recursive:true});
// The UI has no annotation controls or API polling. Stage assets alone so the
// original project's Functions and D1 binding are not attached to this copy.
await cp(source,resolve(stage,'dist'),{recursive:true,filter:path=>
  !['_routes.json','_worker.js'].includes(relative(source,path))});
await writeFile(resolve(stage,'wrangler.jsonc'),JSON.stringify({
  name:config.project,pages_build_output_dir:'./dist',
  compatibility_date:'2026-11-17',
},null,2)+'\n');
const staged=await readFile(resolve(stage,'dist/data/index.json'));
if(createHash('sha256').update(staged).digest('hex')!==
   createHash('sha256').update(await readFile(resolve(source,'data/index.json'))).digest('hex')) {
  throw new Error('Staged data differs from the verified build');
}
const scopes=studyScope(data);
console.log(`Publishing ${scopes.focus.totalRuns} focused trials and ${scopes.archive.totalRuns} archived trials to https://${config.project}.pages.dev`);
const result=Bun.spawnSync([process.execPath,resolve(dashboard,'node_modules/wrangler/bin/wrangler.js'),
  'pages','deploy','dist','--project-name',config.project,'--branch',config.branch,'--commit-dirty=true'],{
  cwd:stage,env:{...process.env,CLOUDFLARE_ACCOUNT_ID:config.accountId},
  stdin:'inherit',stdout:'inherit',stderr:'inherit',
});
if(result.exitCode!==0)process.exit(result.exitCode||1);
await writeFile(resolve(dashboard,'../build/personal-deployment.json'),JSON.stringify({
  ...config,url:`https://${config.project}.pages.dev`,datasetVersion:data.version,
  trials:data.totalRuns,focusTrials:scopes.focus.totalRuns,archivedTrials:scopes.archive.totalRuns,
  chartSvgSha256:plot.svg_sha256,stage,published:new Date().toISOString(),
},null,2)+'\n');
