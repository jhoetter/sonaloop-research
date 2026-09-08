// Provider-wire fixture only. Never installed in a customer release or pointed at a real provider.
const nativeFetch=globalThis.fetch;
const textItem=(id,text)=>({id,type:'message',role:'assistant',status:'completed',content:[{type:'output_text',text,annotations:[]}]});
globalThis.fetch=async(url,options)=>{
  if(String(url)!=='https://api.openai.com/v1/responses')return nativeFetch(url,options);
  const input=JSON.parse(options.body);
  if(input.model!=='gpt-5.6-terra'||input.reasoning?.effort!=='none')throw new Error('Fixture requires explicit modern model and latency baseline');
  if(JSON.stringify(input).includes('fixture-secret'))throw new Error('Private tool metadata reached provider');
  const lastUser=input.input.findLastIndex(item=>item.role==='user');
  const command=input.input[lastUser]?.content||'';
  const tail=input.input.slice(lastUser+1),hasTool=tail.some(item=>item.type==='function_call_output');
  if(command==='fixture-error'||command==='fixture-after-tool-error'&&hasTool)return new Response(JSON.stringify({error:{message:'PRIVATE provider diagnostics'}}),{status:503,headers:{'content-type':'application/json'}});
  let output;
  if(command==='fixture-hold')output=[textItem('msg_hold','Das ist eine langsam eintreffende Antwort. '.repeat(12))];
  else if(!hasTool){
    output=[textItem('msg_before','Ich schaue im verbundenen Produkt nach.\n\n'),{id:'fc_fixture',type:'function_call',call_id:`call_${lastUser}`,name:command==='fixture-approval'?'fixture_action':'fixture_read',arguments:JSON.stringify({value:'Reale MCP-Testkarte'})}];
  }else output=[textItem('msg_after','**Bereit.** Die Ansicht ist jetzt geöffnet.\n\n- Direkt in der Karte arbeiten\n- Den Entwurf im Eingabefeld behalten\n\n<script>window.fixtureInjection=true</script> [Ungültiger Link](javascript:alert(1))')];
  const events=[{type:'response.created',response:{id:'resp_fixture',status:'in_progress',output:[]}}];
  for(const [index,item] of output.entries()){
    events.push({type:'response.output_item.added',output_index:index,item:item.type==='message'?{...item,content:[]}:{...item,arguments:''}});
    if(item.type==='message'){
      events.push({type:'response.content_part.added',output_index:index,item_id:item.id,content_index:0,part:{type:'output_text',text:'',annotations:[]}});
      for(const delta of item.content[0].text.match(/.{1,15}|\n/g)||[])events.push({type:'response.output_text.delta',output_index:index,item_id:item.id,content_index:0,delta});
      events.push({type:'response.output_text.done',output_index:index,item_id:item.id,content_index:0,text:item.content[0].text});
    }else{
      events.push({type:'response.function_call_arguments.delta',output_index:index,item_id:item.id,delta:item.arguments});
      events.push({type:'response.function_call_arguments.done',output_index:index,item_id:item.id,arguments:item.arguments});
    }
    events.push({type:'response.output_item.done',output_index:index,item});
  }
  events.push({type:'response.completed',response:{id:'resp_fixture',status:'completed',output,usage:{input_tokens:10,output_tokens:10}}});
  if(!input.stream)return new Response(JSON.stringify(events.at(-1).response),{headers:{'content-type':'application/json'}});
  let timer,closed=false,index=0;
  const body=new ReadableStream({
    start(controller){
      const abort=()=>{if(closed)return;closed=true;clearTimeout(timer);controller.error(new DOMException('Aborted','AbortError'));};
      options.signal?.addEventListener('abort',abort,{once:true});
      if(options.signal?.aborted)return abort();
      function next(){if(closed)return;if(index===events.length){closed=true;options.signal?.removeEventListener('abort',abort);controller.close();return;}controller.enqueue(new TextEncoder().encode(`event: ${events[index].type}\ndata: ${JSON.stringify(events[index++])}\n\n`));timer=setTimeout(next,command==='fixture-hold'?100:65);}
      timer=setTimeout(next,100);
    },cancel(){closed=true;clearTimeout(timer);}
  });
  return new Response(body,{headers:{'content-type':'text/event-stream'}});
};
