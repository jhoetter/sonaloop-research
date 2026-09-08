// Synthetic, transport-real customer UI qualification. Never invokes a native tool.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import { readFile, writeFile, mkdir, mkdtemp } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { build } from 'esbuild';
import { chromium } from 'playwright-core';

const execFile = promisify(execFileCallback);
export const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
export const browserExecutable = process.env.RESEARCH_BROWSER_EXECUTABLE || chromium.executablePath();
export const sha = bytes => createHash('sha256').update(bytes).digest('hex');
export const canonical = value => JSON.stringify(value, (_, item) =>
  item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const origin = 'http://127.0.0.1:17479'; // Intercepted entirely: no socket is bound.

const hostSource = `import {AppBridge,PostMessageTransport} from '@modelcontextprotocol/ext-apps/app-bridge';
const frame=document.querySelector('iframe'),seed=await(await fetch('/fixture/seed')).json();
const bridge=window.bridge=new AppBridge(null,{name:'Synthetic passive customer host',version:'1'},
  {logging:{}},{hostContext:{locale:seed.locale,theme:'light'}});
window.logs=[];window.calls=[];window.initialized=false;
bridge.onloggingmessage=value=>logs.push(value);
bridge.oncalltool=async value=>{calls.push(value);throw new Error('Fixture host grants no execution');};
bridge.onsizechange=({height})=>{frame.style.height=Math.max(100,Math.ceil(height))+'px';};
bridge.oninitialized=()=>{window.initialized=true;};
await bridge.connect(new PostMessageTransport(frame.contentWindow,frame.contentWindow));
frame.src='/fixture/app';`;
let hostBundlePromise;
async function hostBundle() {
  hostBundlePromise ||= build({ stdin: { contents: hostSource, resolveDir: resolve(repo, 'tools/persona-ui') },
    bundle: true, format: 'esm', write: false, target: 'es2022' }).then(value => value.outputFiles[0].text);
  return hostBundlePromise;
}

export async function loadAsset(family, { verifySources = false } = {}) {
  assert.match(family, /^[a-z]+$/);
  const manifestBytes = await readFile(resolve(repo, `sonaloop/mcp_server/ui/${family}.manifest.json`));
  const manifest = JSON.parse(manifestBytes);
  const resource = await readFile(resolve(repo, 'sonaloop/mcp_server/ui', manifest.resource.file));
  assert.equal(sha(resource), manifest.resource.sha256, 'Packaged resource digest');
  assert.equal(resource.length, manifest.resource.bytes, 'Packaged resource byte count');
  const { build_id, ...declaration } = manifest;
  assert.equal(sha(canonical(declaration)), build_id, 'Manifest build identity');
  assert.deepEqual(manifest.actions, [], 'Passive resource exposes no actions');
  if (verifySources) for (const [path, digest] of Object.entries(manifest.sources))
    assert.equal(sha(await readFile(resolve(repo, path))), digest, `Stale manifest source: ${path}`);
  return { manifest, manifestBytes, resource };
}

export async function launchBrowser() {
  return chromium.launch({ executablePath: browserExecutable, headless: true });
}

async function resourceWithLoggingFailure(resource) {
  // Opaque WindowProxy access bypasses a parent's postMessage monkey-patch.
  // Inject a single notification failure at the real SDK boundary instead. The
  // actual adapter, initialization, result notifications and bridge stay intact.
  // This fixture resource is never used by exportScenarios or bound to receipts.
  const sdk = fileURLToPath(import.meta.resolve('@modelcontextprotocol/ext-apps'));
  const injected = await build({ entryPoints: [resolve(repo, 'sonaloop/web/assets/research-view/research-mcp.js')],
    bundle: true, format: 'iife', write: false, target: 'es2022', plugins: [{ name: 'reject-log-notification',
      setup(plugin) {
        plugin.onResolve({ filter: /^@modelcontextprotocol\/ext-apps$/ }, () => ({ path: 'logging-failure', namespace: 'fixture' }));
        plugin.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ loader: 'js', resolveDir: dirname(sdk), contents:
          `import {App as NativeApp} from ${JSON.stringify(sdk)};
           export class App extends NativeApp {
             async notification(message, ...options) {
               if (message.method === 'notifications/message') {
                 globalThis.__loggingTransportFailures = (globalThis.__loggingTransportFailures || 0) + 1;
                 throw new Error('Synthetic logging transport failure');
               }
               return super.notification(message, ...options);
             }
           }` }));
      } }] });
  const script = injected.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
  return Buffer.from(resource.toString().replace(/<script>[\s\S]*<\/script>/, () => `<script>${script}</script>`));
}

