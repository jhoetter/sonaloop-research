import {AppBridge} from '@modelcontextprotocol/ext-apps/app-bridge';
import {JSONRPCMessageSchema} from '@modelcontextprotocol/sdk/types.js';
import {$,node,fallback} from './dom.js';
class OpaqueFrameTransport{
  constructor(target){this.target=target;this.listener=event=>{if(event.source!==target||event.origin!=='null')return;const parsed=JSONRPCMessageSchema.safeParse(event.data);if(parsed.success)this.onmessage?.(parsed.data);};}
  async start(){window.addEventListener('message',this.listener);}
  async send(message){this.target.postMessage(message,'*');}
  async close(){window.removeEventListener('message',this.listener);this.onclose?.();}
}
export function createAppViews({request,confirmAction,getTool,onChange}){
  const views=new Set();
  async function remove(view){
    view.disposed=true;clearTimeout(view.timer);await view.bridge?.close();view.card.remove();views.delete(view);
  }
  async function render(initial,parent){
    if(!initial.resourceUri&&!initial.uiError)return null;
    const card=node('section',undefined,'card');card.setAttribute('aria-label',`MCP ${initial.name}`);
    const appStatus=node('div',initial.uiError||'Ansicht wird geöffnet …','app-status'),slot=node('div');
    const text=node('div',undefined,'fallback'),pre=node('pre');text.append(pre);card.append(appStatus,slot,text);parent.append(card);
    const view={card,bridge:null,dirty:false,pending:false,call:initial,slot,text,appStatus,
      timer:null,ready:false,mounted:false,initialized:false,disposed:false,preview:initial.mode==='preview',
      cancelled:null,cancelSent:false,resultSent:null,executionMessage:null};
    views.add(view);
    const updateFallback=()=>{pre.textContent=view.executionMessage|| (view.call.result?fallback(view.call.result):view.cancelled||'Vorschau vor der Ausführung. Die vollständigen Eingaben stehen in den Tool-Details.');};
    updateFallback();
    function ready(label){
      if(view.disposed)return;view.ready=true;clearTimeout(view.timer);if(view.executionMessage)return;appStatus.textContent=label;
      appStatus.classList.add('ready');text.hidden=!$('text-only').checked;onChange();
    }
    async function deliverResult(){
      if(view.disposed||!view.initialized||!view.call.result||view.resultSent===view.call.id)return;
      view.resultSent=view.call.id;await view.bridge.sendToolResult(view.call.result);
      if(!view.preview)ready('Ansicht verbunden');
    }
    async function deliverCancelled(){
      if(view.disposed||!view.initialized||!view.cancelled||view.cancelSent||view.call.result)return;
      view.cancelSent=true;await view.bridge.sendToolCancelled({reason:view.cancelled});
    }
    async function mount(){
      if(view.disposed||view.mounted)return;
      if(!view.call.viewToken||$('text-only').checked){appStatus.textContent=view.call.uiError||'Textansicht';return;}
      view.mounted=true;
      const frame=node('iframe',undefined,'app-frame');view.frame=frame;frame.title=`${initial.name} · MCP App`;
      frame.setAttribute('sandbox','allow-scripts');frame.referrerPolicy='no-referrer';slot.append(frame);
      const tool=getTool?.(initial.name);
      const bridge=new AppBridge(null,{name:'Customer MCP App host',version:'0.3.0'},{serverTools:{},logging:{}},{
        hostContext:{platform:'web',theme:'light',displayMode:'inline',locale:'de-DE',...(tool?{toolInfo:{tool}}:{})}
      });view.bridge=bridge;
      const unavailable=()=>{
        if(view.disposed||view.executionMessage)return;view.ready=false;appStatus.classList.remove('ready');
        appStatus.textContent=view.preview?'Keine bestätigte Vorschau. Du kannst die Tool-Details prüfen.':'Ansicht nicht erreichbar. Die Textantwort bleibt verfügbar.';
        text.hidden=false;onChange();
      };
      view.timer=setTimeout(unavailable,15000);
      bridge.oncalltool=async params=>{
        // The backend independently denies preview tokens. This UI fence also
        // prevents accidental action requests while the customer renders input.
        if(view.preview||view.cancelled)return{isError:true,content:[{type:'text',text:'Diese Vorschau führt keine Aktionen aus.'}],structuredContent:{error:{code:'preview_readonly',message:'Diese Vorschau führt keine Aktionen aus.'}}};
        if(view.pending)return{isError:true,content:[{type:'text',text:'Eine Aktion läuft bereits.'}]};
        view.pending=true;
        try{
          const input={viewToken:view.call.viewToken,name:params.name,arguments:params.arguments};let data=await request('/api/host/call',input);
          if(data.approval){
            if(!await confirmAction(data.approval))return{isError:true,content:[{type:'text',text:'Aktion abgebrochen.'}],structuredContent:{error:{code:'forbidden',message:'Aktion abgebrochen.'}}};
            data=await request('/api/host/call',{...input,approvalToken:data.approval.token});
          }
          if(!data.result.isError)pre.textContent=fallback(data.result);
          return data.result;
        }catch(error){return{isError:true,content:[{type:'text',text:error.message}],structuredContent:{error:{code:error.code||'outcome_unknown',message:error.message}}};}
        finally{view.pending=false;onChange();}
      };
      bridge.addEventListener('initialized',async()=>{
        if(view.disposed||view.initialized)return;view.initialized=true;
        // One standard input notification per frame, including when completion
        // arrives before initialization. Never manufacture a preview tool result.
        await bridge.sendToolInput({arguments:initial.arguments});
        await deliverResult();await deliverCancelled();
        if(view.preview&&!view.ready&&!view.executionMessage)appStatus.textContent='Vorschau wird geladen …';
      });
      bridge.addEventListener('sizechange',({height})=>{if(Number.isFinite(height))frame.style.height=`${Math.max(180,Math.min(1400,Math.ceil(height)))}px`;onChange();});
      bridge.addEventListener('loggingmessage',({data})=>{
        if(data?.event==='view-rendered')ready(view.preview?'Vorschau bereit':'Ansicht bereit');
        if(data?.event==='view-dirty'&&typeof data.dirty==='boolean'&&!view.preview)view.dirty=data.dirty;
      });
      bridge.onerror=unavailable;
      await bridge.connect(new OpaqueFrameTransport(frame.contentWindow));frame.src=`/app-frame/${encodeURIComponent(view.call.viewToken)}`;
    }
    view.display=async()=>{
      await mount();const textOnly=$('text-only').checked;slot.hidden=textOnly||!!view.executionMessage;appStatus.hidden=textOnly;
      text.hidden=!textOnly&&view.ready&&!view.executionMessage;onChange();
    };
    view.promote=async call=>{
      if(view.disposed||view.call.id===call.id)return view;
      if(call.resourceUri&&call.viewToken&&call.resourceUri===initial.resourceUri&&call.resourceSha256===initial.resourceSha256){
        // The iframe keeps its identity; only the host-held action grant changes.
        view.call=call;view.preview=false;view.cancelled=null;view.executionMessage=null;updateFallback();await deliverResult();await view.display();return view;
      }
      if(call.result?.isError){view.call={...view.call,result:call.result,id:call.id};view.executionMessage=null;updateFallback();await deliverResult();await view.display();return view;}
      // A different verified resource requires its own frame. Do not deliver a
      // new resource's result or live grant into the previously loaded customer UI.
      await remove(view);return render(call,parent);
    };
    view.cancel=async reason=>{
      if(view.disposed||!view.preview||view.call.result)return;
      view.cancelled=reason||'Nicht ausgeführt.';view.executionMessage=null;updateFallback();await deliverCancelled();await view.display();
    };
    view.execution=async message=>{
      if(view.disposed||!view.preview||view.call.result)return;
      view.executionMessage=message;clearTimeout(view.timer);appStatus.classList.remove('ready');appStatus.textContent=message;updateFallback();await view.display();
    };
    await view.display();return view;
  }
  return{
    render,
    hasWork:()=>[...views].some(view=>view.dirty||view.pending),
    async setTextOnly(){for(const view of views)await view.display();},
    async clear(){for(const view of [...views])await remove(view);},
  };
}
