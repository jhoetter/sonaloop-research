import {$,node,icon,toolLabel} from './dom.js';
import {createAppViews} from './app-view.js';
import {createConversation} from './conversation.js';
import {readTurnStream} from './stream.js';
import {TURN_SCHEMA_VERSION} from '../stream-contract.mjs';
let status,sessionId,active=null,directBusy=false,draftRevision=0,approvalQueue=Promise.resolve(),conversation,conversationGeneration=0;
const current=state=>state.generation===conversationGeneration;
const requestHeaders=()=>({'Content-Type':'application/json','X-Host-CSRF':status?.csrf||''});
async function request(path,value){
  const response=await fetch(path,{method:value===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:value===undefined?{}:requestHeaders(),body:value===undefined?undefined:JSON.stringify(value),signal:AbortSignal.timeout(280000)});
  let data;try{data=await response.json();}catch{throw new Error('Verbindung unterbrochen. Der Aktionsstatus ist möglicherweise noch offen.');}
  if(!response.ok)throw Object.assign(new Error(data.error?.message||'Anfrage fehlgeschlagen.'),{code:data.error?.code});return data;
}
function showError(error){$('error').hidden=false;$('error').textContent=error.message||'Verbindung fehlgeschlagen.';}
function confirmAction(approval){
  const answer=approvalQueue.then(()=>new Promise(resolve=>{
    const dialog=$('approval');$('approval-name').textContent=toolLabel(status,approval.name);$('approval-args').textContent=JSON.stringify(approval.arguments,null,2);
    const done=value=>{dialog.close();dialog.oncancel=null;$('accept').onclick=null;$('decline').onclick=null;resolve(value);};
    $('accept').onclick=()=>done(true);$('decline').onclick=()=>done(false);dialog.oncancel=event=>{event.preventDefault();done(false);};dialog.showModal();$('decline').focus();
  }));approvalQueue=answer.then(()=>undefined,()=>undefined);return answer;
}
const apps=createAppViews({request,confirmAction,onChange:()=>conversation?.changed()});
function resize(){const prompt=$('prompt');prompt.style.height='auto';prompt.style.height=`${Math.min(190,prompt.scrollHeight)}px`;controls();}
function controls(){
  const waiting=!!active||directBusy;$('send').hidden=!!active;$('stop').hidden=!active;
  $('send').disabled=waiting||!status?.providerConfigured||!$('prompt').value.trim();
  $('stop').disabled=!!active?.stopRequested;$('new-chat').disabled=waiting;
  $('draft-hint').textContent=waiting&&$('prompt').value?'Entwurf für danach':'';$('call').disabled=waiting;
}
function serial(state,work){const next=(state.updates||Promise.resolve()).then(work);state.updates=next.catch(()=>{});return next;}
function applyEvent(state,event){return serial(state,()=>applyEventNow(state,event));}
async function applyEventNow(state,event){
  if(!current(state))return;
  if(state.turnId&&event.turnId!==state.turnId||state.sessionId&&event.sessionId!==state.sessionId)throw new Error('Die Antwort gehört zu einem anderen Chat.');
  if(event.seq<=state.seq)return;state.seq=event.seq;state.turnId=event.turnId;state.sessionId=event.sessionId;sessionId=event.sessionId;
  if(event.type==='turn.started'){state.status='running';$('announcer').textContent='Der Agent antwortet.';}
  else if(event.type==='text.delta')conversation.text(state,event.partId,event.delta);
  else if(event.type==='tool.state')await conversation.tool(state,event);
  else if(event.type==='turn.paused'){state.status='waiting_approval';state.progress.hidden=true;$('announcer').textContent='Eine Aktion braucht deine Freigabe.';}
  else if(event.type==='turn.finished'){state.terminal=true;conversation.finish(state,event.status,event.error);if(active===state)active=null;}
  controls();
}
async function snapshot(state){
  if(!current(state))return;
  const path=state.turnId?`/api/host/chat/turns/${encodeURIComponent(state.turnId)}`:`/api/host/chat/requests/${encodeURIComponent(state.clientTurnId)}`;
  const value=await request(path);
  if(!current(state))return;
  if(value.schemaVersion!==TURN_SCHEMA_VERSION||state.turnId&&value.turnId!==state.turnId||state.sessionId&&value.sessionId!==state.sessionId||!state.turnId&&value.clientTurnId!==state.clientTurnId)throw new Error('Der gespeicherte Status passt nicht zur Anfrage.');
  const result=await serial(state,async()=>{
  if(!current(state)||value.seq<state.seq)return value;
  state.turnId=value.turnId;state.sessionId=value.sessionId;sessionId=value.sessionId;
  conversation.clearRecovery(state);if(state.recoveryError){if($('error').textContent===state.recoveryError)$('error').hidden=true;state.recoveryError=null;}
  for(const part of value.parts){if(part.kind==='text')conversation.text(state,part.id,part.text,false);else if(part.kind==='tool')await conversation.tool(state,{...part,partId:part.id,confirmedWaiting:value.status==='waiting_approval'});}
  state.seq=Math.max(state.seq,value.seq);state.status=value.status;
  if(['completed','stopped','failed'].includes(value.status)){state.terminal=true;conversation.finish(state,value.status,value.error);if(active===state)active=null;}
  else if(value.status==='waiting_approval')state.progress.hidden=true;
  else{state.progress.hidden=false;state.progressText.textContent=value.toolInFlight?'Laufende Aktion wird abgeschlossen …':'Aktionsstatus wird geprüft …';}
  controls();return value;
  });
  if(current(state)&&state.stopRequested&&!state.stopSent&&!state.terminal){state.stopSent=true;try{await request('/api/host/chat/stop',{sessionId:state.sessionId,turnId:state.turnId});}catch(error){state.stopSent=false;throw error;}}
  return result;
}
async function recover(state){
  if(!current(state)||state.recovering)return;state.recovering=true;
  try{
    for(let attempt=0;attempt<100&&current(state);attempt++){
      try{await snapshot(state);}catch(error){if(!(error.code==='turn_missing'&&!state.turnId&&attempt<7))throw error;}
      if(state.terminal||state.status==='waiting_approval'&&!state.stopRequested)break;
      await new Promise(resolve=>setTimeout(resolve,attempt<5?1000:3000));
    }
    if(current(state)&&!state.terminal&&state.status!=='waiting_approval')conversation.note(state,'Der Aktionsstatus ist noch offen. Es wurde nichts erneut ausgeführt.',()=>recover(state));
  }catch(error){if(!current(state))return;conversation.note(state,'Status derzeit nicht erreichbar. Bereits ausgeführte Aktionen werden nicht wiederholt.',()=>recover(state));state.recoveryError=error.message;showError(error);}
  finally{state.recovering=false;controls();}
}
async function stream(state,input){
  state.controller=new AbortController();state.terminal=false;state.progress.hidden=false;
  try{
    const response=await fetch('/api/host/chat',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{...requestHeaders(),Accept:'text/event-stream'},body:JSON.stringify(input),signal:AbortSignal.any([state.controller.signal,AbortSignal.timeout(660000)])});
    await readTurnStream(response,event=>applyEvent(state,event));
    if(!state.terminal&&state.status!=='waiting_approval')throw new Error('Die Verbindung wurde vor Abschluss unterbrochen.');
  }catch(error){
    if(!current(state))return;
    if(state.turnId||!error.notAccepted){conversation.note(state,'Verbindung unterbrochen. Der gespeicherte Aktionsstatus wird geprüft.',()=>recover(state));await recover(state);}
    else{
      conversation.finish(state,'failed',{message:error.notAccepted?error.message:'Verbindung unterbrochen. Der Ausgang ist unklar; die Anfrage wurde nicht erneut gesendet.'});
      if(error.notAccepted&&state.draftRevision===draftRevision&&!$('prompt').value){$('prompt').value=state.sentText;resize();}
      if(active===state)active=null;
    }
  }finally{controls();}
}
async function approve(state,approval,accepted){
  if(state.streamingApproval)return;state.streamingApproval=true;active=state;state.status='running';controls();
  try{await stream(state,{sessionId:state.sessionId,turnId:state.turnId,approved:{id:approval.id,accepted}});}
  finally{state.streamingApproval=false;}
}
conversation=createConversation({getStatus:()=>status,apps,approve,recover});
$('chat').addEventListener('submit',async event=>{
  event.preventDefault();const prompt=$('prompt'),message=prompt.value.trim();if(active||directBusy||!status?.providerConfigured||!message)return;
  $('error').hidden=true;conversation.user(message);active=conversation.turn();
  Object.assign(active,{seq:-1,generation:conversationGeneration,sentText:prompt.value,draftRevision,clientTurnId:crypto.randomUUID()});
  prompt.value='';resize();prompt.focus();controls();await stream(active,{message,sessionId,clientTurnId:active.clientTurnId});
});
$('prompt').addEventListener('input',()=>{draftRevision++;resize();});
$('prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!active&&!directBusy)$('chat').requestSubmit();}});
$('stop').onclick=async()=>{
  const state=active;if(!state||state.stopRequested)return;state.stopRequested=true;controls();state.progress.hidden=false;state.progressText.textContent='Stop wird angefordert …';
  if(!state.turnId){state.controller?.abort();return;}
  try{
    state.stopSent=true;const result=await request('/api/host/chat/stop',{sessionId:state.sessionId,turnId:state.turnId});
    state.progressText.textContent=result.toolInFlight?'Laufende Aktion wird abgeschlossen, danach gestoppt …':'Antwort wird gestoppt …';
    await recover(state);
  }catch(error){state.stopRequested=false;state.stopSent=false;showError(error);controls();}
};
$('new-chat').onclick=async()=>{
  if(active||directBusy)return;if(apps.hasWork()){showError(new Error('Bitte die Bearbeitung in der Ansicht zuerst speichern oder abbrechen.'));return;}
  conversationGeneration++;await apps.clear();conversation.clear();sessionId=undefined;$('error').hidden=true;$('prompt').focus();controls();
};
$('connection').onclick=()=>{$('connection-dialog').showModal();};$('close-connection').onclick=()=>{$('connection-dialog').close();};
$('call').onclick=async()=>{
  if(active||directBusy)return;directBusy=true;controls();$('error').hidden=true;let state;
  try{
    const input={name:$('tool').value,arguments:JSON.parse($('arguments').value)};$('connection-dialog').close();$('welcome').hidden=true;state=conversation.turn();
    const id=crypto.randomUUID();await conversation.tool(state,{partId:id,name:input.name,state:'running',arguments:input.arguments});
    let data=await request('/api/host/call',input);
    if(data.approval){if(!await confirmAction(data.approval)){await conversation.tool(state,{partId:id,name:input.name,state:'denied'});conversation.finish(state,'completed');return;}data=await request('/api/host/call',{...input,approvalToken:data.approval.token});}
    await conversation.tool(state,{partId:id,name:input.name,state:data.call.result.isError?'failed':'completed',call:data.call});conversation.finish(state,'completed');
  }catch(error){if(state)conversation.finish(state,'failed',error);else showError(error);}
  finally{directBusy=false;controls();}
};
$('text-only').onchange=async()=>{if(apps.hasWork()){$('text-only').checked=!$('text-only').checked;showError(new Error('Bitte die laufende Bearbeitung zuerst abschließen.'));return;}await apps.setTextOnly();};
for(const el of document.querySelectorAll('[data-icon]'))el.replaceChildren(icon(el.dataset.icon));
for(const el of document.querySelectorAll('[data-prompt]'))el.onclick=()=>{if(active)return;$('prompt').value=el.dataset.prompt;draftRevision++;resize();$('prompt').focus();};
window.addEventListener('beforeunload',event=>{if(active||directBusy||apps.hasWork()){event.preventDefault();event.returnValue='';}});
window.addEventListener('pagehide',()=>{active?.controller?.abort();void apps.clear();});
try{
  status=await request('/api/host/status');const server=status.server?.name||'MCP';$('status').textContent=`${server} · verbunden`;
  $('connection-info').textContent=`${server} · ${status.tools.length} freigegebene Tools`;$('model').textContent=status.model.replace(/^gpt-/,'GPT-').replace(/-terra$/,' Terra').replace(/-luna$/,' Luna');
  for(const tool of status.tools.filter(tool=>!tool._meta?.ui?.visibility||tool._meta.ui.visibility.includes('model'))){const option=node('option',tool.title||tool.name);option.value=tool.name;$('tool').append(option);}
  if(!status.providerConfigured)showError(new Error('Für den Chat ist noch kein API-Schlüssel konfiguriert. Tools kannst du unter „Tools und Verbindung“ direkt testen.'));
}catch(error){$('status').textContent='Verbindung nicht verfügbar';showError(error);}
controls();
