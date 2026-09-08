import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url)), repo = resolve(here, '../..');
const source = resolve(repo, 'sonaloop/web/assets/research-view'), resource = resolve(repo, 'sonaloop/mcp_server/ui');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key,item[key]])) : item);
const script = (await build({ entryPoints:[resolve(source,'research-mcp.js')], bundle:true, minify:true, format:'iife', target:['es2022'], platform:'browser', write:false, legalComments:'none', charset:'utf8', nodePaths:[resolve(here,'node_modules')] })).outputFiles[0].contents;
const style = await readFile(resolve(source,'research.css'));
const sources = {};
const sourceFiles = [...(await readdir(source)).map(file => resolve(source,file)), ...(await readdir(resolve(repo,'sonaloop/ui_components'))).filter(file => /\.(py|json)$/.test(file)).map(file => resolve(repo,'sonaloop/ui_components',file)), resolve(repo,'sonaloop/mcp_server/_research_ui.py'), resolve(repo,'sonaloop/web/pages/library.py'), resolve(repo,'sonaloop/web/pages/projects.py'), resolve(repo,'sonaloop/web/_routes_api.py'), resolve(repo,'sonaloop/web/_palette.py'), resolve(repo,'sonaloop/web/_html.py'), resolve(repo,'sonaloop/web/_i18n.py'), resolve(repo,'sonaloop/web/_i18n_strings.py'), resolve(repo,'sonaloop/web/_components.py'), resolve(here,'build-research.mjs'), resolve(here,'package.json'), resolve(here,'package-lock.json')];
sourceFiles.push(...['sonaloop/web/pages/hypotheses.py','sonaloop/web/pages/decisions.py','sonaloop/web/_render.py','sonaloop/web/_presence.py','sonaloop/web/ui.py','sonaloop/artifacts.py'].map(file => resolve(repo,file)));
for (const file of sourceFiles.sort()) sources[relative(repo,file)] = sha(await readFile(file));
await mkdir(resource,{recursive:true});
for (const [family,fields] of [['notes',['title','text','kind']],['sections',['title','note','kind','member_ids','members']],['projects',['title','goal','description']],['search',['title','text']],['hypotheses',['text','status','prediction','result','drop_note','derived_from']],['decisions',['title','status','decision','based_on','rejected','superseded_by','supersedes']]]) {
  const component = `sonaloop.research.${family}-view`;
  const html = Buffer.from(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="sonaloop-component" content="${component}"><title>Research ${family}</title><style>html{color-scheme:light dark}body{font:14px/1.5 system-ui,sans-serif;margin:0;padding:16px;background:var(--panel,#fff)}html[data-theme=dark]{--panel:#202823;--panel-2:#29332c;--ink:#eaf1ec;--muted:#b1bfb5;--line:#4c6053}${style.toString().replace(/<\/style/gi,'<\\/style')}</style></head><body><main data-research-app aria-live="polite"></main><script>${Buffer.from(script).toString().replace(/\n[ \t]+\n/g,'\n\n').replace(/<\/script/gi,'<\\/script')}</script></body></html>\n`);
  await writeFile(resolve(resource,`${family}.html`),html);
  const manifest = {schema_version:'sonaloop.customer-ui-build.v1',component_id:component,dto_schema_version:'sonaloop.research-presentation.v1',resource:{uri:`ui://sonaloop/${family}/v1`,mime:'text/html;profile=mcp-app',file:`${family}.html`,sha256:sha(html),bytes:html.byteLength},sources,product:{style:{file:'research-view/research.css',sha256:sha(style)}},fields,actions:[],states:['loading','ready','empty','unavailable'],fallback:{kind:'text',description:'Unchanged native tool text and structured output remain available in hosts without MCP Apps.'}};
  manifest.build_id=sha(canonical(manifest));
  await writeFile(resolve(resource,`${family}.manifest.json`),`${canonical(manifest)}\n`);
  console.log(JSON.stringify({family,build_id:manifest.build_id,resource_sha256:manifest.resource.sha256,bytes:html.byteLength}));
}