export async function openApp(browser, { family = 'notes', locale = 'en',
  viewport = { width: 960, height: 900 }, deviceScaleFactor = 1, rejectLogging = false } = {}) {
  const asset = await loadAsset(family), bundle = await hostBundle();
  const resource = rejectLogging ? await resourceWithLoggingFailure(asset.resource) : asset.resource;
  const page = await browser.newPage({ viewport, deviceScaleFactor });
  page.setDefaultTimeout(7000);
  const errors = [], blockedRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { blockedRequests.push(url.href); return route.abort(); }
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body:
      `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><iframe title="Research ${family}" sandbox="allow-scripts" style="display:block;width:100%;border:0"></iframe><script type="module">${bundle}</script></body></html>` });
    if (url.pathname === '/fixture/seed') return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ locale }) });
    if (url.pathname === '/fixture/app') return route.fulfill({ contentType: 'text/html', body: resource,
      headers: { 'Content-Security-Policy': "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; form-action 'none'" } });
    blockedRequests.push(url.href);
    return route.abort();
  });
  await page.goto(origin);
  await page.waitForFunction(() => window.initialized);
  const frame = page.frameLocator('iframe'), root = frame.locator('[data-research-app]');
  return { page, frame, root, asset, errors, blockedRequests, injectedLoggingFailure: rejectLogging,
    async send(result, input = {}) {
      await page.evaluate(async ({ result, input }) => {
        await window.bridge.sendToolInput({ arguments: input });
        await window.bridge.sendToolResult(result);
      }, { result, input });
    },
    async rendered() { await page.waitForFunction(() => window.logs.some(log => log.data?.event === 'view-rendered')); },
    async assertPassive() {
      assert.deepEqual(await page.evaluate(() => window.calls), []);
      assert.deepEqual(errors, []);
      assert.deepEqual(blockedRequests, []);
      assert.equal(await root.locator('a,script,style,img,iframe,object,embed,svg,math,video,audio,form,input,button,select,textarea').count(), 0);
    } };
}

export function toolResult(html, { family = 'notes', state = 'ready', text = 'Synthetic fixture result', tool = 'list_notes' } = {}) {
  return { content: [{ type: 'text', text }], _meta: { 'sonaloop/presentation': {
    schema_version: 'sonaloop.research-presentation.v1', component_id: `sonaloop.research.${family}-view`,
    tool, state, html, text_sha256: sha(text),
  } } };
}

