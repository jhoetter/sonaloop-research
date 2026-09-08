import { createServer, request as httpRequest } from 'node:http';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { ContractError, createPolicy, checkedResource, sha } from './policy.mjs';
import { json, fail, body, originGuard, createSessions } from './http.mjs';
import { createAgent } from './agent.mjs';
import { serveChatStream } from './chat-http.mjs';
import { MAX_MCP_STDIO_BUFFER_BYTES } from './host-limits.mjs';

const config = JSON.parse(readFileSync(resolve(process.env.MCP_APP_HOST_CONFIG || 'config.json'), 'utf8'));
const origin = new URL(config.hostOrigin);
if (!['127.0.0.1','localhost'].includes(origin.hostname) || origin.protocol !== 'http:' || origin.origin !== config.hostOrigin
    || !Number.isInteger(Number(origin.port)) || Number(origin.port) < 1024 || !Array.isArray(config.allowedTools)
    || !config.allowedTools.length || config.allowedTools.length > 64) throw new Error('Explicit loopback origin and bounded tool policy required.');
const product = config.productProxy && new URL(config.productProxy);
if (product && (product.protocol !== 'http:' || !['localhost','127.0.0.1'].includes(product.hostname) || product.origin === origin.origin || product.pathname !== '/')) throw new Error('Product proxy must name another loopback HTTP origin.');
const client = new Client({name:'customer-mcp-app-reference-host',version:'0.2.0'},{capabilities:{extensions:{'io.modelcontextprotocol/ui':{mimeTypes:['text/html;profile=mcp-app']}}}});
const transport = new StdioClientTransport({command:config.command, args:config.args || [], cwd:config.cwd, maxBufferSize:MAX_MCP_STDIO_BUFFER_BYTES,
  env:{PATH:process.env.PATH, ...(process.env.OPENAI_API_KEY ? {OPENAI_API_KEY:process.env.OPENAI_API_KEY} : {}), ...config.env}, stderr:'pipe'});
