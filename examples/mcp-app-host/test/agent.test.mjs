import test from 'node:test';
import assert from 'node:assert/strict';
import {createAgent} from '../agent.mjs';
import {createPolicy} from '../policy.mjs';
const tool=(name,readonly,visibility=['model','app'])=>({name,description:'Fixture',inputSchema:{type:'object',properties:{operation_id:{type:'string'}},required:['operation_id'],additionalProperties:false},annotations:{readOnlyHint:readonly},_meta:{ui:{resourceUri:'ui://fixture/card',visibility}}});
function fixture({name='read',readonly=true,visibility,unknown=false}={}){
  let invoked=0;const payloads=[];let round=0;
  const policy=createPolicy([tool(name,readonly,visibility)],{allowedTools:[name]});
  const agent=createAgent({policy,model:'fixture',apiKey:'fixture-key',grant:async(name,args,result)=>({name,arguments:args,result}),
    client:{callTool:async()=>{invoked++;if(unknown)throw new Error('PRIVATE transport diagnostics');return{content:[{type:'text',text:'safe'}],structuredContent:{value:'native'},_meta:{secret:'PRIVATE'}};}},
    fetcher:async(_url,options)=>{payloads.push(JSON.parse(options.body));return new Response(`data: ${JSON.stringify({type:'response.completed',response:{status:'completed',id:'fixture-response',output:round++===0?[{id:'fc_one',type:'function_call',name,call_id:'one',arguments:'{"operation_id":"stable"}'}]:[{id:'msg_one',type:'message',content:[{type:'output_text',text:'Completed'}]}]}})}\n\n`,{headers:{'Content-Type':'text/event-stream'}});}});
  return {agent,payloads,invoked:()=>invoked};
}
test('model chooses discovered tool and private metadata stays outside next model call',async()=>{
  const f=fixture();const result=await f.agent.chat('read current data',undefined,'owner');
  assert.equal(f.invoked(),1);assert.equal(result.calls[0].name,'read');
  assert.equal(JSON.stringify(f.payloads).includes('PRIVATE'),false);
  assert.equal(f.payloads[0].tools[0].strict,false);
});
test('model write pauses before execution and exact approval resumes once',async()=>{
  const f=fixture({name:'write',readonly:false});const pending=await f.agent.chat('create it',undefined,'owner');
  assert.equal(f.invoked(),0);assert.equal(pending.approval.name,'write');
  await assert.rejects(()=>f.agent.chat('',pending.sessionId,'other',{id:pending.approval.id,accepted:true}),/abgelaufen/);
  const done=await f.agent.chat('',pending.sessionId,'owner',{id:pending.approval.id,accepted:true});
  assert.equal(done.text,'Completed');assert.equal(f.invoked(),1);
  await assert.rejects(()=>f.agent.chat('',pending.sessionId,'owner',{id:pending.approval.id,accepted:true}));
  assert.equal(f.invoked(),1);
});
test('app-only tool is absent from model schema and cannot be smuggled in response',async()=>{
  const f=fixture({name:'app_write',readonly:false,visibility:['app']});
  await assert.rejects(()=>f.agent.chat('try',undefined,'owner'),/not enabled/);
  assert.equal(f.payloads[0].tools.length,0);assert.equal(f.invoked(),0);
});
test('unknown tool transport outcome is not retried and private exception is sanitized',async()=>{
  const f=fixture({unknown:true});await assert.rejects(()=>f.agent.chat('read',undefined,'owner'),error=>error.code==='outcome_unknown'&&!error.message.includes('PRIVATE'));
  assert.equal(f.invoked(),1);assert.equal(f.payloads.length,1);
});