// Calls only the pure renderer using authored DTOs. No server build, Store, service,
// provider, native tool invocation or runtime dataset is involved.
const fixturePython = String.raw`
import json, sys
def audit(event, args):
    if event in {"sqlite3.connect", "socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("Fixture renderer attempted runtime access: " + event)
sys.addaudithook(audit)
from sonaloop.ui_components.registry import render_tool, SURFACES
from sonaloop.ui_components.library import note_content
from sonaloop.ui_components.discovery import project_heading, search_hit_content
from sonaloop.web._i18n import _UI_LANG
_UI_LANG.set("en")
note = {"id": "note_fixture", "kind": "observation", "title": "Handover needs a visible owner",
        "text": "The team loses context when a shift changes.\n\n**Observation:** a short summary helps the next person begin.\n\n- Show the current owner\n- Keep unresolved questions visible\n\n> Synthetic example for component review, not research evidence."}
section = {"id": "section_fixture", "title": "Handover observations", "note": "Two references, supplied by the fixture.",
           "member_ids": ["note:note_fixture", "note:note_second"]}
members = [{"id": "note_fixture", "kind": "note", "title": note["title"], "summary": "The next shift needs context and a named owner.", "href": "/notes/note_fixture"},
           {"id": "note_second", "kind": "note", "title": "Open questions remain visible", "summary": "Unresolved issues stay attached to the handover.", "href": "/notes/note_second"}]
project = {"id": "project_fixture", "title": "Understanding shift handovers",
           "goal": "Learn what the next shift needs to continue the work.",
           "description": "A synthetic project for shared component review."}
hit = {"id": "project:project_fixture", "title": project["title"], "text": project["goal"], "url": "/projects/project_fixture"}
fetched = {**hit, "text": "## Handover questions\n\nWhat context helps the next shift?\n\n- Who owns the open issue?\n- What has already been checked?\n\n**Fixture:** this is a readable example, not collected research.",
           "metadata": {"kind": "project"}}
specs = [
    ("notes-ready", "notes", "list_notes", {"project_id": "project_fixture"}, {"items": [note], "total": 1, "has_more": False}),
    ("notes-empty", "notes", "list_notes", {"project_id": "project_fixture"}, {"items": [], "total": 0, "has_more": False}),
    ("sections-ready", "sections", "get_section_members", {"section_id": "section_fixture"}, {"section": section, "members": members}),
    ("sections-empty", "sections", "list_sections", {"project_id": "project_fixture"}, []),
    ("sections-detail", "sections", "get_section", {"section_id": "section_fixture"}, section),
    ("projects-ready", "projects", "list_research_projects", {}, [project]),
    ("projects-empty", "projects", "list_research_projects", {}, []),
    ("projects-detail", "projects", "create_research_project", {key: project[key] for key in ("title", "goal", "description")}, project),
    ("search-ready", "search", "search", {"query": "handover"}, {"results": [hit]}),
    ("search-empty", "search", "search", {"query": "unmatched synthetic phrase"}, {"results": []}),
    ("search-detail", "search", "fetch", {"id": hit["id"]}, fetched),
]
output = []
for scenario, family, tool, arguments, data in specs:
    envelope = data if tool in {"search", "fetch"} else {"tool": tool, "data": data}
    html, state = render_tool(tool, envelope)
    output.append(dict(scenario=scenario, family=family, tool=tool, input=arguments, native=envelope,
                       html=str(html), state=state, note_content=str(note_content(note)),
                       project_heading=str(project_heading(project, level="h2")),
                       search_hit_content=str(search_hit_content(hit["title"], hit["text"])),
                       fetched_content=str(note_content(fetched))))
declarations = [dict(tool=name, componentId=surface.component_id, resourceUri=surface.uri)
                for name, surface in sorted(SURFACES.items())]
print(json.dumps(dict(fixtures=output, declarations=declarations)))
`;

export async function nativeFixtureSet() {
  const python = process.env.RESEARCH_TEST_PYTHON || 'python3';
  const { stdout } = await execFile(python, ['-B', '-c', fixturePython], { cwd: repo,
    env: { PATH: process.env.PATH || '', PYTHONPATH: repo, PYTHONDONTWRITEBYTECODE: '1', LANG: 'C.UTF-8' },
    maxBuffer: 1024 * 1024 });
  const { fixtures, declarations } = JSON.parse(stdout);
  return { declarations, fixtures: fixtures.map(value => ({ ...value,
    result: { ...toolResult(value.html, { ...value, text: canonical(value.native) }), structuredContent: value.native } })) };
}

export async function nativeFixtures() {
  return (await nativeFixtureSet()).fixtures;
}

