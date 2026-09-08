import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';
import {chromium} from 'playwright-core';
import {projectRecordPreview,validatePreview,validateSurface,PREVIEW_SCHEMA} from '../../../sonaloop/web/assets/persona-view/persona-contract.js';
import {fixture} from './fixture.mjs';

const input=()=>({description:'An explicitly synthetic adult persona for a browser fixture.',operation_id:'preview-fixture-intent',
  profile:{display_name:'Mira <script>window.injected=true</script>',demographics:{age:'35–44',location:'Berlin'},role:{title:'Design researcher'},
    identity_traits:{avatar_profile:'A fictional adult with short hair'},goals:['Understand real needs'],pain_points:['Too many assumptions']}});
test('record preview projects only bounded display fields, never native identity or capabilities',()=>{
  const args=input(),before=structuredClone(args);args.profile.capabilities={edit:['anything']};args.profile.avatar={path:'/private'};
  const preview=projectRecordPreview(args,'record_persona_surface');
  assert.deepEqual(Object.keys(preview).sort(),['fields','schema_version']);assert.equal(preview.schema_version,PREVIEW_SCHEMA);
  assert.equal(preview.fields.display_name,before.profile.display_name);assert.equal(preview.fields.portrait_description,before.profile.identity_traits.avatar_profile);
  assert.equal(validatePreview(preview),preview);assert.throws(()=>validateSurface(preview));
  args.profile.goals.push('Later modification');assert.deepEqual(preview.fields.goals,before.profile.goals);
  assert.equal(projectRecordPreview(input(),'get_persona_surface'),null);assert.equal(projectRecordPreview({persona_id:'real'}),null);
  assert.deepEqual(projectRecordPreview(input()),projectRecordPreview(input(),'record_persona_surface'));
});
test('unsafe, incomplete and misleading preview shapes fail without coercing native data',()=>{
  const invalid=[args=>({...args,extra:true}),args=>({...args,operation_id:''}),args=>({...args,description:' '}),
    args=>({...args,profile:{...args.profile,demographics:[]}}),args=>({...args,profile:{...args.profile,display_name:'x'.repeat(121)}}),
    args=>({...args,profile:{...args.profile,goals:['x'.repeat(181)]}}),args=>({...args,profile:{...args.profile,pain_points:[]}}),
    args=>({...args,profile:{...args.profile,demographics:{age:true}}}),args=>({...args,profile:{...args.profile,identity_traits:{avatar_profile:'x'.repeat(501)}}})];
  for(const change of invalid)assert.throws(()=>projectRecordPreview(change(input()),'record_persona_surface'),{code:'invalid_preview'});
  const preview=projectRecordPreview(input());
  for(const key of ['persona_id','slug','version','avatar','capabilities'])assert.throws(()=>validatePreview({...preview,[key]:'invented'}),{code:'invalid_preview'});
});

