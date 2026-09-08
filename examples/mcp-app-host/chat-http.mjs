/** Auth/CSRF and request admission happen in server.mjs before this transport. */
export async function serveChatStream(res, request, agent, owner) {
  if(res.destroyed){agent.stop({sessionId:request.sessionId,turnId:request.turnId},owner);await request.start();return;}
  res.writeHead(200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-store, no-transform',
    'X-Content-Type-Options':'nosniff','X-Accel-Buffering':'no'});
  res.flushHeaders();
  let unsubscribe=()=>{};
  const disconnected=()=>{
    unsubscribe();
    if (!res.writableEnded) agent.stop({sessionId:request.sessionId,turnId:request.turnId},owner);
  };
  res.on('close',disconnected);
  const heartbeat=setInterval(()=>{if(!res.destroyed)res.write(': heartbeat\n\n');},15000);
  heartbeat.unref();
  try {
    unsubscribe=request.subscribe(event=>{
      if (res.destroyed) return;
      res.write(`id: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`);
      // A stalled observer cannot accumulate unbounded queued tool results.
      if (res.writableLength > 2 * 1024 * 1024) res.destroy();
    });
    if(res.destroyed) agent.stop({sessionId:request.sessionId,turnId:request.turnId},owner);
    await request.start();
    if (!res.destroyed) res.end();
  } finally { clearInterval(heartbeat);unsubscribe();res.removeListener('close',disconnected); }
}
