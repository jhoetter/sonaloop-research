import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { build } from 'esbuild';
import { chromium } from 'playwright-core';
import { fixture } from './fixture.mjs';
const repo=new URL('../../../',import.meta.url), origin='http://127.0.0.1:19361';
const manifest=JSON.parse(await readFile(new URL('sonaloop/mcp_server/ui/persona.manifest.json',repo)));
const png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=';
const imageHash=createHash('sha256').update(Buffer.from(png.slice(22),'base64')).digest('hex');
const hostSource=`import{AppBridge,PostMessageTransport}from'@modelcontextprotocol/ext-apps/app-bridge';
const iframe=document.querySelector('iframe');const bridge=window.bridge=new AppBridge(null,{name:'Fixture generic host',version:'1'}, {serverTools:{},logging:{}},{hostContext:{locale:'de',theme:'light'}});
bridge.oncalltool=async params=>(await fetch('/fixture/tool',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(params)})).json();
window.logs=[];bridge.onloggingmessage=p=>logs.push(p);bridge.onsizechange=({height})=>{iframe.style.height=Math.max(200,height)+'px';};
bridge.oninitialized=async()=>{await bridge.sendToolInput({arguments:{persona_id:'persona_fixture'}});await bridge.sendToolResult(await(await fetch('/fixture/result')).json());};
const transport=new PostMessageTransport(iframe.contentWindow,iframe.contentWindow);await bridge.connect(transport);iframe.src='/fixture/app';`;
const hostBundle=(await build({stdin:{contents:hostSource,resolveDir:new URL('..',import.meta.url).pathname},bundle:true,format:'esm',write:false,target:'es2022'})).outputFiles[0].text;
async function setup(mode){
 let value=fixture(),revision=1,fail,operationStatus='outcome_unknown';const calls=[],errors=[];
 const browser=await chromium.launch({executablePath:process.env.RESEARCH_BROWSER_EXECUTABLE||'/home/sonaloop/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1100,height:1000}});page.setDefaultTimeout(5000);page.on('pageerror',error=>errors.push(error.message));
 const result=()=>({content:[{type:'text',text:value.fields.display_name}],structuredContent:structuredClone(value),...value.avatar.sha256?{_meta:{'sonaloop/avatarDataUri':png}}:{}});
 function mutate(action,args){
   calls.push({action,args});
   if(fail){const code=fail;fail=undefined;return{error:{code,message:'Synthetic '+code}};}
   if(args.expected_version!==value.version)return{error:{code:'conflict',message:'Changed in another view'}};
   if(action==='update')value={...value,version:'version-'+ ++revision,fields:{...value.fields,...args.changes},avatar:{...value.avatar,state:value.avatar.sha256?'stale':'missing'}};
   else value={...value,version:'version-'+ ++revision,avatar:{state:'ready',sha256:imageHash,generated_at:'2026-09-08',profile_version:'native-profile'}};
   return result();
 }
 await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());if(url.origin!==origin)return route.abort();
   const json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:mode==='product'?`<!doctype html><html lang="de"><head><meta charset="utf-8"><link rel="stylesheet" href="/web-assets/${manifest.product.style.file}"></head><body style="font:14px system-ui"><section data-persona-surface-section><div data-persona-view><script type="application/json">${JSON.stringify({persona_id:'persona_fixture',locale:'de',csrf_token:'fixture-only-csrf'})}</script></div><p data-persona-surface-fallback>Server fallback</p></section><script src="/web-assets/${manifest.product.script.file}"></script></body></html>`:`<!doctype html><html lang="de"><body><iframe title="Persona" sandbox="allow-scripts" style="width:100%;border:0"></iframe><script type="module">${hostBundle}</script></body></html>`});
   if(url.pathname==='/fixture/app')return route.fulfill({contentType:'text/html',headers:{'Content-Security-Policy':"sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'"},body:await readFile(new URL('sonaloop/mcp_server/ui/persona.html',repo))});
   if(url.pathname==='/fixture/result')return json(result());
   if(url.pathname==='/fixture/tool'){
     const{name,arguments:args}=request.postDataJSON();
     if(name==='get_persona_surface')return json(result());
     if(name==='get_persona_surface_operation')return json({content:[{type:'text',text:operationStatus}],structuredContent:{operation_id:args.operation_id,status:operationStatus}});
     const answer=mutate(name==='update_persona_surface'?'update':'generate_avatar',args);
     return json(answer.error?{isError:true,content:[{type:'text',text:answer.error.message}],structuredContent:{error:answer.error}}:answer);
   }
   if(url.pathname.startsWith('/web-assets/'))return route.fulfill({contentType:url.pathname.endsWith('.css')?'text/css':'text/javascript',body:await readFile(new URL('sonaloop/web/assets/'+url.pathname.slice(12),repo))});
   if(url.pathname.endsWith('/avatar'))return route.fulfill({contentType:'image/png',body:Buffer.from(png.slice(22),'base64')});
   if(url.pathname.endsWith('/surface/actions'))return json(mutate(request.postDataJSON().action,request.postDataJSON()));
   if(url.pathname.endsWith('/surface'))return json(result());
   if(url.pathname.startsWith('/api/personas/surface-operations/'))return json({structuredContent:{operation_id:url.pathname.split('/').at(-1),status:operationStatus}});
   return route.fulfill({status:404,body:'fixture route missing'});
 });
 await page.goto(origin);const frame=mode==='product'?page:page.frameLocator('iframe');await frame.locator('[data-field=display_name]').waitFor();
 return{browser,page,frame,calls,errors,get value(){return value;},fail:code=>{fail=code;},replace:next=>{value=next;},terminal:()=>{operationStatus='succeeded';},external:()=>{value={...value,version:'version-'+ ++revision,fields:{...value.fields,role_title:'Changed elsewhere'}};},result};
}
for(const mode of ['product','mcp'])test(`built ${mode} adapter exercises shared direct editing, avatar and recovery`,{timeout:60000},async()=>{
 const s=await setup(mode);const f=s.frame;try{
  assert.equal(await f.locator('script').filter({hasText:'inert()'}).count(),0,'profile strings never execute as markup');
  await f.locator('[data-field=display_name]').click();await f.getByRole('textbox',{name:'Name',exact:true}).fill('Mira Changed');await f.getByRole('textbox',{name:'Name',exact:true}).press('Escape');assert.equal(s.calls.length,0);
  await f.locator('[data-field=display_name]').click();await f.getByRole('textbox',{name:'Name',exact:true}).fill('Mira Changed');await f.getByRole('textbox',{name:'Name',exact:true}).press('Enter');await f.locator('[data-field=display_name]').waitFor();assert.equal(s.value.fields.display_name,'Mira Changed');assert.equal(s.value.persona_id,'persona_fixture');assert.deepEqual(s.calls[0].args.changes,{display_name:'Mira Changed'});
  if(mode==='product')assert.equal(s.calls[0].args.csrf_token,'fixture-only-csrf');else assert.equal(s.calls[0].args.persona_id,'persona_fixture');
  await f.locator('[data-action=avatar]').click();await f.getByRole('textbox',{name:'Wie soll das Gesicht aussehen?'}).fill('Changed but cancelled');await f.getByRole('button',{name:'Abbrechen',exact:true}).click();assert.equal(s.calls.length,1);
  await f.locator('[data-action=avatar]').click();await f.getByRole('textbox',{name:'Wie soll das Gesicht aussehen?'}).fill('An explicitly fictional adult face');await f.getByRole('button',{name:'Generieren',exact:true}).click();await f.locator('.sl-persona-view__avatar img').waitFor();assert.equal(await f.locator('img').evaluate(img=>img.naturalWidth),1);assert.equal(s.value.fields.portrait_description,fixture().fields.portrait_description);
  s.fail('conflict');await f.locator('[data-field=location]').click();await f.getByRole('textbox',{name:'Ort',exact:true}).fill('Unconfirmed city');await f.getByRole('textbox',{name:'Ort',exact:true}).press('Enter');await f.getByRole('alert').waitFor();assert.equal(await f.getByRole('textbox',{name:'Ort',exact:true}).inputValue(),'Unconfirmed city');assert.ok(await f.locator('[data-action=save-field]').isDisabled());assert.ok(await f.locator('img').isVisible());
  await f.getByRole('button',{name:'Neu laden · Eingabe verwerfen',exact:true}).click();await f.locator('[data-field=location]').waitFor();assert.equal(s.value.fields.location,'Berlin');
  s.fail('outcome_unknown');await f.locator('[data-field=role_title]').click();await f.getByRole('textbox',{name:'Rolle',exact:true}).fill('Uncertain role');await f.getByRole('textbox',{name:'Rolle',exact:true}).press('Enter');await f.getByRole('button',{name:'Status prüfen',exact:true}).waitFor();assert.ok(await f.locator('[data-action=save-field]').isDisabled());const writes=s.calls.length;
  await f.getByRole('button',{name:'Status prüfen',exact:true}).click();await f.locator('.sl-persona-view[aria-busy=false]').waitFor();assert.equal(s.calls.length,writes);s.terminal();await f.getByRole('button',{name:'Status prüfen',exact:true}).click();await f.locator('[data-field=role_title]').waitFor();assert.equal(s.calls.length,writes);
  await s.page.setViewportSize({width:390,height:844});await f.locator('[data-field=display_name]').click();await f.getByRole('textbox',{name:'Name',exact:true}).fill('Mobile editor');assert.ok(await f.locator('body').evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.getByRole('textbox',{name:'Name',exact:true}).press('Escape');
  if(mode==='mcp'){assert.ok(await s.page.evaluate(()=>logs.some(log=>log.data.event==='view-rendered')));assert.ok(await s.page.evaluate(()=>logs.some(log=>log.data.event==='view-dirty'&&log.data.dirty)));await s.page.evaluate(()=>bridge.setHostContext({locale:'en',theme:'dark'}));await f.getByRole('button',{name:'Edit: Name',exact:true}).waitFor();assert.equal(await f.locator('html').getAttribute('data-theme'),'dark');}
  assert.deepEqual(s.errors,[]);
 }catch(error){console.error('FIXTURE DOM',mode,await f.locator('body').innerText());throw error;}finally{await s.browser.close();}
});
test('external canonical updates preserve dirty input and capabilities govern readonly presentation',{timeout:30000},async()=>{
 const s=await setup('mcp'),f=s.frame;try{
  await f.locator('[data-field=role_title]').click();await f.getByRole('textbox',{name:'Rolle',exact:true}).fill('Keep this unsaved role');s.external();
  await s.page.evaluate(result=>bridge.sendToolResult(result),s.result());await f.getByText('Das Profil wurde inzwischen geändert.',{exact:false}).waitFor();
  assert.equal(await f.getByRole('textbox',{name:'Rolle',exact:true}).inputValue(),'Keep this unsaved role');assert.ok(await f.locator('[data-action=save-field]').isDisabled());assert.equal(s.calls.length,0);
  await f.getByRole('button',{name:'Neu laden · Eingabe verwerfen',exact:true}).click();await f.locator('[data-field=role_title]').waitFor();
  const readonly=structuredClone(s.value);readonly.capabilities={edit:[],generate_avatar:false,reasons:['Imported field format remains readable']};s.replace(readonly);
  await s.page.evaluate(result=>bridge.sendToolResult(result),s.result());await f.locator('[data-field]').first().waitFor({state:'detached'});assert.ok(await f.locator('[data-action=avatar]').isDisabled());assert.ok(await f.getByText('Changed elsewhere',{exact:true}).isVisible());
  await f.getByText('Details',{exact:true}).click();assert.ok(await f.getByText('Imported field format remains readable',{exact:true}).isVisible());assert.deepEqual(s.errors,[]);
 }finally{await s.browser.close();}
});
test('product instances are independent and detached drawers release dirty state',{timeout:30000},async()=>{
 const s=await setup('product');try{
  await s.page.evaluate(()=>{const root=document.createElement('div');root.dataset.personaView='';const seed=document.createElement('script');seed.type='application/json';seed.textContent=JSON.stringify({persona_id:'persona_fixture',locale:'en',csrf_token:'fixture-only-csrf'});root.append(seed);document.body.append(root);document.dispatchEvent(new CustomEvent('spa:load'));});
  await s.page.locator('.sl-persona-view').nth(1).waitFor();assert.equal(await s.page.locator('.sl-persona-view').count(),2);
  const first=s.page.locator('.sl-persona-view').nth(0),second=s.page.locator('.sl-persona-view').nth(1);
  await first.locator('[data-field=display_name]').click();await second.locator('[data-field=display_name]').click();assert.equal(await s.page.locator('input').count(),2);
  const ids=await s.page.locator('input').evaluateAll(inputs=>inputs.map(input=>input.id));assert.equal(new Set(ids).size,2);
  let questions=0;s.page.on('dialog',async dialog=>{questions++;await dialog.dismiss();});
  assert.equal(await s.page.evaluate(()=>document.dispatchEvent(new CustomEvent('sonaloop:before-navigation',{cancelable:true}))),false);assert.equal(questions,1);
  await s.page.evaluate(()=>document.dispatchEvent(new CustomEvent('sonaloop:drawer-closed',{detail:{root:document.body}})));
  assert.equal(await s.page.locator('.sl-persona-view').count(),0);
  await s.page.evaluate(()=>document.dispatchEvent(new CustomEvent('spa:load')));
  assert.equal(await s.page.evaluate(()=>document.dispatchEvent(new CustomEvent('sonaloop:before-navigation',{cancelable:true}))),true);assert.equal(questions,1);assert.deepEqual(s.errors,[]);
 }finally{await s.browser.close();}
});
test('authoritative avatar removal clears prior pixels; unknown image status is reachable inside its dialog',{timeout:30000},async()=>{
 const s=await setup('mcp'),f=s.frame;try{
  await f.locator('[data-action=avatar]').click();await f.getByRole('button',{name:'Generieren',exact:true}).click();await f.locator('img').waitFor();
  const removed=structuredClone(s.value);removed.version='version-avatar-removed';removed.avatar=fixture().avatar;s.replace(removed);
  await s.page.evaluate(result=>bridge.sendToolResult(result),s.result());await f.locator('img').waitFor({state:'detached'});assert.ok(await f.getByRole('button',{name:'Gesicht erstellen',exact:true}).isVisible());
  s.fail('outcome_unknown');await f.locator('[data-action=avatar]').click();await f.getByRole('button',{name:'Generieren',exact:true}).click();
  const dialog=f.getByRole('dialog');await dialog.getByRole('button',{name:'Status prüfen',exact:true}).waitFor();assert.ok(await dialog.getByRole('button',{name:'Generieren',exact:true}).isDisabled());
  const writes=s.calls.length;s.terminal();await dialog.getByRole('button',{name:'Status prüfen',exact:true}).click();await dialog.waitFor({state:'detached'});assert.equal(s.calls.length,writes);assert.equal(await f.locator('img').count(),0);assert.deepEqual(s.errors,[]);
 }finally{await s.browser.close();}
});
for(const mode of ['product','mcp'])test(`${mode} keeps unresolved operations dirty after the editor or image prompt closes`,{timeout:30000},async()=>{
 const s=await setup(mode),f=s.frame;try{
  let questions=0;
  if(mode==='product')s.page.on('dialog',async dialog=>{questions++;await dialog.dismiss();});
  async function assertDirty(expected){
    if(mode==='mcp'){
      await s.page.waitForFunction(expected=>logs.filter(log=>log.data.event==='view-dirty').at(-1)?.data.dirty===expected,expected);
      assert.equal(await s.page.evaluate(()=>logs.filter(log=>log.data.event==='view-dirty').at(-1).data.dirty),expected);
    }else assert.equal(await s.page.evaluate(()=>document.dispatchEvent(new CustomEvent('sonaloop:before-navigation',{cancelable:true}))),!expected);
  }
  s.fail('outcome_unknown');await f.locator('[data-field=display_name]').click();await f.getByRole('textbox',{name:'Name',exact:true}).fill('Uncertain name');await f.getByRole('textbox',{name:'Name',exact:true}).press('Enter');await f.getByRole('button',{name:'Status prüfen',exact:true}).waitFor();
  await f.getByRole('textbox',{name:'Name',exact:true}).press('Escape');assert.equal(await f.getByRole('textbox',{name:'Name',exact:true}).count(),0);await assertDirty(true);
  const writes=s.calls.length;s.terminal();await f.getByRole('button',{name:'Status prüfen',exact:true}).click();await f.locator('[data-field=display_name]:enabled').waitFor();await assertDirty(false);assert.equal(s.calls.length,writes);
  s.fail('outcome_unknown');await f.locator('[data-action=avatar]').click();await f.getByRole('button',{name:'Generieren',exact:true}).click();const dialog=f.getByRole('dialog');await dialog.getByRole('button',{name:'Status prüfen',exact:true}).waitFor();await dialog.getByRole('button',{name:'Abbrechen',exact:true}).click();await dialog.waitFor({state:'detached'});await assertDirty(true);
  const imageWrites=s.calls.length;await f.getByRole('button',{name:'Status prüfen',exact:true}).click();await f.locator('[data-action=avatar]:enabled').waitFor();await assertDirty(false);assert.equal(s.calls.length,imageWrites);if(mode==='product')assert.equal(questions,2);assert.deepEqual(s.errors,[]);
 }finally{await s.browser.close();}
});
