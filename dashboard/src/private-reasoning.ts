import type { ReasoningTrace } from './types';

const store='traces';
let connection:Promise<IDBDatabase>|undefined;
function database(){
  return connection??=new Promise<IDBDatabase>((resolve,reject)=>{
    const request=indexedDB.open('model-forensics-private-reasoning',1);
    request.onupgradeneeded=()=>request.result.createObjectStore(store);
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>{connection=undefined;reject(request.error);};
  });
}

export async function connectReasoningFolder(files:FileList, eligible:ReadonlySet<string>){
  const traces=new Map<string,File>();
  for(const file of files){
    if(!file.name.endsWith('.json'))continue;
    const id=file.name.slice(0,-5);
    if(!eligible.has(id))continue;
    if(traces.has(id)||file.size===0)throw new Error('The folder has duplicate or empty reasoning files.');
    traces.set(id,file);
  }
  if(!traces.size)throw new Error('No matching study reasoning files. Select the prepared reasoning folder.');
  const db=await database();
  await new Promise<void>((resolve,reject)=>{
    const transaction=db.transaction(store,'readwrite');
    transaction.oncomplete=()=>resolve();
    transaction.onabort=()=>reject(transaction.error);
    const records=transaction.objectStore(store);
    // Store the selected files in this browser. Parse only the requested run.
    for(const [id,file] of traces)records.put(file,id);
  });
  return new Set(traces.keys());
}

async function read<T>(request:(source:IDBObjectStore)=>IDBRequest<T>){
  const db=await database();
  return new Promise<T>((resolve,reject)=>{
    const result=request(db.transaction(store).objectStore(store));
    result.onsuccess=()=>resolve(result.result);
    result.onerror=()=>reject(result.error);
  });
}

export async function hasPrivateReasoning(id:string){return (await read(source=>source.getKey(id)))!==undefined;}
export async function privateReasoning(id:string){
  const file=await read<File|undefined>(source=>source.get(id));
  return file?JSON.parse(await file.text()) as ReasoningTrace:null;
}
