// Authored Persona DTOs through the real MCP Apps bridge; no native service runs.
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
import { fixture } from './fixture.mjs';

const execFile = promisify(execFileCallback);
const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const origin = 'http://127.0.0.1:17481'; // All routes intercepted; no port is bound.
const browserExecutable = process.env.RESEARCH_BROWSER_EXECUTABLE || chromium.executablePath();
export const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
export const sha = bytes => createHash('sha256').update(bytes).digest('hex');

export function personaScenario() {
  const value = fixture();
  value.fields.display_name = 'Mira Chen';
  return { scenario: 'persona-ready-placeholder', state: 'ready', tool: 'get_persona_surface',
    input: { persona_id: value.persona_id }, result: {
      content: [{ type: 'text', text: canonical(value) }], structuredContent: value,
    } };
}

const hostSource = `import {AppBridge,PostMessageTransport} from '@modelcontextprotocol/ext-apps/app-bridge';
const frame=document.querySelector('iframe'),seed=await(await fetch('/fixture/seed')).json();
const bridge=window.bridge=new AppBridge(null,{name:'Synthetic Persona capture host',version:'1'},
  {serverTools:{},logging:{}},{hostContext:{locale:'en',theme:'light'}});
window.logs=[];window.calls=[];window.initialized=false;
bridge.onloggingmessage=value=>logs.push(value);
bridge.oncalltool=async request=>{
  if(request.name!=='get_persona_surface'||JSON.stringify(request.arguments)!==JSON.stringify(seed.input)) {
    calls.push({request,rejected:true});throw new Error('Fixture host permits only the exact simulated refresh');
  }
  const result=structuredClone(seed.result);calls.push({request,result});return result;
};
bridge.onsizechange=({height})=>{frame.style.height=Math.max(100,Math.ceil(height))+'px';};
bridge.oninitialized=()=>{window.initialized=true;};
await bridge.connect(new PostMessageTransport(frame.contentWindow,frame.contentWindow));frame.src='/fixture/app';`;

async function loadAsset() {
  const manifestBytes = await readFile(resolve(repo, 'sonaloop/mcp_server/ui/persona.manifest.json'));
  const manifest = JSON.parse(manifestBytes);
  const resource = await readFile(resolve(repo, 'sonaloop/mcp_server/ui', manifest.resource.file));
  assert.equal(sha(resource), manifest.resource.sha256, 'Packaged Persona resource digest');
  assert.equal(resource.length, manifest.resource.bytes);
  const { build_id, ...declaration } = manifest;
  assert.equal(sha(canonical(declaration)), build_id, 'Manifest build identity');
  assert.equal(manifest.component_id, 'sonaloop.research.persona-view');
  assert.equal(manifest.resource.uri, 'ui://sonaloop/persona/v1');
  assert.ok(manifest.states.includes('ready'));
  for (const [path, digest] of Object.entries(manifest.sources))
    assert.equal(sha(await readFile(resolve(repo, path))), digest, `Stale source: ${path}`);
  return { manifest, manifestBytes, resource };
}

async function sourceIdentity() {
  const { stdout: commit } = await execFile('git', ['rev-parse', 'HEAD'], { cwd: repo });
  const { stdout: dirty } = await execFile('git', ['status', '--porcelain'], { cwd: repo });
  return { commit: commit.trim(), dirty: Boolean(dirty) };
}