export function pngDimensions(png) {
  assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(png.subarray(12, 16).toString(), 'IHDR');
  return { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
}

export async function exportScenarios(outputParent = process.env.RESEARCH_SCENARIO_OUTPUT || resolve(tmpdir(), 'sonaloop-research-ui-scenarios')) {
  await mkdir(outputParent, { recursive: true });
  const output = await mkdtemp(resolve(outputParent, 'run-'));
  const { fixtures, declarations } = await nativeFixtureSet();
  const failed = { ...fixtures[0], scenario: 'notes-error', state: 'unavailable',
    result: { isError: true, content: [{ type: 'text', text: 'Synthetic native tool failure; no operation was invoked.' }] } };
  const scenarios = [...fixtures, failed].map(fixture => ({ fixture, viewport: { width: 390, height: 844 } }));
  scenarios.unshift({ fixture: fixtures[0], viewport: { width: 960, height: 900 } });
  const rendererBytes = await readFile(fileURLToPath(import.meta.url)), bundle = await hostBundle();
  const { stdout: commit } = await execFile('git', ['rev-parse', 'HEAD'], { cwd: repo });
  const { stdout: dirty } = await execFile('git', ['status', '--porcelain'], { cwd: repo });
  const browser = await launchBrowser();
  const rendererBuild = { harnessSha256: sha(rendererBytes), bridgeBundleSha256: sha(bundle),
    executableSha256: sha(await readFile(browserExecutable)), browserVersion: browser.version() };
  const receipts = [];
  try {
    for (const { fixture, viewport } of scenarios) {
      const asset = await loadAsset(fixture.family, { verifySources: true });
      const session = await openApp(browser, { family: fixture.family, viewport });
      try {
        assert.equal(session.asset.manifest.build_id, asset.manifest.build_id, 'Resource remained stable during capture');
        await session.send(fixture.result, fixture.input);
        if (fixture.state === 'unavailable') await session.root.getByText('This view is unavailable.', { exact: false }).waitFor();
        else await session.rendered();
        await session.assertPassive();
        assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth), 'No horizontal overflow');
        await session.frame.locator('body').evaluate(async () => { await document.fonts.ready; await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); });
        const box = await session.root.boundingBox();
        assert.ok(box && box.width > 0 && box.height > 0);
        const crop = { x: Math.floor(box.x), y: Math.floor(box.y), width: Math.ceil(box.x + box.width) - Math.floor(box.x), height: Math.ceil(box.y + box.height) - Math.floor(box.y) };
        assert.ok(crop.x + crop.width <= viewport.width && crop.y + crop.height <= viewport.height, 'Full component fits the captured viewport');
        const png = await session.page.screenshot({ type: 'png', clip: crop, animations: 'disabled' });
        const dimensions = pngDimensions(png);
        assert.equal(dimensions.width, crop.width);
        assert.equal(dimensions.height, crop.height);
        assert.ok(png.length <= 2 * 1024 * 1024 && dimensions.width * dimensions.height <= 4 * 1024 * 1024);
        assert.ok(dimensions.width <= 4096 && dimensions.height <= 4096);
        const name = `${fixture.scenario}-${viewport.width}`, directory = resolve(output, name);
        await mkdir(directory);
        const input = canonical(fixture.input), result = canonical(fixture.result);
        const receipt = { schemaVersion: 'sonaloop.customer-ui-scenario-render.v1',
          componentId: asset.manifest.component_id, buildId: asset.manifest.build_id,
          manifestSha256: sha(asset.manifestBytes), resourceUri: asset.manifest.resource.uri,
          resourceSha256: sha(asset.resource), source: { commit: commit.trim(), dirty: Boolean(dirty),
            sourcesSha256: sha(canonical(asset.manifest.sources)), files: asset.manifest.sources },
          scenario: fixture.scenario, state: fixture.state, mode: 'tool_result', dataKind: 'synthetic_fixture',
          tool: fixture.tool, inputSha256: sha(input), resultSha256: sha(result),
          renderer: { name: 'Playwright Chromium MCP Apps fixture', version: browser.version(), buildSha256: sha(canonical(rendererBuild)) },
          rendererBuild, capturedAt: new Date().toISOString(), viewport: { ...viewport, deviceScaleFactor: 1 }, crop,
          image: { mediaType: 'image/png', sha256: sha(png), bytes: png.length, ...dimensions },
          files: { image: 'view.png', manifest: 'manifest.json', resource: 'resource.html', input: 'input.json', result: 'result.json', renderer: 'renderer.mjs', bridge: 'host.bundle.js' },
          checks: { protocol: 'MCP Apps AppBridge', passive: true, nativeToolCalls: 0, providerCalls: 0,
            runtimeVerification: 'not_asserted', humanAcceptance: 'not_asserted' } };
        await Promise.all([
          writeFile(resolve(directory, 'view.png'), png), writeFile(resolve(directory, 'manifest.json'), asset.manifestBytes),
          writeFile(resolve(directory, 'resource.html'), asset.resource), writeFile(resolve(directory, 'input.json'), input),
          writeFile(resolve(directory, 'result.json'), result), writeFile(resolve(directory, 'renderer.mjs'), rendererBytes),
          writeFile(resolve(directory, 'host.bundle.js'), bundle), writeFile(resolve(directory, 'receipt.json'), `${canonical(receipt)}\n`),
        ]);
        receipts.push({ directory, receiptSha256: sha(`${canonical(receipt)}\n`), ...receipt });
      } finally { await session.page.close(); }
    }
    const declaredTools = { source: 'sonaloop/ui_components/registry.py:SURFACES',
      count: declarations.length, declarations };
    await writeFile(resolve(output, 'index.json'), `${canonical({ dataKind: 'synthetic_fixture', declaredTools, scenarios: receipts })}\n`);
    return { output, declaredTools, scenarios: receipts.map(({ directory, image, state, tool }) => ({ directory, image, state, tool })) };
  } finally { await browser.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const report = await exportScenarios(process.argv[2]);
  const stdout = `${JSON.stringify(report, null, 2)}\n`;
  await writeFile(resolve(report.output, 'stdout.json'), stdout);
  process.stdout.write(stdout);
}
