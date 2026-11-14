import type { Annotation, Run } from '../src/types';
export interface Env { DB: D1Database; ASSETS: Fetcher }
const json=(value:unknown,status=200)=>Response.json(value,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
class InputError extends Error { constructor(message:string, readonly status=400){super(message);} }
const text=(value:unknown,max:number,name:string,required=false)=>{
  if(typeof value!=='string'||value.length>max||(required&&!value.trim())) throw new InputError(`${name} must be ${required?'non-empty ':''}text, up to ${max} characters.`);
  return value.trim();
};
async function readBody(request:Request):Promise<Record<string,unknown>> {
  const raw=await request.text();
  if(new TextEncoder().encode(raw).length>32768) throw new InputError('Annotation is too large.',413);
  try { const parsed:unknown=JSON.parse(raw);if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw new Error();return parsed as Record<string,unknown>; }
  catch {throw new InputError('Expected a JSON object.');}
}
async function validate(env:Env,request:Request,body:Record<string,unknown>) {
  const run_id=text(body.run_id,180,'Run ID',true);
  const transcript_hash=text(body.transcript_hash,64,'Transcript hash',true);
  if(!/^[a-zA-Z0-9_-]+$/.test(run_id)||!/^[a-f0-9]{64}$/.test(transcript_hash))throw new InputError('Invalid transcript reference.');
  // Always validate against the public transcript shipped with this deployment.
  const source=await env.ASSETS.fetch(new Request(new URL(`/data/runs/${run_id}.json`,request.url)));
  if(!source.ok)throw new InputError('Transcript was not found.',404);
  let run:Run;
  try {run=await source.json() as Run;}catch{throw new InputError('Transcript was not found.',404);}
  if(run.id!==run_id||run.transcript_hash!==transcript_hash)throw new InputError('Transcript version has changed. Reload before saving.',409);
  // Do not trim quotes: their exact bytes are evidence, including whitespace.
  if(typeof body.quote!=='string'||body.quote.length>16000)throw new InputError('Quote must be text, up to 16000 characters.');
  const quote=body.quote;
  if(quote&&!run.text.includes(quote))throw new InputError('Selected quote does not occur in this transcript.');
  const note=text(body.note,8000,'Note',true);
  const reviewer=text(body.reviewer??'Anonymous',80,'Display name')||'Anonymous';
  const outcome=body.outcome??null;
  if(outcome!==null&&!['concealed','reported','unresolved'].includes(String(outcome)))throw new InputError('Unknown suggested outcome.');
  return {run_id,transcript_hash,quote,note,reviewer,outcome:outcome as Annotation['outcome']};
}
export async function handle(request:Request,env:Env):Promise<Response> {
  try {
    const url=new URL(request.url);
    const path=url.pathname.replace(/^\/api\/?/,'').split('/').filter(Boolean);
    if(path[0]==='health'&&request.method==='GET'){
      if(!env.DB)return json({ready:false,error:'Annotation database is not configured.'},503);
      await env.DB.prepare('SELECT 1 FROM annotations LIMIT 1').first();
      return json({ready:true});
    }
    if(!env.DB)return json({error:'Shared annotations are not configured.'},503);
    if(path[0]!=='annotations')return json({error:'Not found.'},404);
    if(request.method!=='GET'){
      const origin=request.headers.get('Origin');
      if(origin&&origin!==url.origin)throw new InputError('Cross-origin writes are not accepted.',403);
      if(!request.headers.get('Content-Type')?.startsWith('application/json'))throw new InputError('Use application/json.',415);
    }
    if(path.length===1&&request.method==='GET'){
      const run=url.searchParams.get('run')??'';
      if(!/^[a-zA-Z0-9_-]{1,180}$/.test(run))throw new InputError('A valid run ID is required.');
      const results=await env.DB.prepare('SELECT * FROM annotations WHERE run_id=? AND (?=1 OR deleted=0) ORDER BY created_at LIMIT 1000').bind(run,url.searchParams.get('include_deleted')==='1'?1:0).all<Annotation>();
      return json({annotations:results.results});
    }
    if(path.length===1&&request.method==='POST'){
      const fields=await validate(env,request,await readBody(request));
      const id=crypto.randomUUID(),now=new Date().toISOString();
      const row=await env.DB.prepare('INSERT INTO annotations (id,run_id,transcript_hash,quote,note,reviewer,outcome,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?) RETURNING *')
        .bind(id,fields.run_id,fields.transcript_hash,fields.quote,fields.note,fields.reviewer,fields.outcome,now,now).first<Annotation>();
      return json({annotation:row},201);
    }
    const id=path[1];
    if(!id||!/^[-a-f0-9]{36}$/.test(id))throw new InputError('Invalid annotation ID.');
    const current=await env.DB.prepare('SELECT * FROM annotations WHERE id=?').bind(id).first<Annotation>();
    if(!current)return json({error:'Annotation not found.'},404);
    if(path[2]==='history'&&request.method==='GET'){
      const rows=await env.DB.prepare('SELECT snapshot FROM annotation_history WHERE id=? ORDER BY revision DESC').bind(id).all<{snapshot:string}>();
      return json({history:[current,...rows.results.map(row=>JSON.parse(row.snapshot) as Annotation)]});
    }
    if(path.length!==2||!['PATCH','DELETE'].includes(request.method))return json({error:'Method not allowed.'},405);
    const body=await readBody(request);
    if(body.revision!==current.revision)throw new InputError('This note changed in another session. Reload it before saving.',409);
    const fields=request.method==='DELETE'?current:await validate(env,request,{...body,run_id:current.run_id,transcript_hash:current.transcript_hash});
    const now=new Date().toISOString();
    // Batch is atomic. The revision guard prevents concurrent writers overwriting each other.
    const result=await env.DB.batch([
      env.DB.prepare('INSERT OR IGNORE INTO annotation_history (id,revision,snapshot) SELECT id,revision,? FROM annotations WHERE id=? AND revision=?').bind(JSON.stringify(current),id,current.revision),
      env.DB.prepare('UPDATE annotations SET quote=?,note=?,reviewer=?,outcome=?,updated_at=?,revision=revision+1,deleted=? WHERE id=? AND revision=? RETURNING *')
        .bind(fields.quote,fields.note,fields.reviewer,fields.outcome,now,request.method==='DELETE'?1:0,id,current.revision),
    ]);
    const updated=result[1]?.results[0] as Annotation|undefined;
    if(!updated)throw new InputError('This note changed in another session. Reload it before saving.',409);
    return json({annotation:updated});
  } catch(error) {
    if(error instanceof InputError)return json({error:error.message},error.status);
    console.error('Annotation request failed',error instanceof Error?error.message:'Unknown error');
    return json({error:'Shared review could not be reached. Please try again.'},500);
  }
}
