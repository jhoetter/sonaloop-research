import {AppBridge} from '@modelcontextprotocol/ext-apps/app-bridge';
import {JSONRPCMessageSchema} from '@modelcontextprotocol/sdk/types.js';
import {$,node,fallback} from './dom.js';
class OpaqueFrameTransport{
  constructor(target){this.target=target;this.listener=event=>{if(event.source!==target||event.origin!=='null')return;const parsed=JSONRPCMessageSchema.safeParse(event.data);if(parsed.success)this.onmessage?.(parsed.data);};}
  async start(){window.addEventListener('message',this.listener);}
  async send(message){this.target.postMessage(message,'*');}
  async close(){window.removeEventListener('message',this.listener);this.onclose?.();}
}
export function createAppViews({request,confirmAction,onChange}){
  const views=[];
  async function render(call,parent){
    if(!call.resourceUri&&!call.uiError)return;
    const card=node('section',undefined,'card');card.setAttribute('aria-label',`MCP ${call.name}`);
    const appStatus=node('div',call.uiError||'Ansicht wird geöffnet …','app-status');const slot=node('div');
    const text=node('div',undefined,'fallback');text.append(node('pre',fallback(call.result)));card.append(appStatus,slot,text);parent.append(card);
    const view={bridge:null,dirty:false,pending:false,call,slot,text,appStatus,timer:null,ready:false,mounted:false};views.push(view);
    async function mount(){
      if(view.mounted)return;
      text.hidden=false;appStatus.classList.remove('ready');
      if(!call.viewToken||$('text-only').checked){appStatus.textContent=call.uiError||'Textansicht';onChange();return;}
      view.mounted=true;
      const frame=node('iframe',undefined,'app-frame');frame.title=`${call.name} · MCP App`;frame.setAttribute('sandbox','allow-scripts');frame.referrerPolicy='no-referrer';slot.append(frame);
      const bridge=new AppBridge(null,{name:'Customer MCP App host',version:'0.2.0'},{serverTools:{},logging:{}},{hostContext:{platform:'web',theme:'light',displayMode:'inline',locale:'de-DE'}});view.bridge=bridge;
      const unavailable=()=>{view.ready=false;appStatus.classList.remove('ready');appStatus.textContent='Ansicht nicht erreichbar. Die Textantwort bleibt verfügbar.';text.hidden=false;onChange();};
      view.timer=setTimeout(unavailable,15000);
      bridge.oncalltool=async params=>{
        if(view.pending)return{isError:true,content:[{type:'text',text:'Eine Aktion läuft bereits.'}]};view.pending=true;
        try{
          const input={viewToken:call.viewToken,name:params.name,arguments:params.arguments};let data=await request('/api/host/call',input);
          if(data.approval){if(!await confirmAction(data.approval))return{isError:true,content:[{type:'text',text:'Aktion abgebrochen.'}],structuredContent:{error:{code:'forbidden',message:'Aktion abgebrochen.'}}};data=await request('/api/host/call',{...input,approvalToken:data.approval.token});}
          if(!data.result.isError)text.querySelector('pre').textContent=fallback(data.result);
          return data.result;
        }catch(error){return{isError:true,content:[{type:'text',text:error.message}],structuredContent:{error:{code:error.code||'outcome_unknown',message:error.message}}};}
        finally{view.pending=false;onChange();}
      };
      bridge.addEventListener('initialized',async()=>{
        clearTimeout(view.timer);await bridge.sendToolInput({arguments:call.arguments});await bridge.sendToolResult(call.result);
        view.ready=true;appStatus.textContent='Ansicht verbunden';appStatus.classList.add('ready');text.hidden=!$('text-only').checked;onChange();
      });
      bridge.addEventListener('sizechange',({height})=>{if(Number.isFinite(height))frame.style.height=`${Math.max(180,Math.min(1400,Math.ceil(height)))}px`;onChange();});
      bridge.addEventListener('loggingmessage',({data})=>{
        if(data?.event==='view-rendered'){clearTimeout(view.timer);view.ready=true;appStatus.textContent='Ansicht bereit';appStatus.classList.add('ready');text.hidden=!$('text-only').checked;onChange();}
        if(data?.event==='view-dirty'&&typeof data.dirty==='boolean')view.dirty=data.dirty;
      });
      bridge.onerror=unavailable;
      await bridge.connect(new OpaqueFrameTransport(frame.contentWindow));frame.src=`/app-frame/${encodeURIComponent(call.viewToken)}`;
    }
    view.display=async()=>{await mount();const textOnly=$('text-only').checked;slot.hidden=textOnly;appStatus.hidden=textOnly; text.hidden=!textOnly&&view.ready;onChange();};await view.display();
  }
  return{
    render,
    hasWork:()=>views.some(view=>view.dirty||view.pending),
    async setTextOnly(){for(const view of views)await view.display();},
    async clear(){for(const view of views){clearTimeout(view.timer);await view.bridge?.close();}views.length=0;},
  };
}
