import { MAX_STREAM_PENDING_EVENTS } from './host-limits.mjs';

/** Auth/CSRF and request admission happen in server.mjs before this transport. */
export async function serveChatStream(res, request, agent, owner) {
  if(res.destroyed){agent.stop({sessionId:request.sessionId,turnId:request.turnId},owner);await request.start({includeSnapshot:false});return;}
  res.writeHead(200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-store, no-transform',
    'X-Content-Type-Options':'nosniff','X-Accel-Buffering':'no'});
  res.flushHeaders();
  let unsubscribe=()=>{},closed=false,writer=null,head=0;
  let queue=[];
  const disconnected=()=>{
    closed=true;queue=[];head=0;unsubscribe();
    if(!res.writableEnded)agent.stop({sessionId:request.sessionId,turnId:request.turnId},owner);
  };
  const writeError=()=>res.destroy();
  res.on('close',disconnected);res.on('error',writeError);
  const heartbeat=setInterval(()=>{if(!closed&&!res.destroyed&&!res.writableNeedDrain)res.write(': heartbeat\n\n');},15000);
  heartbeat.unref();
  const drain=()=>new Promise(resolve=>{
    const finish=()=>{res.removeListener('drain',finish);res.removeListener('close',finish);res.removeListener('error',finish);resolve();};
    res.once('drain',finish);res.once('close',finish);res.once('error',finish);
    if(res.destroyed||!res.writableNeedDrain)finish();
  });
  async function pump(){
    try{
      while(head<queue.length&&!closed&&!res.destroyed){
        const event=queue[head++];
        // Queue bounded references, never duplicate image JSON for every waiting
        // event. Serialize one frame and respect actual socket backpressure.
        const frame=`id: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`;
        if(!res.write(frame))await drain();
        if(head>1024){queue=queue.slice(head);head=0;}
      }
      if(head===queue.length){queue=[];head=0;}
    }catch{res.destroy();}
  }
  function schedule(){
    if(writer||closed||res.destroyed)return;
    writer=pump().finally(()=>{writer=null;if(head<queue.length)schedule();});
  }
  function enqueue(event){
    if(closed||res.destroyed)return;
    if(queue.length-head>=MAX_STREAM_PENDING_EVENTS){res.destroy();return;}
    queue.push(event);
    schedule();
  }
  try{
    unsubscribe=request.subscribe(enqueue);
    if(res.destroyed)agent.stop({sessionId:request.sessionId,turnId:request.turnId},owner);
    await request.start({includeSnapshot:false});
    while(!closed&&!res.destroyed&&(writer||head<queue.length)){if(writer)await writer;else await pump();}
    if(!res.destroyed)res.end();
  }finally{
    clearInterval(heartbeat);unsubscribe();res.removeListener('close',disconnected);res.removeListener('error',writeError);
  }
}
