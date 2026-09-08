import test from 'node:test';
import assert from 'node:assert/strict';
import {createPolicy,checkedResource,modelResult} from '../policy.mjs';
const make=(name,visibility,readOnlyHint,uri='ui://customer/card')=>({name,inputSchema:{type:'object',additionalProperties:false,properties:{value:{type:'string'}},required:['value']},annotations:{readOnlyHint},_meta:{ui:{resourceUri:uri,visibility}}});
const tools=[make('read',['app','model'],true),make('save',['app'],false),make('other',['app'],false,'ui://customer/other')];
test('operator allowlist and app/model/resource scopes are independent',()=>{
  const policy=createPolicy(tools,{allowedTools:['read','save']});
  assert.equal(policy.authorize('read',{value:'x'},'model').confirmation,false);
  assert.throws(()=>policy.authorize('save',{value:'x'},'model'),/not enabled/);
  assert.throws(()=>policy.authorize('other',{value:'x'},'app','ui://customer/other'),/not enabled/);
  assert.throws(()=>policy.authorize('save',{value:'x'},'app','ui://customer/other'),/different UI/);
  assert.equal(policy.authorize('save',{value:'x'},'app','ui://customer/card').confirmation,true);
  assert.throws(()=>policy.authorize('save',{value:'x',authority:'owner'},'app','ui://customer/card'),/schema/);
});
test('only explicit operator policy permits direct writes',()=>{
  assert.throws(()=>createPolicy(tools,{allowedTools:['read'],autoApproveTools:['save']}),/exceeds/);
  const policy=createPolicy(tools,{allowedTools:['save'],autoApproveTools:['save']});
  assert.equal(policy.authorize('save',{value:'x'},'app','ui://customer/card').confirmation,false);
});
test('MCP resource admits exact URI/MIME/bounded bytes only',()=>{
  const resource={uri:'ui://customer/card',mimeType:'text/html;profile=mcp-app',text:'<html><head></head><body>Card</body></html>'};
  assert.match(checkedResource({contents:[resource]},resource.uri).sha256,/^[a-f0-9]{64}$/);
  for(const contents of [[{...resource,mimeType:'text/html'}],[{...resource,uri:'https://customer/code'}],[resource,resource],[{...resource,text:'x'.repeat(3_000_001)}]])assert.throws(()=>checkedResource({contents},resource.uri));
});
test('private metadata never reaches the model',()=>{
  const result=modelResult({content:[{type:'text',text:'Safe'}],structuredContent:{id:'one'},_meta:{secret:'PIXELS'}});
  assert.equal(JSON.stringify(result).includes('PIXELS'),false);
});
