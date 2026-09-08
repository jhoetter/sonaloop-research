import test from 'node:test';
import assert from 'node:assert/strict';
import {createAgent} from '../agent.mjs';
import {createPolicy} from '../policy.mjs';

const tool=(name,readOnlyHint=true)=>({name,description:'Fixture only',inputSchema:{type:'object',properties:{operation_id:{type:'string'}},required:['operation_id'],additionalProperties:false},annotations:{readOnlyHint}});
const call=(name='read',id='one')=>({id:`fc_${id}`,type:'function_call',name,call_id:id,arguments:'{"operation_id":"stable"}'});
const message=(text='Done')=>({id:'msg_final',type:'message',role:'assistant',content:[{type:'output_text',text}]});
const event=value=>`data: ${JSON.stringify(value)}\n\n`;
const complete=output=>({type:'response.completed',response:{status:'completed',id:'response_fixture',output,usage:{input_tokens:1,output_tokens:2,total_tokens:3}}});
const response=(output,events=[])=>new Response([...events,complete(output)].map(event).join(''),{headers:{'Content-Type':'text/event-stream'}});
const deferred=()=>Promise.withResolvers();
async function until(predicate){for(let n=0;n<100;n++){if(predicate())return;await new Promise(resolve=>setImmediate(resolve));}throw new Error('Fixture did not reach state');}
function fixture({readonly=true,fetcher,invoke,grant}={}){
  const payloads=[],invocations=[];let round=0;
  const policy=createPolicy([tool('read'),tool('write',false)],{allowedTools:['read','write']});
  const agent=createAgent({policy,apiKey:'fixture-key',client:{async callTool(input){invocations.push(input);return invoke ? await invoke(input) : {content:[{type:'text',text:'Native completed'}],_meta:{private:'APP_ONLY'}};}},
    grant:grant || (async(name,args,result)=>({id:'grant_fixture',name,arguments:args,result,viewToken:'opaque-owner-grant'})),
    fetcher:async(_url,options)=>{payloads.push(JSON.parse(options.body));return fetcher ? await fetcher(round++,options) : response(round++===0?[call(readonly?'read':'write')]:[message()]);}});
  return {agent,payloads,invocations,open:(id='client_turn_1',sessionId)=>agent.open({message:'Please use the tool',clientTurnId:id,sessionId},'owner')};
}
test('early identities precede provider dispatch; actual deltas arrive before completion',async()=>{
  let controller;const f=fixture({fetcher:async()=>new Response(new ReadableStream({start(c){controller=c;}}),{headers:{'Content-Type':'text/event-stream'}})});
  const request=f.open(),events=[];request.subscribe(e=>events.push(e));
  assert.equal(events[0].type,'turn.started');assert.equal(f.payloads.length,0);
  const done=request.start();await until(()=>controller);
  controller.enqueue(new TextEncoder().encode(event({type:'response.output_text.delta',item_id:'msg_final',content_index:0,delta:'Hallo '})));
  await until(()=>events.some(e=>e.type==='text.delta'));
  assert.equal(request.snapshot().status,'running');assert.equal(request.snapshot().parts[0].text,'Hallo ');
  controller.enqueue(new TextEncoder().encode(event(complete([message('Hallo Welt')]))));
  const result=await done;assert.equal(result.status,'completed');assert.equal(result.parts[0].text,'Hallo Welt');
  assert.equal(f.payloads[0].model,'gpt-5.6-terra');assert.deepEqual(f.payloads[0].reasoning,{effort:'none'});assert.equal(f.payloads[0].stream,true);
  assert.equal(events.filter(e=>e.type==='text.delta').every(e=>e.partId===result.parts[0].id),true);
});
test('completed native call survives later provider failure and duplicate request never reruns it',async()=>{
  const f=fixture({fetcher:async round=>round===0?response([call()]):new Response('PRIVATE provider diagnostics',{status:503})});
  const request=f.open(),events=[];request.subscribe(e=>events.push(e));const result=await request.start();
  assert.equal(result.status,'failed');assert.equal(result.parts[0].state,'completed');assert.equal(result.parts[0].call.result.content[0].text,'Native completed');
  assert.equal(events.findIndex(e=>e.type==='tool.state'&&e.state==='completed')<events.findIndex(e=>e.type==='turn.finished'),true);
  const replay=await f.open().start();assert.equal(replay.turnId,result.turnId);assert.equal(f.invocations.length,1);assert.equal(f.payloads.length,2);
  assert.equal(JSON.stringify(f.payloads).includes('APP_ONLY'),false);assert.equal(JSON.stringify(result.error).includes('PRIVATE'),false);
  assert.throws(()=>f.agent.snapshot(result.turnId,'other'),e=>e.code==='turn_missing');
  assert.throws(()=>f.agent.stop({sessionId:result.sessionId,turnId:result.turnId},'other'),e=>e.code==='turn_missing');
  assert.throws(()=>f.agent.open({message:'Different',clientTurnId:'client_turn_1'},'owner'),e=>e.code==='request_conflict');
});
test('approval continuation consumes once, retains call identity, rejects overlap and foreign owner',async()=>{
  const f=fixture({readonly:false});const request=f.open();const pending=await request.start();
  assert.equal(pending.status,'waiting_approval');assert.equal(f.invocations.length,0);
  const part=pending.parts[0],approved={id:part.approval.id,accepted:true};
  assert.throws(()=>f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved},'other'));
  assert.throws(()=>f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved:{id:'wrong',accepted:true}},'owner'),e=>e.code==='approval_missing');
  assert.throws(()=>f.open('client_turn_2',pending.sessionId),e=>e.code==='busy');
  const continuation=f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved},'owner');
  assert.throws(()=>f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved},'owner'),e=>e.code==='busy');
  const done=await continuation.start();assert.equal(done.parts[0].id,part.id);assert.equal(done.parts[0].state,'completed');assert.equal(f.invocations.length,1);
  assert.throws(()=>f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved},'owner'),e=>e.code==='approval_missing');
});
test('stop aborts pending provider stream without dispatching its proposed tool',async()=>{
  let controller,cancelled=false;const f=fixture({fetcher:async()=>new Response(new ReadableStream({start(c){controller=c;},cancel(){cancelled=true;}}),{headers:{'Content-Type':'text/event-stream'}})});
  const request=f.open(),done=request.start();await until(()=>controller);
  controller.enqueue(new TextEncoder().encode(event({type:'response.output_item.added',item:call()})));
  await until(()=>request.snapshot().parts.length===1);
  const stopped=f.agent.stop(request,'owner');assert.equal(stopped.toolInFlight,false);
  const result=await done;assert.equal(result.status,'stopped');assert.equal(result.parts[0].state,'denied');assert.equal(f.invocations.length,0);assert.equal(cancelled,true);
});
test('stop waits for an admitted native result, then forbids another provider round',async()=>{
  const native=deferred();const f=fixture({invoke:()=>native.promise});
  const request=f.open(),done=request.start();await until(()=>f.invocations.length===1);
  const ack=f.agent.stop(request,'owner');assert.equal(ack.status,'stopping');assert.equal(ack.toolInFlight,true);
  native.resolve({content:[{type:'text',text:'Persisted'}]});const result=await done;
  assert.equal(result.status,'stopped');assert.equal(result.parts[0].state,'completed');assert.equal(result.parts[0].call.result.content[0].text,'Persisted');assert.equal(f.payloads.length,1);
});
test('unknown native outcome remains failed and explicit even after stop; no automatic retry',async()=>{
  const native=deferred();const f=fixture({invoke:()=>native.promise});
  const request=f.open(),done=request.start();await until(()=>f.invocations.length===1);f.agent.stop(request,'owner');native.reject(new Error('PRIVATE'));
  const result=await done;assert.equal(result.status,'failed');assert.equal(result.error.code,'outcome_unknown');assert.equal(result.parts[0].state,'outcome_unknown');
  await f.open().start();assert.equal(f.invocations.length,1);assert.equal(f.payloads.length,1);assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
});
test('stop of pending approval records non-execution and a subsequent turn has no dangling call',async()=>{
  const f=fixture({readonly:false});const request=f.open(),pending=await request.start();const approval=pending.parts[0].approval;
  assert.equal(f.agent.stop(request,'owner').status,'stopped');
  assert.throws(()=>f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved:{id:approval.id,accepted:true}},'owner'),e=>e.code==='approval_missing');
  const done=await f.open('client_turn_2',pending.sessionId).start();assert.equal(done.status,'completed');assert.equal(f.invocations.length,0);
  assert.equal(f.payloads[1].input.some(x=>x.type==='function_call_output'&&x.call_id==='one'),true);
});
test('stop between accepted approval and continuation start prevents native admission',async()=>{
  const f=fixture({readonly:false});const first=f.open(),pending=await first.start();
  const continuation=f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved:{id:pending.parts[0].approval.id,accepted:true}},'owner');
  f.agent.stop(continuation,'owner');const result=await continuation.start();assert.equal(result.status,'stopped');assert.equal(f.invocations.length,0);
  await f.open('client_turn_2',pending.sessionId).start();assert.equal(f.payloads[1].input.some(x=>x.type==='function_call_output'),true);
});
test('invalid model arguments never execute and do not poison the next input history',async()=>{
  const f=fixture({fetcher:async round=>round===0?response([{...call(),arguments:'{bad'}]):response([message()])});
  const first=f.open(),failed=await first.start();assert.equal(failed.error.code,'model_arguments');assert.equal(f.invocations.length,0);
  await f.open('client_turn_2',failed.sessionId).start();assert.equal(f.payloads[1].input.some(x=>x.type==='function_call'),false);
});
test('UI grant failure preserves actual tool success and bounded oversized result cannot invite retry',async()=>{
  const f=fixture({grant:async()=>{throw new Error('PRIVATE resource');}});const result=await f.open().start();
  assert.equal(result.parts[0].state,'completed');assert.equal(result.parts[0].call.result.content[0].text,'Native completed');assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
  const large=fixture({invoke:async()=>({content:[{type:'text',text:'x'.repeat(1100000)}]})});const bounded=await large.open().start();
  assert.equal(bounded.parts[0].state,'completed');assert.equal(Buffer.byteLength(JSON.stringify(bounded))<10000,true);assert.equal(large.invocations.length,1);
});
test('streamed text or tool identity missing from final output cannot be presented as completed',async()=>{
  for(const progress of [
    {type:'response.output_text.delta',item_id:'msg_missing',content_index:0,delta:'Unconfirmed'},
    {type:'response.output_item.added',item:call('read','missing')},
  ]){
    const f=fixture({fetcher:async()=>response([message()], [progress])});const result=await f.open().start();
    assert.equal(result.status,'failed');assert.equal(result.error.code,'provider_stream_invalid');assert.equal(f.invocations.length,0);
  }
});
test('incremental reconnect replays exact deltas without duplicating an already seen prefix',async()=>{
  const f=fixture({fetcher:async()=>response([message('AB')],[
    {type:'response.output_text.delta',item_id:'msg_final',content_index:0,delta:'A'},
    {type:'response.output_text.delta',item_id:'msg_final',content_index:0,delta:'B'},
  ])});
  const request=f.open(),first=[];request.subscribe(e=>first.push(e));await request.start();
  const a=first.find(e=>e.type==='text.delta');let displayed=a.delta;const replay=f.open();
  replay.subscribe(e=>{if(e.seq>a.seq&&e.type==='text.delta')displayed+=e.delta;});await replay.start();
  assert.equal(displayed,'AB');assert.equal(f.payloads.length,1);
});
