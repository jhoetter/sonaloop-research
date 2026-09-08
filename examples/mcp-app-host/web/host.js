import {AppBridge} from '@modelcontextprotocol/ext-apps/app-bridge';
import {JSONRPCMessageSchema} from '@modelcontextprotocol/sdk/types.js';
const $=id=>document.getElementById(id);
const views=[];let status,sessionId,busy=false,approvalQueue=Promise.resolve();
const node=(tag,text,cls)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(cls)item.className=cls;return item;};
async function request(path,value){
  const response=await fetch(path,{method:value===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:value===undefined?{}:{'Content-Type':'application/json','X-Host-CSRF':status.csrf},body:value===undefined?undefined:JSON.stringify(value),signal:AbortSignal.timeout(280000)});
  const data=await response.json();if(!response.ok)throw Object.assign(new Error(data.error?.message || 'Anfrage fehlgeschlagen.'),{code:data.error?.code});return data;
}
function confirmAction(approval){
  const answer=approvalQueue.then(()=>new Promise(resolve=>{
    const dialog=$('approval');$('approval-name').textContent=approval.name;$('approval-args').textContent=JSON.stringify(approval.arguments,null,2);
    const done=value=>{dialog.close();dialog.oncancel=null;$('accept').onclick=null;$('decline').onclick=null;resolve(value);};
    $('accept').onclick=()=>done(true);$('decline').onclick=()=>done(false);dialog.oncancel=event=>{event.preventDefault();done(false);};dialog.showModal();
  }));
  approvalQueue=answer.then(()=>undefined,()=>undefined);
  return answer;
}
const fallback=result=>(result.content || []).filter(item=>item.type==='text').map(item=>item.text).join('\n');
class OpaqueFrameTransport{
  constructor(target){this.target=target;this.listener=event=>{if(event.source!==target || event.origin!=='null')return;const parsed=JSONRPCMessageSchema.safeParse(event.data);if(parsed.success)this.onmessage?.(parsed.data);};}
  async start(){window.addEventListener('message',this.listener);}
  async send(message){this.target.postMessage(message,'*');}
  async close(){window.removeEventListener('message',this.listener);this.onclose?.();}
}
async function renderCall(call,parent){
  const card=node('section',undefined,'card');card.setAttribute('aria-label',`MCP ${call.name}`);
  const head=node('div',undefined,'card-head');head.append(node('strong',call.name),node('span',call.resourceUri || 'Textantwort'));card.append(head);
  const appStatus=node('div',call.uiError || 'MCP App wird geladen …','app-status');const slot=node('div');
  const text=node('div',undefined,'fallback');text.append(node('pre',fallback(call.result)));card.append(appStatus,slot,text);
  const details=node('details');details.append(node('summary','Aufruf und Ressource prüfen'),node('pre',JSON.stringify({arguments:call.arguments,resourceUri:call.resourceUri,sha256:call.resourceSha256},null,2)));card.append(details);parent.append(card);
  const view={bridge:null,dirty:false,pending:false,call,slot,text,appStatus};views.push(view);
  async function mount(){
    await view.bridge?.close();slot.replaceChildren();text.hidden=false;
    if(!call.viewToken || $('text-only').checked){appStatus.textContent=call.uiError || 'Textantwort · kein UI-Renderer aktiv';return;}
    const frame=node('iframe',undefined,'app-frame');frame.title=`${call.name} · MCP App`;frame.setAttribute('sandbox','allow-scripts');frame.referrerPolicy='no-referrer';slot.append(frame);
    const bridge=new AppBridge(null,{name:'Customer MCP App host',version:'0.1.0'},{serverTools:{},logging:{}},{hostContext:{platform:'web',theme:'light',displayMode:'inline',locale:'de-DE'}});view.bridge=bridge;
    bridge.oncalltool=async params=>{
      if(view.pending)return{isError:true,content:[{type:'text',text:'Eine Aktion läuft bereits.'}]};view.pending=true;
      try{
        const input={viewToken:call.viewToken,name:params.name,arguments:params.arguments};let data=await request('/api/host/call',input);
        if(data.approval){if(!await confirmAction(data.approval))return{isError:true,content:[{type:'text',text:'Aktion abgebrochen.'}],structuredContent:{error:{code:'forbidden',message:'Aktion abgebrochen.'}}};data=await request('/api/host/call',{...input,approvalToken:data.approval.token});}
        if(!data.result.isError){text.querySelector('pre').textContent=fallback(data.result);}
        return data.result;
      }catch(error){return{isError:true,content:[{type:'text',text:error.message}],structuredContent:{error:{code:error.code || 'outcome_unknown',message:error.message}}};}finally{view.pending=false;}
    };
    bridge.addEventListener('initialized',async()=>{appStatus.textContent='MCP App verbunden';await bridge.sendToolInput({arguments:call.arguments});await bridge.sendToolResult(call.result);});
    bridge.addEventListener('sizechange',({height})=>{if(Number.isFinite(height))frame.style.height=`${Math.max(200,Math.min(1200,Math.ceil(height)))}px`;});
    // Generic lifecycle telemetry is optional; no component names or business fields.
    bridge.addEventListener('loggingmessage',({data})=>{if(data?.event==='view-rendered'){appStatus.textContent='MCP App dargestellt';text.hidden=true;}if(data?.event==='view-dirty' && typeof data.dirty==='boolean')view.dirty=data.dirty;});
    bridge.onerror=()=>{appStatus.textContent='MCP App nicht verfügbar · Textantwort bleibt sichtbar';text.hidden=false;};
    await bridge.connect(new OpaqueFrameTransport(frame.contentWindow));frame.src=`/app-frame/${encodeURIComponent(call.viewToken)}`;
  }
  view.mount=mount;await mount();
}
function message(role,text){const item=node('article',undefined,`message ${role}`);item.append(node('p',text));$('messages').append(item);return item;}
async function showTurn(turn){sessionId=turn.sessionId;const item=message('assistant',turn.text || 'Tool-Aktion abgeschlossen.');for(const call of turn.calls || [])await renderCall(call,item);if(turn.approval){const accepted=await confirmAction(turn.approval);await showTurn(await request('/api/host/chat',{sessionId,approved:{id:turn.approval.id,accepted}}));}}
function error(error){$('error').hidden=false;$('error').textContent=error.message || 'Anfrage fehlgeschlagen.';}
$('chat').addEventListener('submit',async event=>{event.preventDefault();if(busy || !$('prompt').value.trim())return;busy=true;$('send').disabled=true;$('error').hidden=true;const value=$('prompt').value;message('user',value);try{await showTurn(await request('/api/host/chat',{message:value,sessionId}));$('prompt').value='';}catch(e){error(e);}finally{busy=false;$('send').disabled=!status.providerConfigured;}});
$('prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('chat').requestSubmit();}});
$('call').addEventListener('click',async()=>{if(busy)return;busy=true;$('call').disabled=true;$('error').hidden=true;try{const input={name:$('tool').value,arguments:JSON.parse($('arguments').value)};let data=await request('/api/host/call',input);if(data.approval){if(!await confirmAction(data.approval))return;data=await request('/api/host/call',{...input,approvalToken:data.approval.token});}await renderCall(data.call,message('assistant','Direkter MCP-Aufruf'));}catch(e){error(e);}finally{busy=false;$('call').disabled=false;}});
$('text-only').addEventListener('change',async()=>{if(views.some(view=>view.dirty||view.pending)){$('text-only').checked=!$('text-only').checked;error(new Error('Bitte die laufende Bearbeitung zuerst abschließen.'));return;}for(const view of views)await view.mount();});
window.addEventListener('beforeunload',event=>{if(views.some(view=>view.dirty||view.pending)){event.preventDefault();event.returnValue='';}});
window.addEventListener('pagehide',()=>{for(const view of views)view.bridge?.close();});
try{status=await request('/api/host/status');$('status').textContent=`${status.server?.name || 'MCP'} verbunden · ${status.tools.length} freigegebene Tools`;$('model').textContent=status.model;$('send').disabled=!status.providerConfigured;for(const tool of status.tools.filter(tool=>!tool._meta?.ui?.visibility || tool._meta.ui.visibility.includes('model'))){const option=node('option',tool.title || tool.name);option.value=tool.name;$('tool').append(option);}}catch(e){error(e);$('send').disabled=true;}
