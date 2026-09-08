import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:net';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createHash} from 'node:crypto';

test('actual host preview tokens deny every call; exact approval yields a separate live grant',async t=>{
  const root=fileURLToPath(new URL('../',import.meta.url)),dir=await mkdtemp(join(tmpdir(),'approval-preview-host-'));
  let child;
  t.after(async()=>{
    if(child&&child.exitCode===null){const stopped=once(child,'exit');child.kill('SIGTERM');const timer=setTimeout(()=>child.kill('SIGKILL'),3000);try{await stopped;}finally{clearTimeout(timer);}}
    await rm(dir,{recursive:true,force:true});
  });
  const reservation=createServer();reservation.listen(0,'127.0.0.1');await once(reservation,'listening');const port=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
  const origin=`http://127.0.0.1:${port}`,log=join(dir,'protocol.jsonl'),version=join(dir,'resource-version.txt');
  await writeFile(log,'');await writeFile(version,'v1');
  await writeFile(join(dir,'config.json'),JSON.stringify({hostOrigin:origin,command:process.execPath,args:[join(root,'test/preview-protocol-fixture.mjs')],cwd:root,
    env:{PREVIEW_FIXTURE_LOG:log,PREVIEW_FIXTURE_VERSION:version},allowedTools:['fixture_read','fixture_save','fixture_action'],autoApproveTools:[],model:'gpt-5.6-terra'}));
  child=spawn(process.execPath,['--import',join(root,'test/provider-fixture.mjs'),'server.mjs'],{cwd:root,
    env:{PATH:process.env.PATH,OPENAI_API_KEY:'fixture-key',OPENAI_MODEL:'gpt-5.6-terra',MCP_APP_HOST_CONFIG:join(dir,'config.json')},stdio:['ignore','pipe','pipe']});
  child.stderr.on('data',()=>{});
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Fixture host start timed out')),10000);
    child.stdout.on('data',data=>{if(data.toString().includes('"ready":true')){clearTimeout(timer);resolve();}});
    child.once('exit',code=>{clearTimeout(timer);reject(new Error(`Fixture host exited ${code}`));});
  });
  const status=await fetch(origin+'/api/host/status'),cookie=status.headers.get('set-cookie').split(';')[0],{csrf}=await status.json();
  const headers={Origin:origin,Cookie:cookie,'X-Host-CSRF':csrf,'Content-Type':'application/json'};
  const post=(path,value,more={})=>fetch(origin+path,{method:'POST',headers:{...headers,...more},body:JSON.stringify(value)});
  const read=(path,as=cookie)=>fetch(origin+path,{headers:{Cookie:as}});
  const records=async()=>{const text=await readFile(log,'utf8');return text.trim()?text.trim().split('\n').map(JSON.parse):[];};
  const calls=async()=>(await records()).filter(item=>item.method==='tools/call');
  const stream=async value=>{const response=await post('/api/host/chat',value,{Accept:'text/event-stream'});assert.equal(response.status,200);return(await response.text()).split('\n').filter(line=>line.startsWith('data: ')).map(line=>JSON.parse(line.slice(6)));};

  const events=await stream({message:'fixture-approval',clientTurnId:'http_preview_1'});
  const started=events[0],pending=events.find(event=>event.state==='approval_required'),preview=pending.preview;
  assert.equal(preview.mode,'preview');assert.equal(pending.call,undefined);assert.equal(preview.result,undefined);assert.equal((await calls()).length,0);
  assert.equal(preview.argumentsSha256,createHash('sha256').update(JSON.stringify(pending.approval.arguments)).digest('hex'));
  assert.deepEqual(preview.arguments,pending.approval.arguments);assert.equal((await records()).every(item=>item.method==='resources/read'),true);
  const frame=await read('/app-frame/'+preview.viewToken);assert.equal(frame.status,200);assert.match(await frame.text(),/Passive fixture v1/);
  for(const name of ['fixture_read','fixture_save','fixture_action','unlisted']){
    const denied=await post('/api/host/call',{viewToken:preview.viewToken,name,arguments:{value:'Denied request'}});
    assert.equal(denied.status,403);const body=await denied.json();assert.equal(body.error.code,'preview_readonly');assert.equal(body.approval,undefined);
  }
  assert.equal((await calls()).length,0);
  const foreignStatus=await fetch(origin+'/api/host/status'),foreignCookie=foreignStatus.headers.get('set-cookie').split(';')[0],foreign=await foreignStatus.json();
  assert.equal((await read('/app-frame/'+preview.viewToken,foreignCookie)).status,403);
  const foreignCall=await post('/api/host/call',{viewToken:preview.viewToken,name:'fixture_read',arguments:{value:'Denied'}},{Cookie:foreignCookie,'X-Host-CSRF':foreign.csrf});assert.equal(foreignCall.status,403);
  const snapshot=await(await read('/api/host/chat/turns/'+started.turnId)).json();assert.deepEqual(snapshot.parts.find(part=>part.preview).preview,preview);
  const beforeReplay=(await records()).length;await stream({message:'fixture-approval',clientTurnId:'http_preview_1'});assert.equal((await records()).length,beforeReplay);
  await writeFile(version,'v2');const drift=await read('/app-frame/'+preview.viewToken);assert.equal(drift.status,409);assert.equal((await drift.json()).error.code,'resource_drift');await writeFile(version,'v1');

  const resumed=await stream({sessionId:started.sessionId,turnId:started.turnId,approved:{id:pending.approval.id,accepted:true,arguments:{value:'Do not use replacement'}}});
  const actual=resumed.find(event=>event.call)?.call;
  assert.ok(actual);assert.notEqual(actual.viewToken,preview.viewToken);assert.equal(actual.resourceUri,preview.resourceUri);assert.equal(actual.resourceSha256,preview.resourceSha256);
  assert.deepEqual((await calls()).map(item=>item.params),[{name:'fixture_action',arguments:preview.arguments}]);
  const permanentlyDenied=await post('/api/host/call',{viewToken:preview.viewToken,name:'fixture_read',arguments:{value:'Still forbidden'}});assert.equal(permanentlyDenied.status,403);
  const actualRead=await post('/api/host/call',{viewToken:actual.viewToken,name:'fixture_read',arguments:{value:'Allowed through actual result'}});assert.equal(actualRead.status,200);assert.equal((await actualRead.json()).result.structuredContent.value,'Allowed through actual result');
  const stale=await post('/api/host/chat',{sessionId:started.sessionId,turnId:started.turnId,approved:{id:pending.approval.id,accepted:true}},{Accept:'text/event-stream'});assert.equal(stale.status,409);
  assert.equal((await calls()).length,2);

  for(const action of ['decline','stop']){
    const next=await stream({message:'fixture-approval',sessionId:started.sessionId,clientTurnId:`http_preview_${action}`});const current=next.find(event=>event.state==='approval_required');
    if(action==='decline')await stream({sessionId:started.sessionId,turnId:current.turnId,approved:{id:current.approval.id,accepted:false}});
    else assert.equal((await post('/api/host/chat/stop',{sessionId:started.sessionId,turnId:current.turnId})).status,200);
    const after=await(await read('/api/host/chat/turns/'+current.turnId)).json(),part=after.parts.find(item=>item.preview);
    assert.equal(part.state,'denied');assert.equal(part.call,undefined);assert.equal(part.preview.mode,'preview');assert.equal((await calls()).length,2);
  }
});
