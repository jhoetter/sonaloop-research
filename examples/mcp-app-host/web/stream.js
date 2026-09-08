import {STREAM_SCHEMA_VERSION} from '../stream-contract.mjs';
// Read only the public host event protocol. A disconnected stream is never POST-retried.
export async function readTurnStream(response,onEvent){
  if(!response.ok||!response.headers.get('content-type')?.includes('text/event-stream')){
    let data;try{data=await response.json();}catch{}
    throw Object.assign(new Error(data?.error?.message||'Der Agent ist gerade nicht erreichbar.'),{code:data?.error?.code,notAccepted:response.status>=400&&response.status<500});
  }
  const reader=response.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});let buffer='',total=0;
  async function consume(block){
    if(block.length>16*1024*1024)throw new Error('Ein Tool-Ergebnis ist zu groß für diese Ansicht.');
    const data=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
    if(!data)return;const event=JSON.parse(data);
    if(event.schemaVersion!==STREAM_SCHEMA_VERSION||!Number.isSafeInteger(event.seq)||typeof event.turnId!=='string'||typeof event.sessionId!=='string')throw new Error('Die Antwort hat ein ungültiges Format.');
    await onEvent(event);
  }
  try{
    for(;;){
      const chunk=await reader.read();if(chunk.done)break;total+=chunk.value.byteLength;
      if(total>64*1024*1024)throw new Error('Die Antwort überschreitet das Anzeigelimit.');
      buffer+=decoder.decode(chunk.value,{stream:true});buffer=buffer.replace(/\r\n/g,'\n');
      let boundary;while((boundary=buffer.indexOf('\n\n'))!==-1){const part=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);await consume(part);}
      if(buffer.length>16*1024*1024)throw new Error('Ein Tool-Ergebnis ist zu groß für diese Ansicht.');
    }
    buffer+=decoder.decode();if(buffer.trim())await consume(buffer);
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
