import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { componentSourceHashes, familySourceInputs } from './research-source-inputs.mjs';
const here = dirname(fileURLToPath(import.meta.url)), repo = resolve(here, '../..');
const source = resolve(repo, 'sonaloop/web/assets/research-view'), resource = resolve(repo, 'sonaloop/mcp_server/ui');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key,item[key]])) : item);
const script = (await build({ entryPoints:[resolve(source,'research-mcp.js')], bundle:true, minify:true, format:'iife', target:['es2022'], platform:'browser', write:false, legalComments:'none', charset:'utf8', nodePaths:[resolve(here,'node_modules')] })).outputFiles[0].contents;
const style = await readFile(resolve(source,'research.css'));
// Resolve every declared source before writing any resource. Unknown/missing or
// over-budget ownership fails the build instead of emitting partial manifests.
const sourceHashes = Object.fromEntries(await Promise.all(Object.keys(familySourceInputs).map(async family =>
  [family, await componentSourceHashes(repo, family)])));
await mkdir(resource,{recursive:true});
for (const [family,fields] of [['notes',['title','text','kind']],['sections',['title','note','kind','member_ids','members']],['projects',['title','goal','description']],['search',['title','text']],['hypotheses',['text','status','prediction','result','drop_note','derived_from']],['decisions',['title','status','decision','based_on','rejected','superseded_by','supersedes']],['surveys',['title','intro','status','questions','response_count','responses','derived_from','survey_id','imported','total_responses']],['syntheses',['id','title','scope','status','created_at','goal','start_input','gesamtbild','positionierung','arc_narrative','next_council_question','stop_reason','iterations','council_ids','references','citations','statements','findings','prompts','lead','sections','limitations','claim_posture','graph_snapshot']],['sessions',['id','persona_id','subject','fidelity','date','steps','outcome','statements','grounded_verified','reaction','prototype_id','prototype_version','observed_state_refs','rows','sessions','completed','flow','biggest_dropoff']],['councils',['prompt','persona_ids','created_at','summary','exec_summary','proposal','selection_reason','statements','prompts','findings','claim_posture','head_to_head','red_team','personas','turns','votes']]]) {
  const component = `sonaloop.research.${family}-view`, sources = sourceHashes[family];
  if (!sources) throw new Error(`Missing source ownership for ${family}`);
  const html = Buffer.from(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="sonaloop-component" content="${component}"><title>Research ${family}</title><style>html{color-scheme:light dark}body{font:14px/1.5 system-ui,sans-serif;margin:0;padding:16px;background:var(--panel,#fff)}html[data-theme=dark]{--panel:#202823;--panel-2:#29332c;--ink:#eaf1ec;--muted:#b1bfb5;--line:#4c6053}${style.toString().replace(/<\/style/gi,'<\\/style')}</style></head><body><main data-research-app aria-live="polite"></main><script>${Buffer.from(script).toString().replace(/\n[ \t]+\n/g,'\n\n').replace(/<\/script/gi,'<\\/script')}</script></body></html>\n`);
  await writeFile(resolve(resource,`${family}.html`),html);
  const manifest = {schema_version:'sonaloop.customer-ui-build.v1',component_id:component,dto_schema_version:'sonaloop.research-presentation.v1',resource:{uri:`ui://sonaloop/${family}/v1`,mime:'text/html;profile=mcp-app',file:`${family}.html`,sha256:sha(html),bytes:html.byteLength},sources,product:{style:{file:'research-view/research.css',sha256:sha(style)}},fields,actions:[],states:['loading','ready','empty','unavailable'],fallback:{kind:'text',description:'Unchanged native tool text and structured output remain available in hosts without MCP Apps.'}};
  manifest.build_id=sha(canonical(manifest));
  await writeFile(resolve(resource,`${family}.manifest.json`),`${canonical(manifest)}\n`);
  console.log(JSON.stringify({family,build_id:manifest.build_id,resource_sha256:manifest.resource.sha256,bytes:html.byteLength}));
}