let server;
try {
  await client.connect(transport, {timeout:30000});
  // Drain child diagnostics without copying possibly private runtime/provider details to the browser/log.
  transport.stderr?.on('data', () => {});
  const discovered = []; let cursor;
  do { const page=await client.listTools(cursor ? {cursor} : {}); discovered.push(...page.tools); cursor=page.nextCursor; if(discovered.length>2000) throw new Error('MCP catalogue limit exceeded.'); } while(cursor);
  const policy = createPolicy(discovered, config);
  const sessions = createSessions();
  const views = new Map();
  const approvals = new Map();
  const model = process.env.OPENAI_MODEL || config.model || 'gpt-5.6-terra';
  function sweep() {
    for (const map of [views,approvals]) for(const [key,value] of map) if(Date.now()-value.created>1800000) map.delete(key);
  }
  async function grant(name, args, result, owner) {
    sweep();
    const tool = policy.tools.find(item=>item.name===name);
    const uri = !result.isError && tool?._meta?.ui?.resourceUri;
    const call = {id:randomUUID(), name, arguments:args, result};
    if (typeof uri === 'string' && uri.startsWith('ui://')) {
      // Discovery is data. Only resources/read on this connected server is used;
      // no HTTP fetch, filesystem import or catalog service is inferred from metadata.
      try {
        if(views.size>=200) throw new ContractError('view_limit','Zu viele offene Ansichten.',429);
        const resource = checkedResource(await client.readResource({uri}), uri);
        const viewToken=randomUUID();
        views.set(viewToken,{owner,uri,sha256:resource.sha256,created:Date.now(),calls:0});
        Object.assign(call,{resourceUri:uri,resourceSha256:resource.sha256,viewToken});
      } catch { call.uiError='Die gebundene MCP-App ist nicht verfügbar; Textantwort bleibt verfügbar.'; }
    }
    return call;
  }
  const agent=createAgent({client,policy,model,apiKey:process.env.OPENAI_API_KEY,grant});
  const csp="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src data: 'self'; frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";
  function staticFile(res,name) {
    res.writeHead(200,{'Content-Type':name.endsWith('.html')?'text/html; charset=utf-8':name.endsWith('.css')?'text/css; charset=utf-8':'text/javascript; charset=utf-8',
      'Content-Security-Policy':csp,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'});
    res.end(readFileSync(new URL(`dist/${name}`,import.meta.url)));
  }
  function getView(token,owner) {
    sweep(); const view=views.get(token);
    if(!view || view.owner!==owner) throw new ContractError('view_expired','Ansicht abgelaufen; bitte neu öffnen.',403);
    return view;
  }
  async function invoke(input,owner) {
    sweep();
    const audience=input.viewToken?'app':'model';
    const view=input.viewToken && getView(input.viewToken,owner);
    const authorization=policy.authorize(input.name,input.arguments,audience,view?.uri);
    if(view && ++view.calls>100) throw new ContractError('call_limit','Aufruflimit der Ansicht erreicht.',429);
    if(authorization.confirmation) {
      const expected=sha({name:input.name,arguments:input.arguments,viewToken:input.viewToken || null});
      const approved=approvals.get(input.approvalToken);
      if(!approved || approved.owner!==owner || approved.digest!==expected) {
        sweep(); if(approvals.size>=100) throw new ContractError('approval_limit','Zu viele offene Bestätigungen.',429);
        const approvalToken=randomUUID(); approvals.set(approvalToken,{owner,digest:expected,created:Date.now()});
        return {approval:{token:approvalToken,name:input.name,arguments:input.arguments}};
      }
      approvals.delete(input.approvalToken);
    }
    let result;
    try { result=await client.callTool({name:input.name,arguments:input.arguments},undefined,{timeout:240000}); }
    catch { throw new ContractError('outcome_unknown','Tool-Ausgang unklar. Bitte den gespeicherten Operationsstatus prüfen; die Aktion wird nicht wiederholt.',502); }
    return input.viewToken ? {result} : {call:await grant(input.name,input.arguments,result,owner)};
  }
  server=createServer(async(req,res)=>{
    try {
      const url=new URL(req.url,origin);
      if(url.origin!==origin.origin) throw new ContractError('origin_denied','Ungültiges Anfrageziel.',403);
      originGuard(req,origin.origin,req.method==='POST');
      if(req.method==='GET' && ['/', '/agent'].includes(url.pathname)) return staticFile(res,'index.html');
      if(req.method==='GET' && ['/host.js','/style.css'].includes(url.pathname)) return staticFile(res,url.pathname.slice(1));
      if(req.method==='GET' && url.pathname==='/api/host/status') {
        const session=sessions.session(req,res,true);
        return json(res,200,{csrf:session.csrf,model,providerConfigured:!!process.env.OPENAI_API_KEY,tools:policy.tools,server:client.getServerVersion(),productAvailable:!!product});
      }
      if(url.pathname.startsWith('/api/host/') || url.pathname.startsWith('/app-frame/')) {
        const session=sessions.session(req,res);
        if(req.method==='GET' && /^\/api\/host\/chat\/requests\/[a-zA-Z0-9_-]+$/.test(url.pathname)) return json(res,200,agent.requestSnapshot(url.pathname.split('/').at(-1),session.id));
        if(req.method==='GET' && /^\/api\/host\/chat\/turns\/[a-zA-Z0-9_-]+$/.test(url.pathname)) return json(res,200,agent.snapshot(url.pathname.split('/').at(-1),session.id));
        if(req.method==='GET' && url.pathname.startsWith('/app-frame/')) {
          const token=url.pathname.slice('/app-frame/'.length);const view=getView(token,session.id);
          const resource=checkedResource(await client.readResource({uri:view.uri}),view.uri);
          if(resource.sha256!==view.sha256) throw new ContractError('resource_drift','Die MCP-App wurde seit dem Tool-Ergebnis verändert; bitte neu öffnen.',409);
          res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
            'Permissions-Policy':'camera=(), microphone=(), geolocation=(), clipboard-read=(), clipboard-write=()',
            'Content-Security-Policy':"sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"});
          return res.end(resource.html);
        }
        if(req.method==='POST') {
          sessions.csrf(req,session);const input=await body(req,65536);
          if(url.pathname==='/api/host/chat') {
            if(req.headers.accept?.split(',').some(value=>value.trim().split(';')[0]==='text/event-stream')) {
              const request=agent.open(input,session.id);
              return await serveChatStream(res,request,agent,session.id);
            }
            return json(res,200,await agent.chat(input.message,input.sessionId,session.id,input.approved));
          }
          if(url.pathname==='/api/host/chat/stop') return json(res,200,agent.stop(input,session.id));
          if(url.pathname==='/api/host/call') return json(res,200,await invoke(input,session.id));
        }
        throw new ContractError('not_found','Unbekannter Host-Endpunkt.',404);
      }
      if(product) {
        // Operator-configured native product, mounted at its original paths. No
        // product-specific route or data handling lives in the generic host.
        const target=new URL(product);target.pathname=url.pathname;target.search=url.search;
        const proxied=httpRequest(target,{method:req.method,headers:{...req.headers,host:product.host}},upstream=>{
          res.writeHead(upstream.statusCode,upstream.headers);upstream.pipe(res);
        });
        proxied.on('error',()=>{if(!res.headersSent)fail(res,new ContractError('product_unavailable','Kundenprodukt nicht erreichbar.',503));else res.destroy();});
        req.pipe(proxied);return;
      }
      throw new ContractError('not_found','Seite nicht gefunden.',404);
    } catch(error) {if(!res.headersSent)fail(res,error);else res.destroy();}
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(Number(origin.port),'127.0.0.1',resolve);});
  console.log(JSON.stringify({ready:true,hostOrigin:origin.origin,server:client.getServerVersion(),allowedTools:policy.tools.map(tool=>tool.name),model,providerConfigured:!!process.env.OPENAI_API_KEY}));
  const shutdown=async()=>{server.closeAllConnections();server.close();await client.close();process.exit(0);};
  process.on('SIGINT',shutdown);process.on('SIGTERM',shutdown);
} catch(error) {
  server?.close();await client.close().catch(()=>{});
  console.error(JSON.stringify({ready:false,code:error instanceof ContractError?error.code:'startup_failed'}));process.exitCode=1;
}
