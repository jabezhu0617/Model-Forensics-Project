interface TextPart {
  text:string;
  added:boolean;
}

const tokens=(text:string)=>text.match(/\s+|[\p{L}\p{N}\p{M}_]+(?:['’][\p{L}\p{N}\p{M}_]+)*|[^\s]/gu)??[];
const weight=(token:string)=>/[\p{L}\p{N}]/u.test(token)?token.length+2:1;

// Align the tested and proposed text while preserving the proposed bytes.
export function proposedDiff(tested:string,proposed:string):TextPart[]{
  if(tested===proposed)return [{text:proposed,added:false}];
  const a=tokens(tested),b=tokens(proposed),parts:TextPart[]=[];
  const append=(text:string,added:boolean)=>{
    if(!text)return;
    const last=parts.at(-1);
    if(last?.added===added)last.text+=text;
    else parts.push({text,added});
  };
  let start=0,endA=a.length,endB=b.length;
  while(start<endA&&start<endB&&a[start]===b[start])start++;
  while(endA>start&&endB>start&&a[endA-1]===b[endB-1]){endA--;endB--;}
  append(b.slice(0,start).join(''),false);
  const height=endA-start+1,width=endB-start+1;
  if(height*width>1_000_000){
    append(b.slice(start,endB).join(''),true);
  }else{
    const scores=new Uint32Array(height*width);
    const at=(i:number,j:number)=>scores[i*width+j]!;
    for(let i=height-2;i>=0;i--){
      for(let j=width-2;j>=0;j--){
        const token=b[start+j]!;
        scores[i*width+j]=Math.max(at(i+1,j),at(i,j+1),a[start+i]===token?weight(token)+at(i+1,j+1):0);
      }
    }
    let i=0,j=0;
    while(j<width-1){
      const token=b[start+j]!;
      if(i<height-1&&a[start+i]===token&&at(i,j)===weight(token)+at(i+1,j+1)){
        append(token,false);i++;j++;
      }else if(i<height-1&&at(i+1,j)>at(i,j+1)){
        i++;
      }else{
        append(token,true);j++;
      }
    }
  }
  append(b.slice(endB).join(''),false);
  for(const part of parts)if(!part.text.trim())part.added=false;
  return parts;
}
