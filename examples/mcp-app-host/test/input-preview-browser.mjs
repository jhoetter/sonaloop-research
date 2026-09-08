// Generic input-preview qualification. Real local MCP/AppBridge, synthetic model
// stream, isolated trace file. No provider key, customer data or image generation.
import {chromium} from 'playwright-core';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=await mkdtemp(join(tmpdir(),'mcp-input-preview-'));
const origin='http://127.0.0.1:17469',trace=join(dir,'calls.jsonl'),checks=[],errors=[];let browser,child;
const check=(name,passed)=>{checks.push({name,passed:!!passed});assert.ok(passed,name);};
const calls=async()=>{try{return(await readFile(trace,'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);}catch(e){if(e.code==='ENOENT')return[];throw e;}};
await writeFile(join(dir,'config.json'),JSON.stringify({hostOrigin:origin,command:process.execPath,args:[join(root,'test/fixture-server.mjs')],cwd:root,env:{FIXTURE_TRACE_FILE:trace},model:'gpt-5.6-terra',allowedTools:['fixture_read','fixture_save','fixture_action'],autoApproveTools:[]}));
try{
 child=spawn(process.execPath,['--import',join(root,'test/provider-fixture.mjs'),'server.mjs'],{cwd:root,env:{PATH:process.env.PATH,OPENAI_API_KEY:'fixture-key',MCP_APP_HOST_CONFIG:join(dir,'config.json')},stdio:['ignore','pipe','pipe']});child.stderr.on('data',()=>{});
 await new Promise((yes,no)=>{const timer=setTimeout(()=>no(new Error('Host startup timed out')),20000);child.stdout.on('data',v=>{if(v.toString().includes('"ready":true')){clearTimeout(timer);yes();}});child.once('exit',code=>{clearTimeout(timer);no(new Error('Fixture host exited '+code));});});
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/sonaloop/.local/share/sonaloop-v4/m006a-capture-browser/chromium_headless_shell-1193/chrome-linux/headless_shell',headless:true,args:['--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1280,height:1000},reducedMotion:'reduce'});page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin);await page.locator('#status').filter({hasText:'verbunden'}).waitFor();
 const frame=()=>page.frameLocator('.app-frame');
 async function start(command='fixture-approval'){await page.locator('#prompt').fill(command);await page.locator('#send').click();await page.locator('.approval-inline').waitFor();await frame().locator('p').filter({hasText:'Vorschau'}).waitFor();}
 async function done(){await page.locator('#stop').waitFor({state:'hidden',timeout:30000});}
 async function fresh(){await page.locator('#new-chat').click();await page.locator('#welcome').waitFor();}
 await start();
 check('input preview rendered before any native tool dispatch',(await calls()).length===0);
 check('technical arguments stay collapsed',await page.locator('.tool-inspector').evaluate(el=>!el.open));
 check('preview appears before decision controls',await page.locator('.app-frame').boundingBox().then(async b=>b.y<(await page.locator('.approval-inline').boundingBox()).y));
 const firstElement=await page.locator('.app-frame').elementHandle(),firstFrame=await firstElement.contentFrame();
 check('one standard input and no synthetic tool result',await firstFrame.evaluate(()=>window.fixtureLifecycle.inputs===1&&window.fixtureLifecycle.results===0));
 await firstFrame.evaluate(()=>parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*'));
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 check('repeated initialized does not duplicate input',await firstFrame.evaluate(()=>window.fixtureLifecycle.inputs===1));
 check('customer preview is passive',await frame().getByRole('button',{name:'Change fixture'}).isDisabled()&&await frame().getByLabel('Fixture draft').isDisabled());
 await page.locator('#prompt').fill('Nächster Entwurf');
 await page.locator('#connection').click();await page.locator('#text-only').check();await page.locator('#close-connection').click();
 check('text-only does not execute or dispose input preview',(await calls()).length===0&&await page.locator('.app-frame').count()===1&&!await page.locator('.app-frame').isVisible());
 await page.locator('#connection').click();await page.locator('#text-only').uncheck();await page.locator('#close-connection').click();
 check('return from text-only keeps preview iframe',await firstElement.evaluate(el=>el===document.querySelector('.app-frame')));
 await page.locator('.approval-inline').getByRole('button',{name:'Ablehnen',exact:true}).click();await done();
 await frame().locator('p').filter({hasText:'Nicht ausgeführt'}).waitFor();
 check('decline sends cancellation and has zero native effects',(await calls()).length===0&&await firstFrame.evaluate(()=>window.fixtureLifecycle.cancelled===1&&window.fixtureLifecycle.results===0));
 check('decline preserves next composer draft',await page.locator('#prompt').inputValue()==='Nächster Entwurf');
 await firstElement.dispose();await fresh();await start();
 const liveElement=await page.locator('.app-frame').elementHandle(),liveFrame=await liveElement.contentFrame();await liveFrame.evaluate(()=>{window.previewIdentity='unchanged-document';});
 await page.locator('.approval-inline').getByRole('button',{name:'Ausführen',exact:true}).click();await done();
 await frame().locator('p').filter({hasText:'Reale MCP-Testkarte'}).waitFor();
 check('approval executes exact original arguments once',(await calls()).filter(c=>c.name==='fixture_action'&&c.arguments.value==='Reale MCP-Testkarte').length===1);
 check('actual result promotes the same iframe and document',await liveElement.evaluate(el=>el===document.querySelector('.app-frame'))&&await liveFrame.evaluate(()=>window.previewIdentity)==='unchanged-document');
 check('upgrade sends result without a second input',await liveFrame.evaluate(()=>window.fixtureLifecycle.inputs===1&&window.fixtureLifecycle.results===1&&window.fixtureLifecycle.cancelled===0));
 check('actual card activates existing interactions',await frame().getByRole('button',{name:'Change fixture'}).isEnabled()&&await frame().getByLabel('Fixture draft').isEnabled());
 await frame().getByRole('button',{name:'Change fixture'}).click();await page.locator('#approval[open]').waitFor();await page.locator('#accept').click();await frame().locator('p').filter({hasText:'Changed through MCP'}).waitFor();
 check('promoted host uses the new live action grant',(await calls()).filter(c=>c.name==='fixture_save').length===1);
 await liveElement.dispose();await fresh();await start();const beforeStop=(await calls()).length;
 await page.locator('#stop').click();await done();await frame().locator('p').filter({hasText:'Nicht ausgeführt'}).waitFor();
 check('Stop during approval cancels preview without dispatch',(await calls()).length===beforeStop);
 await fresh();await start('fixture-preview-error');await page.locator('.approval-inline').getByRole('button',{name:'Ausführen',exact:true}).click();await done();
 await frame().locator('p').filter({hasText:'Vorschau fehlgeschlagen'}).waitFor();
 check('failed native result keeps passive preview',await frame().getByRole('button',{name:'Change fixture'}).isDisabled());
 check('failed action is not repeated',(await calls()).filter(c=>c.arguments.value==='fixture-failed-preview').length===1);
 // Transport-only terminal snapshots: keep a real owner-bound input preview,
 // but inject the no-call budget-fallback shape without executing or filling memory.
 // Only turn.started reaches the browser before GET; no running/preview event can
 // hide the card first and accidentally make this recovery regression pass.
 for(const terminal of ['completed','failed']){
   await fresh();const before=(await calls()).length;let posts=0,snapshots=0,sourceValid=false;
   const message='Tool beendet. Das gespeicherte Ergebnis ist nicht darstellbar. Aktion nicht wiederholen.';
   const chatPath=origin+'/api/host/chat',snapshotPath=origin+'/api/host/chat/turns/*';
   const bufferHandler=async route=>{
     posts++;const response=await route.fetch(),body=await response.text();
     const blocks=body.split('\n\n').filter(block=>block.includes('"type":"turn.started"'));
     assert.equal(blocks.length,1);await route.fulfill({response,body:blocks[0]+'\n\n'});
   };
   const snapshotHandler=async route=>{
     snapshots++;const response=await route.fetch(),value=await response.json();
     const tool=value.parts.find(part=>part.kind==='tool');
     sourceValid=value.status==='waiting_approval'&&tool?.state==='approval_required'&&tool.preview?.mode==='preview'&&!tool.call&&await page.locator('.app-frame').count()===0;
     assert.ok(sourceValid,'Snapshot injection must start from a genuine unseen waiting preview');
     value.status=terminal;value.seq++;
     tool.state=terminal;delete tool.approval;tool.error={code:'ui_result_limit',message};
     await route.fulfill({response,body:JSON.stringify(value)});
   };
   await page.route(chatPath,bufferHandler);await page.route(snapshotPath,snapshotHandler);
   try{
     await page.locator('#prompt').fill('fixture-approval');await page.locator('#send').click();await done();
     await page.locator('.app-frame').waitFor({state:'attached'});
     const element=await page.locator('.app-frame').elementHandle(),recoveredFrame=await element.contentFrame();
     await recoveredFrame.waitForFunction(()=>window.fixtureLifecycle?.inputs===1);
     check(terminal+' no-call snapshot is recovered without any prior running/preview event',sourceValid&&posts===1&&snapshots===1);
     check(terminal+' no-call snapshot hides stale preview and shows honest terminal fallback',!await page.locator('.app-frame').isVisible()&&await page.locator('.fallback').innerText()===message&&await page.locator('.tool-state').innerText()===(terminal==='completed'?'Erledigt':'Fehlgeschlagen'));
     check(terminal+' injected terminal recovery sends no result/cancellation and executes nothing',(await calls()).length===before&&await recoveredFrame.evaluate(()=>window.fixtureLifecycle.inputs===1&&window.fixtureLifecycle.results===0&&window.fixtureLifecycle.cancelled===0));
     await element.dispose();
   }finally{await page.unroute(chatPath,bufferHandler);await page.unroute(snapshotPath,snapshotHandler);}
 }
 await fresh();await start('fixture-preview-unknown');
 const uncertainElement=await page.locator('.app-frame').elementHandle(),uncertainFrame=await uncertainElement.contentFrame();
 await page.locator('.approval-inline').getByRole('button',{name:'Ausführen',exact:true}).click();await done();
 check('unknown native outcome hides stale unsaved claim but retains frame',await page.locator('.app-frame').count()===1&&!await page.locator('.app-frame').isVisible()&&await page.locator('.fallback').innerText().then(t=>t.includes('Ausgang unklar')));
 check('admitted unknown action is never presented as cancelled',await uncertainFrame.evaluate(()=>window.fixtureLifecycle.cancelled===0&&window.fixtureLifecycle.results===0));
 check('uncertain action is not repeated',(await calls()).filter(c=>c.arguments.value==='fixture-disconnect').length===1);
 await uncertainElement.dispose();
 check('no browser errors',errors.length===0);
 console.log(JSON.stringify({kind:'real_host_input_preview_fixture',status:'passed',checks,realProviderCalls:0,customerWrites:0,injectedTerminalSnapshots:['completed','failed'],fixtureCalls:(await calls()).map(c=>c.name),errors}));
}catch(error){console.error(JSON.stringify({status:'failed',checks,error:error.message,errors}));process.exitCode=1;}
finally{await browser?.close();if(child){child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)resolve();else{child.once('exit',resolve);setTimeout(()=>{child.kill('SIGKILL');resolve();},3000).unref();}});}await rm(dir,{recursive:true,force:true});}
