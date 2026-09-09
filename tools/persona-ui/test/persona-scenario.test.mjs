import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { exportPersonaScenarios, exportPersonaComponentScenarios, personaScenario, canonical, sha } from './persona-scenario-browser.mjs';
import { personaComponentScenario } from './persona-component-fixtures.mjs';

test('Persona full-card PNGs and standalone receipts bind the real bridge and exact simulated canonical refresh', { timeout: 30000 }, async () => {
  const parent = await mkdtemp(resolve(tmpdir(), 'persona-scenario-test-'));
  try {
    const report = await exportPersonaScenarios(parent, { allowDirty: true });
    const index = JSON.parse(await readFile(resolve(report.output, 'index.json')));
    assert.equal(index.dataKind, 'synthetic_fixture');
    assert.equal(index.scenarios.length, 2);
    assert.deepEqual(index.scenarios.map(item => item.viewport.width), [960, 390]);
    for (const { directory, receiptSha256 } of index.scenarios) {
      const receiptBytes = await readFile(resolve(directory, 'receipt.json'));
      assert.equal(sha(receiptBytes), receiptSha256);
      const receipt = JSON.parse(receiptBytes);
      const files = Object.fromEntries(await Promise.all(Object.entries(receipt.files)
        .map(async ([key, file]) => [key, await readFile(resolve(directory, file))])));
      const manifest = JSON.parse(files.manifest), result = JSON.parse(files.result), input = JSON.parse(files.input);
      assert.equal(receipt.schemaVersion, 'sonaloop.customer-ui-scenario-render.v1');
      assert.equal(receipt.dataKind, 'synthetic_fixture');
      assert.equal(receipt.mode, 'tool_result');
      assert.equal(receipt.state, 'ready');
      assert.ok(manifest.states.includes(receipt.state));
      assert.equal(receipt.componentId, manifest.component_id);
      assert.equal(receipt.buildId, manifest.build_id);
      assert.equal(receipt.resourceUri, manifest.resource.uri);
      assert.equal(sha(files.manifest), receipt.manifestSha256);
      assert.equal(sha(files.resource), receipt.resourceSha256);
      assert.equal(receipt.resourceSha256, manifest.resource.sha256);
      assert.equal(sha(canonical(input)), receipt.inputSha256);
      assert.equal(sha(canonical(result)), receipt.resultSha256);
      assert.deepEqual(result, personaScenario().result);
      assert.equal(result.structuredContent.avatar.state, 'missing');
      assert.equal(result.structuredContent.capabilities.edit.length, 7);
      const calls = JSON.parse(files.simulatedMcp);
      assert.equal(calls.length, 1);
      assert.equal(calls[0].request.name, receipt.tool);
      assert.deepEqual(calls[0].request.arguments, input);
      assert.deepEqual(calls[0].result, result);
      assert.ok(['string', 'number'].includes(typeof calls[0].request._meta?.progressToken), 'SDK request metadata is retained in the transcript');
      assert.equal(sha(files.simulatedMcp), receipt.simulatedMcp.transcriptSha256);
      assert.equal(receipt.simulatedMcp.calls, 1);
      assert.equal(receipt.checks.nativeToolCalls, 0);
      assert.equal(receipt.checks.providerCalls, 0);
      assert.equal(receipt.checks.simulatedWriteCalls, 0);
      assert.equal(receipt.checks.runtimeVerification, 'not_asserted');
      assert.equal(receipt.checks.humanAcceptance, 'not_asserted');
      assert.equal(receipt.presentation.avatar, 'native_placeholder');
      assert.equal(receipt.presentation.details, 'expanded');
      assert.match(receipt.source.commit, /^[a-f0-9]{40}$/);
      assert.equal(typeof receipt.source.dirty, 'boolean');
      assert.equal(sha(canonical(manifest.sources)), receipt.source.sourcesSha256);
      assert.deepEqual(receipt.source.files, manifest.sources);
      assert.equal(sha(files.renderer), receipt.rendererBuild.harnessSha256);
      assert.equal(sha(files.fixture), receipt.rendererBuild.fixtureSha256);
      assert.equal(sha(files.bridge), receipt.rendererBuild.bridgeBundleSha256);
      assert.equal(sha(canonical(receipt.rendererBuild)), receipt.renderer.buildSha256);
      assert.match(receipt.rendererBuild.executableSha256, /^[a-f0-9]{64}$/);
      assert.equal(receipt.renderer.version, receipt.rendererBuild.browserVersion);
      assert.ok(Number.isFinite(Date.parse(receipt.capturedAt)));
      assert.equal(sha(files.image), receipt.image.sha256);
      assert.equal(files.image.length, receipt.image.bytes);
      assert.equal(files.image.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
      assert.equal(files.image.subarray(12, 16).toString(), 'IHDR');
      const dimensions = { width: files.image.readUInt32BE(16), height: files.image.readUInt32BE(20) };
      assert.deepEqual(dimensions, { width: receipt.image.width, height: receipt.image.height });
      assert.equal(dimensions.width, receipt.crop.width * receipt.viewport.deviceScaleFactor);
      assert.equal(dimensions.height, receipt.crop.height * receipt.viewport.deviceScaleFactor);
      for (const value of Object.values(receipt.crop)) assert.ok(Number.isInteger(value) && value >= 0);
      assert.ok(receipt.crop.x + receipt.crop.width <= receipt.viewport.width);
      assert.ok(receipt.crop.y + receipt.crop.height <= receipt.viewport.height);
      assert.ok(receipt.crop.width >= 300 && receipt.crop.height >= 300, 'Full card, not a portrait crop');
      assert.ok(files.image.length <= 2 * 1024 * 1024 && dimensions.width * dimensions.height <= 4 * 1024 * 1024);
      assert.ok(dimensions.width <= 4096 && dimensions.height <= 4096);
    }
  } finally { await rm(parent, { recursive: true, force: true }); }
});

test('Fresh public Persona PNGs bind exact declared props, direct entry and real AppBridge DOM equality', { timeout: 30000 }, async () => {
  const parent = await mkdtemp(resolve(tmpdir(), 'persona-public-scenario-test-'));
  try {
    const report = await exportPersonaComponentScenarios(parent, { allowDirty: true });
    const index = JSON.parse(await readFile(resolve(report.output, 'index.json')));
    assert.equal(index.scenarios.length, 2);
    for (const item of index.scenarios) {
      const receiptBytes = await readFile(resolve(item.directory, 'receipt.json'));
      assert.equal(sha(receiptBytes), item.receiptSha256);
      const receipt = JSON.parse(receiptBytes), proof = receipt.publicComponent;
      const files = Object.fromEntries(await Promise.all(Object.entries(receipt.files)
        .map(async ([key, file]) => [key, await readFile(resolve(item.directory, file))])));
      const declaration = JSON.parse(files.declaration), props = JSON.parse(files.props), result = JSON.parse(files.result);
      assert.equal(receipt.scenario, personaComponentScenario().scenario);
      assert.notEqual(receipt.scenario, personaScenario().scenario, 'Old evidence is never relabeled');
      assert.equal(receipt.state, 'ready');
      assert.equal(receipt.dataKind, 'synthetic_fixture');
      assert.equal(receipt.mode, 'tool_result');
      assert.equal(receipt.tool, 'get_persona_surface');
      assert.equal(proof.scenarioId, receipt.scenario);
      assert.deepEqual(declaration.scenarios.find(item => item.id === proof.scenarioId).props, props);
      assert.deepEqual(props.value, result.structuredContent);
      assert.deepEqual(result, personaComponentScenario().result);
      assert.deepEqual(JSON.parse(files.input), { persona_id: props.value.persona_id });
      assert.equal(sha(files.declaration), proof.declarationSha256);
      assert.equal(sha(files.props), proof.propsSha256);
      assert.equal(sha(canonical(result)), receipt.resultSha256);
      assert.equal(sha(files.manifest), receipt.manifestSha256);
      assert.equal(sha(files.resource), receipt.resourceSha256);
      assert.equal(sha(files.publicEntry), receipt.rendererBuild.publicEntrySha256);
      assert.equal(sha(files.publicBundle), receipt.rendererBuild.publicBundleSha256);
      assert.equal(sha(files.fixture), receipt.rendererBuild.fixtureSha256);
      assert.equal(sha(canonical(receipt.rendererBuild)), receipt.renderer.buildSha256);
      assert.deepEqual(files.publicDom, files.appDom);
      assert.equal(sha(files.publicDom), proof.domSha256);
      assert.equal(proof.equivalence, 'exact_outerHTML');
      assert.equal(proof.entryPoint.exportName, 'createPersonaFromProps');
      const manifest = JSON.parse(files.manifest);
      assert.equal(manifest.sources[proof.entryPoint.source], receipt.rendererBuild.publicEntrySha256);
      assert.equal(manifest.sources['sonaloop/ui_components/declarations/persona.json'], proof.declarationSha256);
      assert.equal(proof.directNativeCalls, 0); assert.equal(proof.directMediaRequests, 0);
      assert.equal(receipt.checks.nativeToolCalls, 0); assert.equal(receipt.checks.providerCalls, 0);
      assert.equal(receipt.checks.simulatedWriteCalls, 0);
      const calls = JSON.parse(files.simulatedMcp);
      assert.equal(calls.length, 1); assert.equal(calls[0].request.name, receipt.tool);
      assert.deepEqual(calls[0].result, result);
      assert.equal(sha(files.image), receipt.image.sha256);
      assert.equal(files.image.readUInt32BE(16), receipt.crop.width * receipt.viewport.deviceScaleFactor);
      assert.equal(files.image.readUInt32BE(20), receipt.crop.height * receipt.viewport.deviceScaleFactor);
      assert.ok(receipt.crop.height > 300 && receipt.crop.width >= 300);
    }
  } finally { await rm(parent, { recursive: true, force: true }); }
});
