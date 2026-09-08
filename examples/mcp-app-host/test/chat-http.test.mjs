import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {createAgent} from '../agent.mjs';
import {createPolicy} from '../policy.mjs';
import {serveChatStream} from '../chat-http.mjs';
import {body,createSessions,fail,json,originGuard} from '../http.mjs';

const tool={name:'read_fixture',description:'Local fixture',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true}};
const encoded=value=>new TextEncoder().encode(`data: ${JSON.stringify(value)}\n\n`);
const completed=output=>({type:'response.completed',response:{id:'response_fixture',status:'completed',output}});
const text={id:'message_fixture',type:'message',content:[{type:'output_text',text:'Fixture'}]};
async function until(fn){for(let n=0;n<100;n++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,5));}throw new Error('Fixture timeout');}
async function fixture(t,{fetcher,invoke=async()=>({content:[{type:'text',text:'Done'}]})}){
  let providerCalls=0,nativeCalls=0,drainCount=0,largestBuffered=0;
  const agent=createAgent({apiKey:'fixture-key',policy:createPolicy([tool],{allowedTools:[tool.name]}),grant:async(name,args,result)=>({id:'result_fixture',name,arguments:args,result}),
    client:{callTool:async()=>{nativeCalls++;return await invoke();}},fetcher:async(...args)=>{providerCalls++;return await fetcher(...args);}});
  const auth=createSessions();let origin;
  const server=createServer(async(req,res)=>{
    res.on('drain',()=>{drainCount++;});const write=res.write;
    res.write=function(...args){const result=write.apply(this,args);largestBuffered=Math.max(largestBuffered,res.writableLength);return result;};
    try{
      originGuard(req,origin,req.method==='POST');
      if(req.url==='/status'){const owner=auth.session(req,res,true);return json(res,200,{csrf:owner.csrf});}
      const owner=auth.session(req,res);
      if(req.method==='GET' && req.url.startsWith('/requests/'))return json(res,200,agent.requestSnapshot(req.url.slice('/requests/'.length),owner.id));
      if(req.method==='GET')return json(res,200,agent.snapshot(req.url.slice(1),owner.id));
      auth.csrf(req,owner);const input=await body(req);
      if(req.url==='/stop')return json(res,200,agent.stop(input,owner.id));
      await serveChatStream(res,agent.open(input,owner.id),agent,owner.id);
    }catch(error){if(!res.headersSent)fail(res,error);else res.destroy();}
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');origin=`http://127.0.0.1:${server.address().port}`;
  t.after(async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));});
  const status=await fetch(`${origin}/status`);const cookie=status.headers.get('set-cookie').split(';')[0],{csrf}=await status.json();
  const headers={Origin:origin,Cookie:cookie,'X-Host-CSRF':csrf,'Content-Type':'application/json',Accept:'text/event-stream'};
  return {origin,headers,agent,nativeCalls:()=>nativeCalls,providerCalls:()=>providerCalls,drainCount:()=>drainCount,largestBuffered:()=>largestBuffered,
    send:(options={})=>fetch(`${origin}/chat`,{method:'POST',headers,body:JSON.stringify({message:'Fixture only',clientTurnId:'fixture_client_turn'}),...options}),
    read:id=>fetch(`${origin}/${id}`,{headers:{Cookie:cookie}}).then(r=>r.json())};
}
async function firstEvent(response){const reader=response.body.getReader();const{value}=await reader.read();const first=new TextDecoder().decode(value).split('\n').find(line=>line.startsWith('data: '));return{reader,event:JSON.parse(first.slice(6))};}
test('actual HTTP disconnect stops provider dispatch, keeps owner-bound snapshot and rejects missing CSRF',async t=>{
  let providerController,cancelled=false;
  const f=await fixture(t,{fetcher:async()=>new Response(new ReadableStream({start(c){providerController=c;},cancel(){cancelled=true;}}),{headers:{'Content-Type':'text/event-stream'}})});
  const rejected=await f.send({headers:{...f.headers,'X-Host-CSRF':''}});assert.equal(rejected.status,403);assert.equal(f.providerCalls(),0);
  const abort=new AbortController(),response=await f.send({signal:abort.signal});assert.match(response.headers.get('content-type'),/text\/event-stream/);
  const lookup=await f.read('requests/fixture_client_turn');assert.equal(lookup.schemaVersion,'customer_agent_turn.v1');assert.equal(lookup.clientTurnId,'fixture_client_turn');
  const first=await firstEvent(response);assert.equal(first.event.type,'turn.started');await until(()=>providerController);
  assert.equal(lookup.turnId,first.event.turnId);
  providerController.enqueue(encoded({type:'response.output_text.delta',item_id:text.id,content_index:0,delta:'Fi'}));
  await first.reader.read();abort.abort();await first.reader.cancel().catch(()=>{});
  let snapshot;await until(()=>cancelled);snapshot=await f.read(first.event.turnId);
  assert.equal(snapshot.status,'stopped');assert.equal(snapshot.parts[0].text,'Fi');assert.equal(f.nativeCalls(),0);
  const foreign=await fetch(`${f.origin}/status`),foreignCookie=foreign.headers.get('set-cookie').split(';')[0];
  const denied=await fetch(`${f.origin}/${first.event.turnId}`,{headers:{Cookie:foreignCookie}});assert.equal(denied.status,404);
  const deniedRequest=await fetch(`${f.origin}/requests/fixture_client_turn`,{headers:{Cookie:foreignCookie}});assert.equal(deniedRequest.status,404);
  const missingRequest=await fetch(`${f.origin}/requests/missing_client_turn`,{headers:{Cookie:foreignCookie}});assert.deepEqual(await deniedRequest.json(),await missingRequest.json());
  const noCookie=await fetch(`${f.origin}/requests/fixture_client_turn`);assert.equal(noCookie.status,401);
  assert.equal(f.providerCalls(),1);assert.equal(f.nativeCalls(),0);
});
test('HTTP disconnect during native work retains actual result and does not start another model round',async t=>{
  const native=Promise.withResolvers();
  const f=await fixture(t,{invoke:()=>native.promise,fetcher:async()=>new Response(encoded(completed([{id:'fc_fixture',type:'function_call',name:tool.name,call_id:'call_fixture',arguments:'{}'}])),{headers:{'Content-Type':'text/event-stream'}})});
  const abort=new AbortController(),response=await f.send({signal:abort.signal});const first=await firstEvent(response);
  await until(()=>f.nativeCalls()===1);abort.abort();await first.reader.cancel().catch(()=>{});
  let snapshot;for(let n=0;n<50;n++){snapshot=await f.read(first.event.turnId);if(snapshot.status==='stopping')break;await new Promise(resolve=>setTimeout(resolve,5));}
  assert.equal(snapshot.status,'stopping');assert.equal(snapshot.toolInFlight,true);
  native.resolve({content:[{type:'text',text:'Actual result'}]});
  for(let n=0;n<50;n++){snapshot=await f.read(first.event.turnId);if(snapshot.status==='stopped')break;await new Promise(resolve=>setTimeout(resolve,5));}
  assert.equal(snapshot.status,'stopped');assert.equal(snapshot.parts[0].state,'completed');assert.equal(snapshot.parts[0].call.result.content[0].text,'Actual result');assert.equal(f.providerCalls(),1);
});
test('already closed HTTP response sets stop fence before starting admitted turn',async()=>{
  const order=[];await serveChatStream({destroyed:true},{sessionId:'session',turnId:'turn',start:async()=>{order.push('start');}},{stop(){order.push('stop');}},'owner');
  assert.deepEqual(order,['stop','start']);
});
test('large private app event drains through real HTTP and later text plus replay remain complete',async t=>{
  let round=0;const media='OPAQUE_HTTP_ATTACHMENT:'+ 'A'.repeat(3*1024*1024);
  const f=await fixture(t,{invoke:async()=>({content:[{type:'text',text:'Native result'}],_meta:{opaqueAttachment:media}}),
    fetcher:async()=>new Response(encoded(completed(round++===0?[{id:'fc_fixture',type:'function_call',name:tool.name,call_id:'call_fixture',arguments:'{}'}]:[text])),{headers:{'Content-Type':'text/event-stream'}})});
  const response=await f.send();await new Promise(resolve=>setTimeout(resolve,25));
  const wire=await response.text();const events=wire.split('\n').filter(line=>line.startsWith('data: ')).map(line=>JSON.parse(line.slice(6)));
  assert.equal(events.find(e=>e.call)?.call.result._meta.opaqueAttachment,media);assert.equal(events.at(-1).type,'turn.finished');assert.equal(events.at(-1).status,'completed');
  assert.equal(events.some(e=>e.type==='text.delta'&&e.delta==='Fixture'),true);assert.equal(f.drainCount()>0,true);
  assert.equal(f.largestBuffered()<4*1024*1024,true);assert.equal(f.nativeCalls(),1);assert.equal(f.providerCalls(),2);
  const replay=await f.send();const replayWire=await replay.text();const replayEvents=replayWire.split('\n').filter(line=>line.startsWith('data: ')).map(line=>JSON.parse(line.slice(6)));
  assert.equal(replayEvents.find(e=>e.call)?.call.result._meta.opaqueAttachment,media);assert.equal(replayEvents.at(-1).status,'completed');assert.equal(f.nativeCalls(),1);assert.equal(f.providerCalls(),2);
});
