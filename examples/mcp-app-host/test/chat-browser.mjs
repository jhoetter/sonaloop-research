import {mkdtemp,writeFile,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=await mkdtemp(join(tmpdir(),'mcp-chat-ux-'));
const origin='http://127.0.0.1:17465',checks=[],errors=[];let browser,child;
const check=(name,value)=>{checks.push({name,passed:!!value});assert.ok(value,name);};
await writeFile(join(dir,'config.json'),JSON.stringify({hostOrigin:origin,command:process.execPath,args:[join(root,'test/fixture-server.mjs')],cwd:root,env:{},model:'gpt-5.6-terra',allowedTools:['fixture_read','fixture_save','fixture_action'],autoApproveTools:[]}));
try{
  child=spawn(process.execPath,['--import',join(root,'test/provider-fixture.mjs'),'server.mjs'],{cwd:root,env:{...process.env,OPENAI_API_KEY:'fixture-key',OPENAI_MODEL:'gpt-5.6-terra',MCP_APP_HOST_CONFIG:join(dir,'config.json')},stdio:['ignore','pipe','pipe']});
  let diagnostic='';child.stderr.on('data',chunk=>{diagnostic=(diagnostic+chunk).slice(-3000);});
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Host start timeout '+diagnostic)),20000);child.stdout.on('data',chunk=>{if(chunk.toString().includes('"ready":true')){clearTimeout(timer);resolve();}});child.once('exit',code=>{clearTimeout(timer);reject(new Error(`Host exit ${code}: ${diagnostic}`));});});
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/sonaloop/.local/share/sonaloop-v4/m006a-capture-browser/chromium_headless_shell-1193/chrome-linux/headless_shell',headless:true,args:['--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:1280,height:960},reducedMotion:'reduce'});page.on('pageerror',e=>errors.push(e.message));
  const requests=[];page.on('request',request=>{if(request.url().startsWith(origin+'/api/host/chat'))requests.push({method:request.method(),path:new URL(request.url()).pathname,body:request.postDataJSON()});});
  await page.goto(origin);await page.locator('#status').filter({hasText:'verbunden'}).waitFor();check('modern model visible',await page.locator('#model').innerText()==='GPT-5.6 Terra');
  async function submit(text){await page.locator('#prompt').fill(text);await page.locator('#send').click();}
  async function done(){await page.locator('#stop').waitFor({state:'hidden',timeout:30000});}
  async function fresh(){await page.locator('#new-chat').click();await page.locator('#welcome').waitFor({state:'visible'});}
  await submit('fixture-chat');
  check('composer clears immediately after submit',await page.locator('#prompt').inputValue()==='');
  check('user message visible immediately',await page.locator('.message.user').count()===1);
  check('waiting phase and Stop visible',await page.locator('#stop').isVisible());
  await page.locator('#prompt').fill('Mein nächster Entwurf');
  await page.locator('.text-part').filter({hasText:'Ich schaue'}).waitFor();
  check('text arrives before turn completion',await page.locator('#stop').isVisible());
  await page.frameLocator('.app-frame').locator('p').filter({hasText:'Reale MCP-Testkarte'}).waitFor();
  const frameSrc=await page.locator('.app-frame').getAttribute('src');
  const frame=page.frameLocator('.app-frame');await frame.getByLabel('Fixture draft').fill('Ungespeicherter Kartenentwurf');
  await page.setViewportSize({width:390,height:420});
  await page.locator('#scroll-area').evaluate(el=>{el.scrollTop=0;el.dispatchEvent(new Event('scroll'));});
  await done();
  check('stream completion respects reading position',await page.locator('#scroll-area').evaluate(el=>el.scrollTop<50));
  await page.locator('#to-latest').waitFor({state:'visible'});await page.locator('#to-latest').click();
  await page.waitForFunction(()=>{const el=document.getElementById('scroll-area');return el.scrollHeight-el.scrollTop-el.clientHeight<80;});
  check('jump to latest returns to conversation end',true);
  await page.setViewportSize({width:1280,height:960});
  check('next draft survives successful streaming',await page.locator('#prompt').inputValue()==='Mein nächster Entwurf');
  check('MCP card is not remounted by streamed assistant text',await page.locator('.app-frame').getAttribute('src')===frameSrc&&await frame.getByLabel('Fixture draft').inputValue()==='Ungespeicherter Kartenentwurf');
  const kinds=await page.locator('.turn-parts').evaluate(el=>[...el.children].map(n=>n.className));
  check('text/tool/card/follow-up have chronological parts',kinds[0]==='text-part'&&kinds[1]==='tool-part'&&kinds[2]==='text-part');
  check('tool details are collapsed after normal completion',await page.locator('.tool-inspector').evaluate(el=>!el.open));
  check('markdown is rendered and scripts/unsafe links removed',await page.locator('.text-part strong').innerText()==='Bereit.'&&!await page.evaluate(()=>window.fixtureInjection)&&await page.locator('.text-part a[href^="javascript:"]').count()===0);
  await page.locator('#new-chat').click();check('dirty MCP card blocks destructive new-chat reset',await page.locator('.app-frame').count()===1&&await page.locator('#error').isVisible());
  await frame.getByLabel('Fixture draft').fill('');await fresh();check('new chat preserves the unsent composer draft',await page.locator('#prompt').inputValue()==='Mein nächster Entwurf');
  await submit('fixture-approval');await page.locator('.approval-inline').waitFor();
  check('approval is inline and no modal interrupts chat',await page.locator('#approval[open]').count()===0&&await page.locator('.tool-state').innerText()==='Freigabe nötig');
  await page.locator('#prompt').fill('Entwurf während Freigabe');
  await page.locator('.approval-inline').getByRole('button',{name:'Ausführen',exact:true}).click();await done();
  check('approval resumes the same assistant turn',await page.locator('.message.assistant').count()===1&&await page.locator('.app-frame').count()===1);
  check('approval continuation preserves next draft',await page.locator('#prompt').inputValue()==='Entwurf während Freigabe');
  await fresh();await submit('fixture-approval');await page.locator('.approval-inline').getByRole('button',{name:'Ablehnen',exact:true}).click();await done();
  check('declined approval never mounts an executed card',await page.locator('.tool-state').innerText()==='Abgelehnt'&&await page.locator('.app-frame').count()===0);
  await fresh();
  await page.route('**/api/host/chat',route=>route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({error:{code:'fixture_rejected',message:'Nicht angenommen.'}})}),{times:1});
  await submit('Mein nicht angenommener Text');await done();
  check('rejected before admission restores the submitted draft',await page.locator('#prompt').inputValue()==='Mein nicht angenommener Text');
  await fresh();await submit('fixture-hold');await page.locator('.text-part').filter({hasText:'langsam'}).waitFor();await page.locator('#prompt').fill('Entwurf nach Stop');
  await page.locator('#stop').click();await done();check('stop is acknowledged and preserves next draft',await page.locator('.turn-notice').innerText().then(t=>t.includes('Gestoppt'))&&await page.locator('#prompt').inputValue()==='Entwurf nach Stop');
  check('stop does not repeat the chat POST',requests.filter(r=>r.body?.message==='fixture-hold').length===1);
  await fresh();await submit('fixture-after-tool-error');await done();
  check('successful native tool/card remains visible after provider error',await page.locator('.app-frame').count()===1&&await page.locator('.turn-error').isVisible());
  check('private provider diagnostics and tool metadata stay out of visible transcript',!await page.locator('#messages').innerText().then(t=>t.includes('PRIVATE')||t.includes('fixture-secret')));
  await page.locator('#connection').click();await page.locator('#text-only').check();await page.locator('#close-connection').click();check('text-only fallback remains reachable',!await page.locator('.app-frame').isVisible()&&await page.locator('.fallback').innerText().then(t=>t.includes('Reale MCP-Testkarte')));
  for(const viewport of [{width:390,height:844},{width:390,height:420},{width:320,height:568}]){
    await page.setViewportSize(viewport);const bounds=await page.locator('#chat').boundingBox();
    check(`composer visible at ${viewport.width}×${viewport.height}`,bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=viewport.width&&bounds.y+bounds.height<=viewport.height);
    check(`no horizontal overflow at ${viewport.width}px`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  await page.setViewportSize({width:1280,height:960});
  const scroll=page.locator('#scroll-area');await scroll.evaluate(el=>{el.scrollTop=0;el.dispatchEvent(new Event('scroll'));});
  // A read-only screenshot is supplemental; these are explicitly synthetic provider fixtures.
  if(process.env.HOST_UX_SCREENSHOTS){
    const target=process.env.HOST_UX_SCREENSHOTS;
    const cdp=await page.context().newCDPSession(page);await writeFile(join(target,'fixture-error-recovery-desktop.png'),Buffer.from((await cdp.send('Page.captureScreenshot',{format:'png'})).data,'base64'));
  }
  check('no browser page errors',errors.length===0);
  console.log(JSON.stringify({kind:'real_host_MCP_and_browser_with_synthetic_provider_stream',status:'passed',checks,realProviderCalls:0,nativeCustomerWrites:0,errors}));
}catch(error){console.error(JSON.stringify({status:'failed',checks,error:error.message,errors}));process.exitCode=1;}
finally{await browser?.close();if(child){child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)resolve();else{child.once('exit',resolve);setTimeout(()=>{child.kill('SIGKILL');resolve();},3000).unref();}});}await rm(dir,{recursive:true,force:true});}