async function capture(browser, asset, bundle, scenario, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  page.setDefaultTimeout(7000);
  const errors = [], blockedRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === origin && url.pathname === '/') return route.fulfill({ contentType: 'text/html', body:
      `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><iframe title="Persona" sandbox="allow-scripts" style="display:block;width:100%;border:0"></iframe><script type="module">${bundle}</script></body></html>` });
    if (url.origin === origin && url.pathname === '/fixture/seed') return route.fulfill({ contentType: 'application/json', body: canonical(scenario) });
    if (url.origin === origin && url.pathname === '/fixture/app') return route.fulfill({ contentType: 'text/html', body: asset.resource,
      headers: { 'Content-Security-Policy': "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'" } });
    blockedRequests.push(url.href);
    return route.abort();
  });
  try {
    await page.goto(origin);
    await page.waitForFunction(() => window.initialized);
    await page.evaluate(async ({ input, result }) => {
      await window.bridge.sendToolInput({ arguments: input });
      await window.bridge.sendToolResult(result);
    }, scenario);
    await page.waitForFunction(() => window.logs.some(log => log.data?.event === 'view-rendered' && !log.data.mode));
    const frame = page.frameLocator('iframe'), card = frame.locator('.sl-persona-view');
    assert.equal(await card.getAttribute('data-mode'), 'persisted');
    assert.equal(await card.getAttribute('aria-busy'), 'false');
    await card.locator('summary').click();
    await card.locator('details[open]').waitFor();
    for (const [field, expected] of Object.entries(scenario.result.structuredContent.fields)) {
      const content = card.locator(`[data-persona-field="${field}"] .sl-persona-view__field-value`);
      assert.ok(await content.isVisible(), `Full card exposes ${field}`);
      assert.equal((await content.innerText()).trim(), Array.isArray(expected) ? expected.join('\n') : String(expected));
    }
    assert.equal(await card.locator('img').count(), 0, 'The fixture uses the native placeholder');
    assert.equal(await card.locator('form,dialog').count(), 0, 'No editor or generation action was opened');
    assert.equal(await card.getByRole('alert').count(), 0);
    assert.equal(await card.locator('[data-field]:enabled').count(), 7, 'Canonical capabilities remain intact');
    assert.ok(await frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth), 'No horizontal overflow');
    await card.evaluate(async () => { await document.fonts.ready; await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); });
    const calls = await page.evaluate(() => window.calls);
    assert.equal(calls.length, 1, 'The existing adapter performs exactly one simulated refresh');
    assert.equal(calls[0].request.name, 'get_persona_surface');
    assert.deepEqual(calls[0].request.arguments, scenario.input);
    assert.deepEqual(calls[0].result, scenario.result, 'The simulated refresh returns the unchanged canonical result');
    assert.deepEqual(errors, []);
    assert.deepEqual(blockedRequests, [], 'No backend, provider or external resource was requested');
    const box = await card.boundingBox();
    assert.ok(box && box.width > 0 && box.height > 0);
    const crop = { x: Math.floor(box.x), y: Math.floor(box.y), width: Math.ceil(box.x + box.width) - Math.floor(box.x), height: Math.ceil(box.y + box.height) - Math.floor(box.y) };
    assert.ok(crop.x + crop.width <= viewport.width && crop.y + crop.height <= viewport.height, 'Full card fits the viewport');
    const png = await page.screenshot({ type: 'png', clip: crop, animations: 'disabled' });
    const dimensions = { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
    assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    assert.equal(dimensions.width, crop.width);
    assert.equal(dimensions.height, crop.height);
    assert.ok(png.length <= 2 * 1024 * 1024 && dimensions.width * dimensions.height <= 4 * 1024 * 1024);
    assert.ok(dimensions.width <= 4096 && dimensions.height <= 4096);
    return { png, dimensions, crop, calls };
  } finally { await page.close(); }
}

