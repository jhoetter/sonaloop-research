import test from 'node:test';
import assert from 'node:assert/strict';
import {createAgent} from '../agent.mjs';
import {createPolicy,sha} from '../policy.mjs';

const args={value:'Exact proposed value',nested:{safe:true}};
const uri='ui://fixture/preview';
const tool={name:'fixture_write',description:'Fixture only',inputSchema:{type:'object',properties:{value:{type:'string'},nested:{type:'object',properties:{safe:{type:'boolean'}},required:['safe'],additionalProperties:false}},required:['value','nested'],additionalProperties:false},_meta:{ui:{resourceUri:uri,visibility:['model','app']}}};
const preview=arguments_=>({id:'preview_fixture',name:tool.name,arguments:arguments_,argumentsSha256:sha(arguments_),resourceUri:uri,resourceSha256:'a'.repeat(64),viewToken:'passive_fixture',mode:'preview'});
function fixture({prepare,appOnly=false}={}){
  const writes=[],previews=[],payloads=[];let round=0;
  const policy=createPolicy([{...tool,...(appOnly?{_meta:{ui:{resourceUri:uri,visibility:['app']}}}:{})}],{allowedTools:[tool.name]});
  const agent=createAgent({policy,apiKey:'fixture-key',client:{callTool:async input=>{writes.push(input);return{content:[{type:'text',text:'Actual fixture result'}]};}},
    grant:async(name,arguments_,result)=>({id:'actual_fixture',name,arguments:arguments_,result,viewToken:'active_fixture',resourceUri:uri,resourceSha256:'a'.repeat(64)}),
    preparePreview:async(name,arguments_,owner,options)=>{previews.push({name,args:arguments_,owner});return prepare?await prepare(arguments_,options):preview(arguments_);},
    fetcher:async(_url,options)=>{payloads.push(JSON.parse(options.body));const output=round++===0?[{id:'fc_fixture',type:'function_call',call_id:'call_fixture',name:tool.name,arguments:JSON.stringify(args)}]:[{id:'msg_fixture',type:'message',content:[{type:'output_text',text:'Actual result received'}]}];
      return new Response(`data: ${JSON.stringify({type:'response.completed',response:{id:'resp_fixture',status:'completed',output}})}\n\n`,{headers:{'Content-Type':'text/event-stream'}});}});
  const input={message:'Propose a write',clientTurnId:'preview_client_1'};
  return{agent,writes,previews,payloads,input,open:()=>agent.open(input,'owner')};
}
test('preview is input-only, owner-bound and replayable before any native effect',async()=>{
  const f=fixture(),request=f.open(),events=[];request.subscribe(event=>events.push(event));const result=await request.start();
  const part=result.parts[0];assert.equal(result.status,'waiting_approval');assert.equal(part.call,undefined);assert.equal(part.preview.result,undefined);
  assert.deepEqual(part.preview.arguments,args);assert.equal(part.preview.argumentsSha256,sha(args));assert.equal(part.preview.mode,'preview');
  assert.deepEqual(f.previews,[{name:tool.name,args,owner:'owner'}]);assert.equal(f.writes.length,0);assert.equal(f.payloads.length,1);
  assert.equal(events.find(event=>event.state==='approval_required').preview.viewToken,'passive_fixture');
  await f.open().start();f.agent.requestSnapshot(f.input.clientTurnId,'owner');assert.equal(f.previews.length,1);assert.equal(f.payloads.length,1);assert.equal(f.writes.length,0);
});
test('confirmation executes only frozen original args and returns a separate actual grant',async()=>{
  const f=fixture(),pending=await f.open().start(),part=pending.parts[0],approvalId=part.approval.id;
  part.preview.arguments.value='Changed browser copy';part.approval.arguments.nested.safe=false;
  const result=await f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved:{id:approvalId,accepted:true,arguments:{value:'Untrusted replacement'}}},'owner').start();
  assert.equal(result.parts[0].id,part.id);assert.deepEqual(f.writes,[{name:tool.name,arguments:args}]);
  assert.equal(result.parts[0].preview.viewToken,'passive_fixture');assert.equal(result.parts[0].call.viewToken,'active_fixture');assert.deepEqual(result.parts[0].preview.arguments,args);
  assert.equal(f.previews.length,1);assert.throws(()=>f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved:{id:approvalId,accepted:true}},'owner'));
});
test('resource preview failure is sanitized and does not authorize or block the pending action',async()=>{
  const f=fixture({prepare:async()=>{throw new Error('PRIVATE resource diagnostics');}}),pending=await f.open().start(),part=pending.parts[0];
  assert.equal(pending.status,'waiting_approval');assert.equal(part.preview,undefined);assert.match(part.previewError,/Vorschau.*nicht verfügbar/);assert.equal(JSON.stringify(pending).includes('PRIVATE'),false);assert.equal(f.writes.length,0);
  const result=await f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved:{id:part.approval.id,accepted:true}},'owner').start();assert.equal(result.status,'completed');assert.equal(f.writes.length,1);
});
test('decline and Stop preserve passive preview and perform no native write',async()=>{
  for(const action of ['decline','stop']){
    const f=fixture(),request=f.open(),pending=await request.start();let result;
    if(action==='stop'){f.agent.stop(request,'owner');result=request.snapshot();}
    else result=await f.agent.open({sessionId:pending.sessionId,turnId:pending.turnId,approved:{id:pending.parts[0].approval.id,accepted:false}},'owner').start();
    assert.equal(result.parts[0].state,'denied');assert.equal(result.parts[0].call,undefined);assert.equal(result.parts[0].preview.mode,'preview');assert.equal(f.writes.length,0);
  }
});
test('Stop aborts resource preparation and cannot publish a late preview or approval',async()=>{
  const started=Promise.withResolvers();let aborted=false;
  const f=fixture({prepare:(_args,{signal})=>new Promise((resolve,reject)=>{signal.addEventListener('abort',()=>{aborted=true;reject(signal.reason);},{once:true});started.resolve();})});
  const request=f.open(),events=[];request.subscribe(event=>events.push(event));const done=request.start();await started.promise;f.agent.stop(request,'owner');
  const result=await done;assert.equal(aborted,true);assert.equal(result.status,'stopped');assert.equal(f.writes.length,0);assert.equal(events.some(event=>event.type==='turn.paused'||event.preview),false);
});
test('unauthorized model tools never obtain a preview resource grant',async()=>{
  const f=fixture({appOnly:true}),result=await f.open().start();assert.equal(result.status,'failed');assert.equal(f.previews.length,0);assert.equal(f.writes.length,0);
});
