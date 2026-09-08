// Explicit protocol fixture: no native customer data, credentials or provider.
import {Server} from '@modelcontextprotocol/sdk/server/index.js';
import {StdioServerTransport} from '@modelcontextprotocol/sdk/server/stdio.js';
import {ListToolsRequestSchema,CallToolRequestSchema,ListResourcesRequestSchema,ReadResourceRequestSchema} from '@modelcontextprotocol/sdk/types.js';
import {build} from 'esbuild';
const uri='ui://fixture/card';
const source=`import {App} from '@modelcontextprotocol/ext-apps';
 const app=new App({name:'Protocol fixture',version:'1.0.0'},{},{autoResize:true});
 const show=r=>{document.querySelector('p').textContent=r.structuredContent.value;};
 app.ontoolresult=async r=>{show(r);await app.sendLog({level:'info',data:{event:'view-rendered'}});};
 document.querySelector('button').onclick=async()=>show(await app.callServerTool({name:'fixture_save',arguments:{value:'Changed through MCP'}}));
 await app.connect();`;
const bundle=await build({stdin:{contents:source,resolveDir:process.cwd(),sourcefile:'fixture.js'},bundle:true,write:false,format:'esm',platform:'browser'});
const html='<html><head><meta charset="utf-8"></head><body><p>Loading fixture</p><button>Change fixture</button><script type="module">'+bundle.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')+'</script></body></html>';
const server=new Server({name:'protocol-fixture',version:'1.0.0'},{capabilities:{tools:{},resources:{}}});
const tools=['fixture_read','fixture_save'].map(name=>({name,description:'Synthetic protocol fixture',inputSchema:{type:'object',properties:{value:{type:'string'}},required:['value'],additionalProperties:false},annotations:{readOnlyHint:name==='fixture_read'},_meta:{ui:{resourceUri:uri,visibility:name==='fixture_read'?['model','app']:['app']}}}));
server.setRequestHandler(ListToolsRequestSchema,async()=>({tools}));
server.setRequestHandler(CallToolRequestSchema,async request=>{
  if(request.params.arguments.value==='fixture-disconnect')process.exit(0);
  return {content:[{type:'text',text:request.params.arguments.value}],structuredContent:{value:request.params.arguments.value},_meta:{private:'fixture-secret'}};
});
server.setRequestHandler(ListResourcesRequestSchema,async()=>({resources:[{uri,name:'Fixture',mimeType:'text/html;profile=mcp-app'}]}));
server.setRequestHandler(ReadResourceRequestSchema,async()=>({contents:[{uri,mimeType:'text/html;profile=mcp-app',text:html}]}));
await server.connect(new StdioServerTransport());