export async function exportPersonaScenarios(outputParent = resolve(tmpdir(), 'sonaloop-persona-ui-scenarios'), { allowDirty = false } = {}) {
  const source = await sourceIdentity();
  assert.ok(allowDirty || !source.dirty, 'Final Persona export requires a clean source checkout');
  const asset = await loadAsset(), scenario = personaScenario();
  const rendererBytes = await readFile(fileURLToPath(import.meta.url));
  const fixtureBytes = await readFile(new URL('./fixture.mjs', import.meta.url));
  const bundle = (await build({ stdin: { contents: hostSource, resolveDir: resolve(repo, 'tools/persona-ui') },
    bundle: true, format: 'esm', write: false, target: 'es2022' })).outputFiles[0].text;
  await mkdir(outputParent, { recursive: true });
  const output = await mkdtemp(resolve(outputParent, 'run-'));
  const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
  const rendererBuild = { harnessSha256: sha(rendererBytes), fixtureSha256: sha(fixtureBytes),
    bridgeBundleSha256: sha(bundle), executableSha256: sha(await readFile(browserExecutable)), browserVersion: browser.version() };
  const receipts = [];
  try {
    for (const viewport of [{ width: 960, height: 1000 }, { width: 390, height: 1000 }]) {
      const { png, dimensions, crop, calls } = await capture(browser, asset, bundle, scenario, viewport);
      const directory = resolve(output, `${scenario.scenario}-${viewport.width}`);
      await mkdir(directory);
      const input = canonical(scenario.input), result = canonical(scenario.result), transcript = canonical(calls);
      const receipt = { schemaVersion: 'sonaloop.customer-ui-scenario-render.v1', componentId: asset.manifest.component_id,
        buildId: asset.manifest.build_id, manifestSha256: sha(asset.manifestBytes), resourceUri: asset.manifest.resource.uri,
        resourceSha256: sha(asset.resource), source: { ...source, sourcesSha256: sha(canonical(asset.manifest.sources)), files: asset.manifest.sources },
        scenario: scenario.scenario, state: scenario.state, mode: 'tool_result', dataKind: 'synthetic_fixture', tool: scenario.tool,
        inputSha256: sha(input), resultSha256: sha(result),
        renderer: { name: 'Playwright Chromium MCP Apps fixture', version: browser.version(), buildSha256: sha(canonical(rendererBuild)) },
        rendererBuild, capturedAt: new Date().toISOString(), viewport: { ...viewport, deviceScaleFactor: 1 }, crop,
        image: { mediaType: 'image/png', sha256: sha(png), bytes: png.length, ...dimensions },
        presentation: { avatar: 'native_placeholder', details: 'expanded', steps: [{ action: 'click', target: '.sl-persona-view details > summary' }] },
        simulatedMcp: { calls: calls.length, transcriptSha256: sha(transcript), response: 'same_canonical_fixture_result' },
        files: { image: 'view.png', manifest: 'manifest.json', resource: 'resource.html', input: 'input.json', result: 'result.json',
          renderer: 'renderer.mjs', fixture: 'fixture.mjs', bridge: 'host.bundle.js', simulatedMcp: 'simulated-mcp.json' },
        checks: { protocol: 'MCP Apps AppBridge', nativeToolCalls: 0, providerCalls: 0, simulatedMcpCalls: calls.length,
          simulatedWriteCalls: 0, runtimeVerification: 'not_asserted', humanAcceptance: 'not_asserted' } };
      const receiptBytes = `${canonical(receipt)}\n`;
      await Promise.all(Object.entries({ 'view.png': png, 'manifest.json': asset.manifestBytes, 'resource.html': asset.resource,
        'input.json': input, 'result.json': result, 'renderer.mjs': rendererBytes, 'fixture.mjs': fixtureBytes,
        'host.bundle.js': bundle, 'simulated-mcp.json': transcript, 'receipt.json': receiptBytes })
        .map(([name, bytes]) => writeFile(resolve(directory, name), bytes)));
      receipts.push({ directory, receiptSha256: sha(receiptBytes), ...receipt });
    }
    const finalSource = await sourceIdentity();
    assert.equal(finalSource.commit, source.commit, 'Source commit remained stable during capture');
    assert.ok(allowDirty || !finalSource.dirty, 'Final Persona export remained clean');
    assert.equal(sha(await readFile(fileURLToPath(import.meta.url))), rendererBuild.harnessSha256);
    assert.equal(sha(await readFile(new URL('./fixture.mjs', import.meta.url))), rendererBuild.fixtureSha256);
    assert.equal((await loadAsset()).manifest.build_id, asset.manifest.build_id);
    await writeFile(resolve(output, 'index.json'), `${canonical({ dataKind: 'synthetic_fixture', scenarios: receipts })}\n`);
    return { output, scenarios: receipts.map(({ directory, image, state, tool, receiptSha256 }) => ({ directory, image, state, tool, receiptSha256 })) };
  } finally { await browser.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const report = await exportPersonaScenarios(process.argv[2]);
  const stdout = `${JSON.stringify(report, null, 2)}\n`;
  await writeFile(resolve(report.output, 'stdout.json'), stdout);
  process.stdout.write(stdout);
}
