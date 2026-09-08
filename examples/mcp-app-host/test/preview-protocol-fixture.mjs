// Synthetic protocol only: no customer data, provider, or real native operation.
import {appendFileSync,readFileSync} from 'node:fs';
import {Server} from '@modelcontextprotocol/sdk/server/index.js';
import {StdioServerTransport} from '@modelcontextprotocol/sdk/server/stdio.js';
import {ListToolsRequestSchema,CallToolRequestSchema,ReadResourceRequestSchema} from '@modelcontextprotocol/sdk/types.js';
const uri='ui://fixture/approval-preview';
const record=(method,params)=>appendFileSync(process.env.PREVIEW_FIXTURE_LOG,JSON.stringify({method,params})+'\n');
const server=new Server({name:'approval-preview-fixture',version:'1.0.0'},{capabilities:{tools:{},resources:{}}});
server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:['fixture_read','fixture_save','fixture_action'].map(name=>({name,description:'Synthetic fixture',inputSchema:{type:'object',properties:{value:{type:'string'}},required:['value'],additionalProperties:false},annotations:{readOnlyHint:name==='fixture_read'},_meta:{ui:{resourceUri:uri,visibility:name==='fixture_save'?['app']:['model','app']}}}))}));
server.setRequestHandler(ReadResourceRequestSchema,async request=>{
  record('resources/read',request.params);
  const version=readFileSync(process.env.PREVIEW_FIXTURE_VERSION,'utf8');
  return{contents:[{uri,mimeType:'text/html;profile=mcp-app',text:`<html><head><title>Fixture</title></head><body>Passive fixture ${version}</body></html>`}]};
});
server.setRequestHandler(CallToolRequestSchema,async request=>{
  record('tools/call',request.params);return{content:[{type:'text',text:request.params.arguments.value}],structuredContent:{value:request.params.arguments.value}};
});
await server.connect(new StdioServerTransport());
