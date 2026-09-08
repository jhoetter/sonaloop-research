import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir, readdir, rm } from 'node:fs/promises';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url)), repo = resolve(here, '../..');
const source = resolve(repo, 'sonaloop/web/assets/persona-view'), output = resolve(source, 'built'), resource = resolve(repo, 'sonaloop/mcp_server/ui');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key,item[key]])) : item);
await mkdir(output, { recursive: true }); await mkdir(resource, { recursive: true });
const bundle = async entry => (await build({ entryPoints: [resolve(source, entry)], bundle: true, minify: true, format: 'iife', target: ['es2022'], platform: 'browser', write: false, legalComments: 'none', charset: 'utf8', nodePaths: [resolve(here,'node_modules')] })).outputFiles[0].contents;
const product = await bundle('persona-product.js'), mcp = await bundle('persona-mcp.js'), style = await readFile(resolve(source,'persona-view.css'));
const scriptFile = `persona.${sha(product)}.js`, styleFile = `persona.${sha(style)}.css`;
for (const file of await readdir(output)) if (/^persona\.[a-f0-9]{64}\.(js|css)$/.test(file)) await rm(resolve(output,file));
await writeFile(resolve(output,scriptFile),product); await writeFile(resolve(output,styleFile),style);
const html = Buffer.from(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Research Persona</title><style>html{color-scheme:light dark}body{font:14px/1.5 var(--font-sans,system-ui,sans-serif);margin:0;padding:20px;background:var(--color-background-primary,#fff)}html[data-theme=dark]{--panel:#202328;--panel-2:#272b30;--ink:#ecedef;--muted:#aab0b5;--line:#3b4047;--accent:#9dbadf;--hover:#303741}@media(max-width:520px){body{padding:14px}}\n${style.toString().replace(/<\/style/gi,'<\\/style')}</style></head><body><main data-persona-app aria-live="polite"></main><script>${Buffer.from(mcp).toString().replace(/<\/script/gi,'<\\/script')}</script></body></html>\n`);
await writeFile(resolve(resource,'persona.html'),html);
const sources = {};
for (const file of [...(await readdir(source)).filter(file => /\.(js|css)$/.test(file)).map(file => resolve(source,file)), resolve(here,'build.mjs'), resolve(here,'package.json'), resolve(here,'package-lock.json'), resolve(repo,'sonaloop/persona_surface_contract.py')].sort()) sources[relative(repo,file)] = sha(await readFile(file));
const manifest = { schema_version:'sonaloop.customer-ui-build.v1', component_id:'sonaloop.research.persona-view', dto_schema_version:'sonaloop.persona-surface.v1',
 resource:{uri:'ui://sonaloop/persona/v1',mime:'text/html;profile=mcp-app',file:'persona.html',sha256:sha(html),bytes:html.byteLength}, sources,
 product:{script:{file:`persona-view/built/${scriptFile}`,sha256:sha(product)},style:{file:`persona-view/built/${styleFile}`,sha256:sha(style)}},
 fields:['display_name','age','location','role_title','goals','pain_points','portrait_description'],
 actions:['update_persona_surface','generate_persona_surface_avatar','get_persona_surface','get_persona_surface_operation'],
 states:['ready','editing','generating','error','conflict','outcome_unknown','readonly','missing_avatar','stale_avatar'],
 fallback:{kind:'text',description:'Canonical Research persona fields remain available as tool text for hosts without MCP Apps.'} };
manifest.build_id = sha(canonical(manifest));
await writeFile(resolve(resource,'persona.manifest.json'),`${canonical(manifest)}\n`);
console.log(JSON.stringify({ build_id:manifest.build_id, resource_sha256:manifest.resource.sha256, bytes:html.byteLength }));
