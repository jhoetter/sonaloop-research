// Real host, provider-wire fixture and MCP fixture. Faults below are explicit
// browser-transport injections; no customer data or real provider is involved.
import {mkdtemp,writeFile,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';

const root=fileURLToPath(new URL('../',import.meta.url));
const dir=await mkdtemp(join(tmpdir(),'mcp-chat-recovery-'));
const origin='http://127.0.0.1:17467',checks=[],errors=[],requests=[];
let browser,child,failure;
const check=(name,value)=>{checks.push({name,passed:!!value});assert.ok(value,name);};
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};
async function bounded(promise,label){
  let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(label+' timed out')),30000);})]);}
  finally{clearTimeout(timer);}
}
const config={hostOrigin:origin,command:process.execPath,args:[join(root,'test/fixture-server.mjs')],cwd:root,env:{},
  model:'gpt-5.6-terra',allowedTools:['fixture_read','fixture_save','fixture_action'],autoApproveTools:[]};
await writeFile(join(dir,'config.json'),JSON.stringify(config));

try{
  child=spawn(process.execPath,['--import',join(root,'test/provider-fixture.mjs'),'server.mjs'],{cwd:root,
    env:{PATH:process.env.PATH,OPENAI_API_KEY:'fixture-key',OPENAI_MODEL:'gpt-5.6-terra',MCP_APP_HOST_CONFIG:join(dir,'config.json')},
    stdio:['ignore','pipe','pipe']});
  child.stderr.on('data',()=>{});
  await bounded(new Promise((resolve,reject)=>{
    child.stdout.on('data',chunk=>{if(chunk.toString().includes('"ready":true'))resolve();});
    child.once('exit',code=>reject(new Error(`Fixture host exited with ${code}`)));
  }),'Host startup');
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/sonaloop/.local/share/sonaloop-v4/m006a-capture-browser/chromium_headless_shell-1193/chrome-linux/headless_shell',headless:true,args:['--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:1280,height:960},reducedMotion:'reduce'});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    if(request.url().startsWith(origin+'/api/host/chat'))requests.push({method:request.method(),path:new URL(request.url()).pathname,body:request.postDataJSON()});
  });
  async function open(){await page.goto(origin);await page.locator('#status').filter({hasText:'verbunden'}).waitFor();}
  async function submit(text){await page.locator('#prompt').fill(text);await page.locator('#send').click();}
  async function done(){await page.locator('#stop').waitFor({state:'hidden',timeout:30000});}
  async function fresh(){await page.locator('#new-chat').click();await page.locator('#welcome').waitFor({state:'visible'});}
  async function displayed(){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
  const initialPosts=command=>requests.filter(item=>item.method==='POST'&&item.body?.message===command).length;
  const snapshots=()=>requests.filter(item=>item.method==='GET'&&item.path.includes('/chat/turns/'));
  await open();

  // A genuine fixture MCP edit must survive presentation-only switching.
  await submit('fixture-chat');await done();
  const frame=page.frameLocator('.app-frame');
  await frame.locator('p').filter({hasText:'Reale MCP-Testkarte'}).waitFor();
  const element=await page.locator('.app-frame').elementHandle();
  await frame.getByRole('button',{name:'Change fixture',exact:true}).click();
  await page.locator('#approval[open]').waitFor();await page.locator('#accept').click();
  await frame.locator('p').filter({hasText:'Changed through MCP'}).waitFor();
  const frameObject=await element.contentFrame();await frameObject.evaluate(()=>{window.recoveryIdentity='same-live-document';});
  await page.locator('#connection').click();await page.locator('#text-only').check();await page.locator('#close-connection').click();
  check('text-only hides and retains the existing MCP iframe',await page.locator('.app-frame').count()===1&&!await page.locator('.app-frame').isVisible());
  check('text-only displays the confirmed latest MCP edit',await page.locator('.fallback').innerText()==='Changed through MCP');
  await page.locator('#connection').click();await page.locator('#text-only').uncheck();await page.locator('#close-connection').click();
  check('presentation switching retains the same iframe node and document',await element.evaluate(el=>el===document.querySelector('.app-frame'))&&await frameObject.evaluate(()=>window.recoveryIdentity)==='same-live-document');
  check('confirmed MCP edit survives presentation switching',await frame.locator('p').innerText()==='Changed through MCP');
  await element.dispose();await fresh();

  // The first approval request never reaches the server. Its real snapshot
  // still says waiting_approval, so only then may the buttons become actionable.
  let interruptedApproval=0,approvalAccepted=0;
  const approvalPath=origin+'/api/host/chat';
  const approvalHandler=async route=>{
    const body=route.request().postDataJSON();
    if(body?.approved){if(interruptedApproval++===0)return route.abort('failed');approvalAccepted++;}
    await route.continue();
  };
  await page.route(approvalPath,approvalHandler);
  await submit('fixture-approval');await page.locator('.approval-inline').waitFor();
  await page.locator('#prompt').fill('Entwurf während Verbindungsfehler');
  const beforeSnapshots=snapshots().length;
  const approvalRecovery=page.waitForResponse(response=>response.request().method()==='GET'&&response.url().startsWith(origin+'/api/host/chat/turns/'));
  await page.locator('.approval-inline').getByRole('button',{name:'Ausführen',exact:true}).click();
  await approvalRecovery;
  await page.locator('.approval-inline button:not([disabled])').first().waitFor();
  check('real waiting snapshot restores approval after pre-admission transport failure',snapshots().length>beforeSnapshots&&await page.locator('.approval-inline button:enabled').count()===2);
  check('approval recovery does not execute the fixture tool automatically',approvalAccepted===0&&await page.locator('.app-frame').count()===0);
  await page.locator('.approval-inline').getByRole('button',{name:'Ausführen',exact:true}).click();await done();
  check('explicit second approval resumes the same turn exactly once',approvalAccepted===1&&await page.locator('.message.assistant').count()===1&&await page.locator('.app-frame').count()===1);
  check('approval recovery preserves the next composer draft',await page.locator('#prompt').inputValue()==='Entwurf während Verbindungsfehler');
  await page.unroute(approvalPath,approvalHandler);await fresh();

  // Forward a real request, then truncate its otherwise successful stream.
  // The durable fixture turn is complete; its first browser recovery GET fails.
  let failedGets=0,truncated=false;
  const snapshotPath=origin+'/api/host/chat/turns/*';
  const failureHandler=async route=>{
    if(failedGets++===0)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'fixture_unavailable',message:'Injected status transport failure'}})});
    await route.continue();
  };
  const truncateHandler=async route=>{
    if(route.request().postDataJSON()?.message!=='fixture-chat')return route.continue();
    const response=await route.fetch(),body=await response.text();
    const blocks=body.split('\n\n').filter(block=>block.includes('"type":"turn.started"')||block.includes('"type":"text.delta"')).slice(0,2);
    assert.equal(blocks.length,2);truncated=true;
    await route.fulfill({response,body:blocks.join('\n\n')+'\n\n'});
  };
  await page.route(snapshotPath,failureHandler);await page.route(approvalPath,truncateHandler);
  const beforeTruncated=initialPosts('fixture-chat');
  await submit('fixture-chat');await page.locator('#prompt').fill('Entwurf nach Statusfehler');
  await page.locator('.turn-notice').getByRole('button',{name:'Status prüfen',exact:true}).waitFor();
  check('failed snapshot leaves an enabled manual recovery action',truncated&&failedGets===1&&await page.locator('.turn-notice button').isEnabled());
  check('unknown state retains the original turn and blocks new chat',await page.locator('#stop').isVisible()&&await page.locator('#new-chat').isDisabled());
  await page.locator('.turn-notice').getByRole('button',{name:'Status prüfen',exact:true}).click();await done();
  await page.frameLocator('.app-frame').locator('p').filter({hasText:'Reale MCP-Testkarte'}).waitFor();
  check('manual recovery restores the real completed tool and following text',await page.locator('.tool-state').innerText()==='Erledigt'&&await page.locator('.text-part strong').innerText()==='Bereit.');
  check('snapshot recovery preserves chronological text-tool-text parts',await page.locator('.turn-parts').evaluate(el=>[...el.children].filter(n=>n.classList.contains('text-part')||n.classList.contains('tool-part')).map(n=>n.className).join(','))==='text-part,tool-part,text-part');
  check('manual recovery never repeats the original model request',initialPosts('fixture-chat')-beforeTruncated===1&&failedGets===2);
  check('recovery keeps the unsent draft and unlocks chat',await page.locator('#prompt').inputValue()==='Entwurf nach Statusfehler'&&await page.locator('#new-chat').isEnabled());
  check('confirmed recovery clears obsolete connection warnings',!await page.locator('#error').isVisible()&&await page.locator('.turn-notice').count()===0);
  await page.unroute(snapshotPath,failureHandler);await page.unroute(approvalPath,truncateHandler);await fresh();

  // A deliberately injected Stop acknowledgement leaves the actual fixture
  // stream running. Capture its real old GET and deliver it after terminal SSE.
  const captured=deferred(),release=deferred(),delivered=deferred();let oldSnapshot;
  const delayedHandler=async route=>{
    try{
      const response=await route.fetch();oldSnapshot=await response.json();captured.resolve();
      await bounded(release.promise,'Delayed snapshot release');await route.fulfill({response});delivered.resolve();
    }catch(error){captured.reject(error);delivered.reject(error);throw error;}
  };
  const stopPath=origin+'/api/host/chat/stop';
  const stopHandler=async route=>{
    const {turnId,sessionId}=route.request().postDataJSON();
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({turnId,sessionId,status:'stopping',toolInFlight:false})});
  };
  await page.route(snapshotPath,delayedHandler);await page.route(stopPath,stopHandler);
  await submit('fixture-hold');await page.locator('.text-part').filter({hasText:'langsam'}).waitFor();
  await page.locator('#stop').click();await bounded(captured.promise,'Running snapshot capture');
  check('race fixture captured a genuine nonterminal snapshot',oldSnapshot.status==='running');
  await done();const completedText=await page.locator('.text-part').innerText();
  const current=await (await page.request.get(origin+'/api/host/chat/turns/'+oldSnapshot.turnId)).json();
  check('terminal stream is demonstrably newer than the delayed snapshot',current.status==='completed'&&current.seq>oldSnapshot.seq);
  release.resolve();await bounded(delivered.promise,'Delayed snapshot delivery');await displayed();
  check('late old GET cannot truncate completed text or revive progress',await page.locator('.text-part').innerText()===completedText&&!await page.locator('.turn-progress').isVisible());
  check('late old GET cannot relock the completed turn',!await page.locator('#stop').isVisible()&&await page.locator('#new-chat').isEnabled());
  check('the stale-snapshot scenario does not repeat the model request',initialPosts('fixture-hold')===1);
  await page.unroute(snapshotPath,delayedHandler);await page.unroute(stopPath,stopHandler);

  // Admit a real request but buffer all its SSE bytes at the browser transport.
  // Stop therefore has only clientTurnId; recovery must look up that same turn
  // and send a real Stop, without re-POSTing the original prompt.
  await fresh();
  const forwarded=deferred(),earlySettled=deferred();let earlyInput,earlyStopRequested=false;
  const earlyHandler=async route=>{
    earlyInput=route.request().postDataJSON();forwarded.resolve();
    try{const response=await route.fetch();await route.fulfill({response});}
    catch(error){if(!earlyStopRequested)throw error;}
    finally{earlySettled.resolve();}
  };
  await page.route(approvalPath,earlyHandler);
  const beforeEarly=initialPosts('fixture-hold');
  await submit('fixture-hold');await bounded(forwarded.promise,'Early request forwarding');
  let admitted;
  for(let attempt=0;attempt<100;attempt++){
    const response=await page.request.get(origin+'/api/host/chat/requests/'+earlyInput.clientTurnId);
    if(response.ok()){admitted=await response.json();break;}
    await new Promise(resolve=>setTimeout(resolve,25));
  }
  check('early Stop fixture is admitted before any SSE reaches the browser',admitted?.status==='running'&&await page.locator('.text-part').count()===0);
  await page.locator('#prompt').fill('Entwurf nach frühem Stop');earlyStopRequested=true;
  await page.locator('#stop').click();await done();await bounded(earlySettled.promise,'Early transport cleanup');
  const actual=await (await page.request.get(origin+'/api/host/chat/requests/'+earlyInput.clientTurnId)).json();
  check('Stop before turn.started recovers by owner-bound client request ID',requests.some(item=>item.method==='GET'&&item.path==='/api/host/chat/requests/'+earlyInput.clientTurnId));
  check('early Stop reaches the real admitted turn and confirms stopped',actual.turnId===admitted.turnId&&actual.status==='stopped'&&requests.filter(item=>item.path==='/api/host/chat/stop'&&item.body?.turnId===actual.turnId).length===1);
  check('early Stop preserves draft and never resubmits the prompt',initialPosts('fixture-hold')-beforeEarly===1&&await page.locator('#prompt').inputValue()==='Entwurf nach frühem Stop');
  await page.unroute(approvalPath,earlyHandler);

  // A terminal turn may still offer a read-only status check. Leaving that
  // conversation must invalidate its delayed response, including session state.
  await fresh();await submit('fixture-error');await done();
  const abandonedCaptured=deferred(),abandonedRelease=deferred(),abandonedDelivered=deferred();
  const abandonedHandler=async route=>{
    const response=await route.fetch();abandonedCaptured.resolve();
    await bounded(abandonedRelease.promise,'Abandoned snapshot release');
    await route.fulfill({response});abandonedDelivered.resolve();
  };
  await page.route(snapshotPath,abandonedHandler);
  await page.locator('.turn-error').getByRole('button',{name:'Status prüfen',exact:true}).click();
  await bounded(abandonedCaptured.promise,'Abandoned snapshot capture');await fresh();
  abandonedRelease.resolve();await bounded(abandonedDelivered.promise,'Abandoned snapshot delivery');await displayed();
  check('late status response cannot repopulate a cleared conversation',await page.locator('#welcome').isVisible()&&await page.locator('.message').count()===0);
  await page.unroute(snapshotPath,abandonedHandler);
  await submit('fixture-hold');await page.locator('.text-part').filter({hasText:'langsam'}).waitFor();
  const nextRequest=requests.findLast(item=>item.method==='POST'&&item.body?.message==='fixture-hold');
  check('late status response cannot restore the old session to New Chat',nextRequest.body.sessionId===undefined);
  await page.locator('#stop').click();await done();

  await page.setViewportSize({width:320,height:568});
  check('mobile New Chat has an accessible name',await page.getByRole('button',{name:'Neuer Chat',exact:true}).isVisible());
  check('no page errors during recovery and iframe scenarios',errors.length===0);
}catch(error){failure=error.message;}
finally{
  await browser?.close();
  if(child){child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)resolve();else{child.once('exit',resolve);setTimeout(()=>{child.kill('SIGKILL');resolve();},3000).unref();}});}
  await rm(dir,{recursive:true,force:true});
}
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
console.log(JSON.stringify({kind:'real_host_MCP_and_browser_with_synthetic_provider_and_injected_transport_faults',status:failure?'failed':'passed',
  checks,error:failure,errors,realProviderCalls:0,nativeCustomerWrites:0,fixtureOnly:true,origin,
  qualifierSha256:sha(await readFile(new URL(import.meta.url))),hostBundleSha256:sha(await readFile(join(root,'dist/host.js'))),cleanup:'browser closed; owned fixture host terminated; temporary config removed'}));
if(failure)process.exitCode=1;
