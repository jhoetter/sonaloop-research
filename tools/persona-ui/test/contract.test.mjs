import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createPersonaActions } from '../../../sonaloop/web/assets/persona-view/persona-actions.js';
import { validateSurface, stableJSON } from '../../../sonaloop/web/assets/persona-view/persona-contract.js';
import { messages } from '../../../sonaloop/web/assets/persona-view/persona-i18n.js';
if (!globalThis.crypto) globalThis.crypto = webcrypto;
import { fixture } from './fixture.mjs';
test('native presentation accepts heterogeneous age and guards identity/closed DTO',()=>{
  const value=fixture();assert.equal(validateSurface(value),value);
  for(const age of [null,42,42.5,'35–44'])assert.ok(validateSurface({...value,fields:{...value.fields,age}}));
  assert.throws(()=>validateSurface({...value,extra:true}));assert.throws(()=>validateSurface({...value,persona_id:'other'},value));assert.throws(()=>validateSurface({...value,slug:'new'},value));
  assert.throws(()=>validateSurface({...value,fields:{...value.fields,age:true}}));
  assert.deepEqual(Object.keys(messages.de).sort(),Object.keys(messages.en).sort());
});
test('uncertain writes stay fenced until an explicit terminal operation read, without retry',async()=>{
 let value=fixture(),calls=0,status='outcome_unknown';
 const actions=createPersonaActions({unpack:async response=>({value:response}),read:async()=>value,inspect:async()=>({status}),invoke:async()=>{calls++;throw new TypeError('network ended');}});
 await actions.accept(value);await assert.rejects(actions.update({display_name:'New'}),{code:'outcome_unknown'});
 await assert.rejects(actions.update({display_name:'New'}),{code:'in_progress'});await assert.rejects(actions.refresh(),{code:'outcome_unknown'});assert.equal(calls,1);
 value={...value,version:'version-2'};status='succeeded';assert.equal((await actions.refresh()).value.version,'version-2');assert.equal(calls,1);
});
test('canonical version and a fresh operation ID accompany only the explicit changed fields',async()=>{
 let value=fixture(),requests=[];
 const actions=createPersonaActions({unpack:async response=>({value:response}),read:async()=>value,inspect:async()=>({status:'succeeded'}),invoke:async(action,args)=>{requests.push({action,args});return value={...value,version:'version-'+(requests.length+1),fields:{...value.fields,...args.changes}};}});
 await actions.accept(value);await actions.update({display_name:'Changed'});await actions.generateAvatar('Different face');
 assert.equal(requests[0].args.expected_version,'version-1');assert.equal(requests[1].args.expected_version,'version-2');assert.notEqual(requests[0].args.operation_id,requests[1].args.operation_id);
 assert.deepEqual(requests[0].args.changes,{display_name:'Changed'});assert.ok(!Object.hasOwn(requests[1].args,'changes'));assert.equal(value.fields.portrait_description,fixture().fields.portrait_description);
});
test('manifest hashes exact deterministic resource and common product source',async()=>{
 const path=new URL('../../../sonaloop/mcp_server/ui/persona.manifest.json',import.meta.url),before=await readFile(path);
 execFileSync(process.execPath,['build.mjs'],{cwd:new URL('..',import.meta.url)});const after=await readFile(path);assert.deepEqual(after,before);
 const manifest=JSON.parse(after),{build_id,...fields}=manifest;const sha=v=>createHash('sha256').update(v).digest('hex');assert.equal(build_id,sha(stableJSON(fields)));
 const html=await readFile(new URL('../../../sonaloop/mcp_server/ui/persona.html',import.meta.url));assert.equal(manifest.resource.sha256,sha(html));assert.equal(manifest.resource.bytes,html.length);
 for(const [path,hash]of Object.entries(manifest.sources))assert.equal(hash,sha(await readFile(new URL('../../../'+path,import.meta.url))));
 assert.ok(manifest.sources['sonaloop/web/assets/persona-view/persona-view.js']);
});
