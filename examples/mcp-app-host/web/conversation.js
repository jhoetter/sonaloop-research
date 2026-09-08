import {$,node,icon,button,markdown,toolLabel,fallback} from './dom.js';
const labels={preparing:'Wird vorbereitet',approval_required:'Freigabe nötig',running:'Wird ausgeführt',completed:'Erledigt',failed:'Fehlgeschlagen',denied:'Abgelehnt',outcome_unknown:'Ausgang unklar'};
export function createConversation({getStatus,apps,approve,recover}){
  let follow=true,scrollPending=false;
  const scroll=$('scroll-area');
  function changed(){
    if(scrollPending)return;scrollPending=true;
    requestAnimationFrame(()=>{scrollPending=false;if(follow)scroll.scrollTop=scroll.scrollHeight;$('to-latest').hidden=follow||scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<80;});
  }
  scroll.addEventListener('scroll',()=>{follow=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<100;$('to-latest').hidden=follow;},{passive:true});
  $('to-latest').onclick=()=>{follow=true;changed();};
  function user(text){$('welcome').hidden=true;const row=node('article',undefined,'message user');row.setAttribute('aria-label','Du');row.append(node('p',text,'user-text'));$('messages').append(row);follow=true;changed();return row;}
  function turn(){
    const row=node('article',undefined,'message assistant');row.setAttribute('aria-label','Produkt-Agent');
    const heading=node('div',undefined,'assistant-heading'),mark=node('span',undefined,'agent-icon');mark.append(icon('spark'));heading.append(mark,node('span','Produkt-Agent'));
    const content=node('div',undefined,'assistant-content'),parts=node('div',undefined,'turn-parts');
    const progress=node('div',undefined,'turn-progress'),spinner=node('span',undefined,'spinner'),progressText=node('span','Antwort wird vorbereitet …');progress.append(spinner,progressText);
    const footer=node('div',undefined,'turn-footer');footer.hidden=true;const copy=button('Antwort kopieren','copy');footer.append(copy);
    content.append(parts,progress,footer);row.append(heading,content);$('messages').append(row);
    const state={row,parts,progress,progressText,footer,items:new Map(),text:new Map(),started:Date.now(),status:'running',notice:null};
    copy.onclick=async()=>{try{await navigator.clipboard.writeText([...state.text.values()].join('\n\n'));copy.replaceChildren(icon('check'));copy.setAttribute('aria-label','Kopiert');setTimeout(()=>{copy.replaceChildren(icon('copy'));copy.setAttribute('aria-label','Antwort kopieren');},1600);}catch{note(state,'Kopieren nicht verfügbar. Du kannst den Text markieren.');}};
    changed();return state;
  }
  function text(state,id,value,append=true){
    let item=state.items.get(id);
    if(!item){item={kind:'text',el:node('div',undefined,'text-part')};state.items.set(id,item);state.parts.append(item.el);}
    if(item.kind!=='text')throw new Error('Ungültige Antwortstruktur.');
    const next=append?(state.text.get(id)||'')+value:value;state.text.set(id,next);markdown(item.el,next);state.progressText.textContent='Antwort wird geschrieben …';changed();
  }
  async function tool(state,event){
    let item=state.items.get(event.partId);
    if(!item){
      const el=node('section',undefined,'tool-part'),details=node('details',undefined,'tool-inspector'),summary=node('summary');
      const glyph=node('span',undefined,'tool-icon'),name=node('span',toolLabel(getStatus(),event.name),'tool-name'),badge=node('span',undefined,'tool-state'),chevron=node('span',undefined,'tool-chevron');glyph.append(icon('tool'));chevron.append(icon('chevron'));summary.append(glyph,name,badge,chevron);
      const body=node('div',undefined,'tool-details'),argsTitle=node('h4','Eingabe'),args=node('pre'),outputTitle=node('h4','Ergebnis'),output=node('pre');outputTitle.hidden=true;output.hidden=true;body.append(argsTitle,args,outputTitle,output);details.append(summary,body);
      const app=node('div'),decision=node('div');el.append(details,app,decision);state.parts.append(el);
      item={kind:'tool',el,details,summary,name,badge,glyph,args,output,outputTitle,app,decision,rendered:false,view:null,previewId:null,approvalId:null};state.items.set(event.partId,item);
    }
    if(item.kind!=='tool')throw new Error('Ungültige Tool-Struktur.');
    if(item.lastState!==event.state&&['running','completed','failed','outcome_unknown'].includes(event.state))$('announcer').textContent=`${toolLabel(getStatus(),event.name)}: ${labels[event.state]}.`;
    item.lastState=event.state;item.badge.textContent=labels[event.state]||event.state;item.badge.dataset.state=event.state==='failed'?'error':event.state;
    item.glyph.replaceChildren(event.state==='running'||event.state==='preparing'?node('span',undefined,'spinner'):icon(event.state==='completed'?'check':event.state==='failed'||event.state==='outcome_unknown'?'alert':'tool'));
    if(event.arguments!==undefined)item.args.textContent=JSON.stringify(event.arguments,null,2);
    if(event.error){item.outputTitle.hidden=false;item.output.hidden=false;item.output.textContent=event.error.message||'Tool-Aktion fehlgeschlagen.';}
    if(event.preview&&!item.view&&!event.call&&item.previewId!==event.preview.id){item.previewId=event.preview.id;item.view=await apps.render(event.preview,item.app);}
    if(event.previewError&&!event.call&&!item.previewError){item.previewError=node('p',event.previewError,'turn-notice');item.app.append(item.previewError);}
    if(event.call){
      item.outputTitle.hidden=false;item.output.hidden=false;item.output.textContent=fallback(event.call.result)||'Tool-Aktion abgeschlossen.';
      if(!item.rendered){item.rendered=true;item.previewError?.remove();item.view=item.view?await item.view.promote(event.call):await apps.render(event.call,item.app);}
    }
    if(event.state==='running'&&!event.call)await item.view?.execution('Aktion wird ausgeführt. Der gespeicherte Stand wird anschließend bestätigt.');
    if(event.state==='outcome_unknown'&&!event.call)await item.view?.execution('Ausgang unklar. Diese Vorschau bestätigt keinen gespeicherten Stand; die Aktion wird nicht wiederholt.');
    if(['completed','failed'].includes(event.state)&&!event.call)await item.view?.execution(event.error?.message||'Die Aktion ist beendet, aber ein bestätigter gespeicherter Stand ist nicht verfügbar. Die Vorschau wird ausgeblendet.');
    if(event.state==='denied')await item.view?.cancel('Aktion nicht ausgeführt.');
    if(event.state==='approval_required'&&event.approval&&(item.approvalId!==event.approval.id||event.confirmedWaiting)){
      item.approvalId=event.approval.id;const box=node('div',undefined,'approval-inline');box.append(node('p','Diesen Vorschlag ausführen?'));
      const actions=node('div',undefined,'dialog-actions'),yes=node('button','Ausführen','primary-button'),no=node('button','Ablehnen','quiet-button');yes.type=no.type='button';actions.append(yes,no);box.append(actions);item.decision.replaceChildren(box);
      const decide=async accepted=>{yes.disabled=no.disabled=true;try{await approve(state,event.approval,accepted);}catch(error){yes.disabled=no.disabled=false;note(state,error.message);}};
      yes.onclick=()=>decide(true);no.onclick=()=>decide(false);
    }else if(event.state!=='approval_required')item.decision.replaceChildren();
    state.progressText.textContent=event.state==='running'?`${toolLabel(getStatus(),event.name)} …`:event.state==='approval_required'?'Wartet auf deine Freigabe':'Nächster Schritt wird vorbereitet …';changed();
  }
  function note(state,message,retry){
    if(!state.notice){state.notice=node('div',undefined,'turn-notice');state.parts.append(state.notice);}
    state.recoveryNotice=!!retry;state.notice.replaceChildren(node('p',message));
    if(retry){const check=node('button','Status prüfen','quiet-button');check.type='button';check.onclick=async()=>{check.disabled=true;try{await retry();}finally{check.disabled=false;}};state.notice.append(check);}
    changed();
  }
  function finish(state,status,error){
    state.status=status;state.progress.hidden=true;state.footer.hidden=false;
    if(status==='stopped')note(state,'Gestoppt. Bereits ausgeführte Aktionen bleiben erhalten.');
    state.errorBox?.remove();state.errorBox=null;
    if(error){
      const box=node('div',undefined,'turn-error');box.setAttribute('role','alert');box.append(node('p',error.message||'Die Antwort konnte nicht abgeschlossen werden.'));
      if(state.turnId){const again=node('button','Status prüfen','quiet-button');again.type='button';again.onclick=()=>recover(state);box.append(again);}state.parts.append(box);state.errorBox=box;
    }
    if(!state.text.size)state.footer.hidden=true;
    $('announcer').textContent=status==='completed'?'Antwort abgeschlossen.':status==='stopped'?'Antwort gestoppt.':'Antwort unterbrochen.';changed();
  }
  return{changed,user,turn,text,tool,note,finish,clearRecovery(state){if(state.recoveryNotice){state.notice?.remove();state.notice=null;state.recoveryNotice=false;}},clear(){follow=true;$('messages').replaceChildren();$('welcome').hidden=false;$('to-latest').hidden=true;}};
}