const repo=new URL('../../../',import.meta.url),origin='http://127.0.0.1:19367';
const hostSource=`import{AppBridge,PostMessageTransport}from'@modelcontextprotocol/ext-apps/app-bridge';
const frame=document.querySelector('iframe'),seed=await(await fetch('/fixture/input')).json();
const context={locale:'de',theme:'light',...(seed.toolName?{toolInfo:{tool:{name:seed.toolName,inputSchema:{type:'object'}}}}:{})};
const bridge=window.bridge=new AppBridge(null,{name:'Input-only fixture host',version:'1'},{serverTools:{},logging:{}},{hostContext:context});
window.logs=[];bridge.onloggingmessage=p=>logs.push(p);bridge.onsizechange=({height})=>{frame.style.height=Math.max(200,height)+'px';};
bridge.oncalltool=async params=>(await fetch('/fixture/tool',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(params)})).json();
bridge.oninitialized=async()=>{if(seed.cancelBeforeInput)await bridge.sendToolCancelled({reason:'user declined'});await bridge.sendToolInput({arguments:seed.args});};
await bridge.connect(new PostMessageTransport(frame.contentWindow,frame.contentWindow));frame.src='/fixture/app';`;
const hostBundle=(await build({stdin:{contents:hostSource,resolveDir:new URL('..',import.meta.url).pathname},bundle:true,format:'esm',write:false,target:'es2022'})).outputFiles[0].text;
async function setup({toolName='record_persona_surface',args=input(),cancelBeforeInput=false,failRead=false}={}){
  const browser=await chromium.launch({executablePath:process.env.RESEARCH_BROWSER_EXECUTABLE||'/home/sonaloop/.local/share/sonaloop-v4/m006a-capture-browser/chromium_headless_shell-1193/chrome-linux/headless_shell',headless:true});
  const page=await browser.newPage({viewport:{width:1050,height:900}}),calls=[],errors=[];page.setDefaultTimeout(7000);
  page.on('pageerror',error=>errors.push(error.message));let value={...fixture(),fields:{...fixture().fields,display_name:'Mira confirmed'}};
  const result=()=>({content:[{type:'text',text:value.fields.display_name}],structuredContent:structuredClone(value)});
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
    if(url.origin!==origin)return route.abort();
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:`<!doctype html><html><body><iframe title="Persona" sandbox="allow-scripts" style="width:100%;border:0"></iframe><script type="module">${hostBundle}</script></body></html>`});
    if(url.pathname==='/fixture/input')return json({toolName,args,cancelBeforeInput});
    if(url.pathname==='/fixture/app')return route.fulfill({contentType:'text/html',headers:{'Content-Security-Policy':"sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'"},body:await readFile(new URL('sonaloop/mcp_server/ui/persona.html',repo))});
    if(url.pathname==='/fixture/tool'){
      const call=route.request().postDataJSON();calls.push(call);
      if(call.name==='get_persona_surface'&&failRead)return json({isError:true,structuredContent:{error:{code:'request_failed',message:'Synthetic read interruption'}},content:[]});
      if(call.name==='update_persona_surface')value={...value,version:'version-2',fields:{...value.fields,...call.arguments.changes}};
      return json(result());
    }
    return route.fulfill({status:404,body:'Unknown fixture request'});
  });
  await page.goto(origin);
  return{browser,page,frame:page.frameLocator('iframe'),calls,errors,result,restoreRead:()=>{failRead=false;}};
}
test('built customer App previews without tools and promotes the same card only on a real surface result',{timeout:30000},async()=>{
  const s=await setup(),f=s.frame;
  try{
    await f.locator('.sl-persona-view[data-mode=preview]').waitFor();
    const card=await f.locator('.sl-persona-view').elementHandle();
    assert.equal(await f.locator('h2').innerText(),input().profile.display_name);
    assert.ok(await f.getByText('Ungespeicherter Entwurf',{exact:true}).isVisible());assert.equal(s.calls.length,0);
    assert.equal(await f.locator('button,input,textarea,img,[data-field],[data-action]').count(),0);
    assert.equal(await f.locator('body').evaluate(()=>window.injected),undefined);
    const changed=input();changed.profile.display_name='Late proposal';await s.page.evaluate(args=>bridge.sendToolInput({arguments:args}),changed);
    assert.equal(await f.locator('h2').innerText(),input().profile.display_name);
    await s.page.evaluate(()=>bridge.sendToolCancelled({reason:'user declined'}));
    await f.getByText('Vorschau abgebrochen',{exact:true}).waitFor();assert.equal(s.calls.length,0);
    await s.page.evaluate(()=>bridge.sendToolResult({isError:true,content:[{type:'text',text:'Private raw diagnostic must not appear'}],structuredContent:{error:{code:'outcome_unknown',message:'Private raw diagnostic must not appear'}}}));
    await f.getByText('Speicherung nicht bestätigt',{exact:true}).waitFor();assert.equal(s.calls.length,0);
    assert.ok(!(await f.locator('body').innerText()).includes('Private raw diagnostic'));
    await s.page.evaluate(result=>bridge.sendToolResult(result),s.result());
    await f.locator('.sl-persona-view[data-mode=persisted] [data-field=display_name]').waitFor();
    assert.equal(await card.evaluate(el=>el===document.querySelector('.sl-persona-view')),true);
    assert.equal(await f.locator('h2').innerText().then(text=>text.includes('Mira confirmed')),true);
    assert.deepEqual(s.calls.map(call=>call.name),['get_persona_surface']);
    assert.equal(s.calls[0].arguments.persona_id,'persona_fixture');
    await s.page.evaluate(args=>bridge.sendToolInput({arguments:args}),input());
    assert.equal(await f.locator('[data-mode=preview]').count(),0);
    await f.locator('[data-field=display_name]').click();await f.getByRole('textbox',{name:'Name',exact:true}).fill('Edited after creation');
    await f.getByRole('textbox',{name:'Name',exact:true}).press('Enter');await f.locator('[data-field=display_name]').waitFor();
    assert.equal(s.calls[1].name,'update_persona_surface');assert.equal(s.calls[1].arguments.expected_version,'version-1');
    assert.deepEqual(s.calls[1].arguments.changes,{display_name:'Edited after creation'});
    assert.equal(s.calls.some(call=>call.name==='record_persona_surface'||call.name==='generate_persona_surface_avatar'),false);
    assert.equal(await s.page.evaluate(()=>logs.some(log=>log.data.event==='view-rendered'&&log.data.mode==='preview'&&!log.data.persona_id&&!log.data.version)),true);
    assert.deepEqual(s.errors,[]);
  }finally{await s.browser.close();}
});
test('a confirmed creation remains saved and recoverable when the follow-up read fails',{timeout:20000},async()=>{
  const s=await setup({failRead:true}),f=s.frame;
  try{
    await f.locator('[data-mode=preview]').waitFor();await s.page.evaluate(result=>bridge.sendToolResult(result),s.result());
    await f.locator('[data-mode=persisted]').waitFor();await f.getByRole('button',{name:'Status prüfen',exact:true}).waitFor();
    assert.equal(await f.locator('[data-mode=preview]').count(),0);assert.ok((await f.locator('h2').innerText()).includes('Mira confirmed'));
    assert.equal(await f.getByText('Speicherung nicht bestätigt',{exact:true}).count(),0);
    assert.deepEqual(s.calls.map(call=>call.name),['get_persona_surface']);
    s.restoreRead();await f.getByRole('button',{name:'Status prüfen',exact:true}).click();await f.locator('[data-field=display_name]:enabled').waitFor();
    assert.deepEqual(s.calls.map(call=>call.name),['get_persona_surface','get_persona_surface']);assert.deepEqual(s.errors,[]);
  }finally{await s.browser.close();}
});
test('cancellation received before input keeps the later preview cancelled and passive',{timeout:20000},async()=>{
  const s=await setup({cancelBeforeInput:true});
  try{await s.frame.getByText('Vorschau abgebrochen',{exact:true}).waitFor();assert.equal(s.calls.length,0);assert.equal(await s.frame.locator('button,input,textarea').count(),0);assert.deepEqual(s.errors,[]);}
  finally{await s.browser.close();}
});
test('built App supports optional toolInfo, mobile preview and a safe invalid-input fallback',{timeout:30000},async()=>{
  for(const options of [{toolName:null},{args:{...input(),profile:{}}}]){
    const s=await setup(options);
    try{
      if(options.toolName===null){
        await s.frame.locator('[data-mode=preview]').waitFor();await s.page.setViewportSize({width:390,height:844});
        assert.equal(await s.frame.locator('body').evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
        await s.page.evaluate(()=>bridge.setHostContext({locale:'en',theme:'dark'}));await s.frame.getByText('Unsaved draft',{exact:true}).waitFor();
      }else{await s.frame.getByText('Für diese Argumente ist keine Persona-Vorschau verfügbar.',{exact:false}).waitFor();assert.equal(await s.frame.locator('.sl-persona-view').count(),0);}
      assert.equal(s.calls.length,0);assert.deepEqual(s.errors,[]);
    }finally{await s.browser.close();}
  }
});
