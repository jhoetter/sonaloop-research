import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { launchBrowser, openApp, nativeFixtureSet, repo } from './research-browser.mjs';

const cases = [
  ...JSON.parse(await readFile(resolve(repo, 'tools/persona-ui/fixtures/projects.json'))).map(value => ({ ...value, family: 'projects' })),
  ...JSON.parse(await readFile(resolve(repo, 'tools/persona-ui/fixtures/project-health.json'))).map(value => ({ ...value, family: 'runs' })),
];
let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

for (const item of cases) test(`Project App preserves native ${item.scenario}`, async () => {
  const fixture = fixtures.find(value => value.scenario === `${item.family}-${item.scenario.replaceAll('_', '-')}`);
  const session = await openApp(browser, { family: item.family, viewport: { width: 390, height: 4096 } });
  try {
    await session.send(fixture.result, fixture.input);
    await session.rendered();
    await session.assertPassive();
    const visible = await session.root.textContent();
    const expected = await session.root.evaluate((_, html) =>
      new DOMParser().parseFromString(html, 'text/html').body.textContent, fixture.html);
    assert.equal(visible, expected, 'Every supplied semantic text node survives the passive bridge');
    const size = await session.root.evaluate(node => ({ width: node.scrollWidth, box: node.clientWidth }));
    assert.ok(size.width <= size.box + 1, 'Project contents fit mobile width');
    if (item.tool === 'start_project') {
      assert.ok(visible.includes('does not establish a started or finished research run'));
      for (const warning of item.value.warnings) assert.ok(visible.includes(warning));
      if (item.value.idempotent_replay) assert.ok(visible.includes('Idempotent replaytrue'));
    }
    if (item.tool === 'query_projects') {
      assert.ok(visible.includes(`Offset ${item.value.offset}`));
      for (const row of item.value.items) assert.ok(visible.includes(row.id) && visible.includes(row.status));
    }
    if (item.tool === 'supersede_project') {
      assert.ok(visible.includes(item.value.supersedes_project_id) && visible.includes(item.value.reason));
      assert.ok(visible.includes('Evidence preserved'));
    }
    if (item.tool === 'archive_project') assert.ok(visible.includes('Archived; evidence is preserved.'));
    if (item.tool === 'delete_research_project') {
      for (const [key, value] of Object.entries(item.value.deleted)) assert.ok(visible.includes(key + value));
    }
    if (['set_project_icon', 'generate_project_icon'].includes(item.tool)) {
      assert.ok(visible.includes('Specification only'));
      if (item.value.icon.svg) assert.ok(visible.includes(item.value.icon.svg));
      assert.equal(await session.root.locator('svg,img,iframe').count(), 0);
    }
    if (item.tool === 'get_project_graph') {
      assert.equal(await session.root.locator('.sl-research-graph-node').count(), item.value.nodes.length);
      for (const row of item.value.nodes) assert.ok(visible.includes(row.study_id) && visible.includes(row.title));
    }
    if (item.tool === 'aggregate_predictions') {
      assert.ok(visible.includes('not observed behavior') && visible.includes('not unique people'));
    }
    if (item.tool === 'project_health') {
      for (const key of ['project_id', 'state', 'driver_state', 'lifecycle']) assert.ok(visible.includes(item.value[key]));
      assert.ok(visible.includes('Engine finished' + item.value.engine_finished));
      assert.ok(visible.includes('this view does not execute tools'));
      assert.ok(visible.includes(item.value.recovery_signals.host_connection_note));
    }
  } finally { await session.page.close(); }
});

for (const name of ['runs-health-waiting', 'projects-get-study-result', 'projects-get-study-result-empty'])
  test(`Full desktop diagnostic framing preserves ${name}`, async () => {
    const fixture = fixtures.find(value => value.scenario === name);
    assert.ok(fixture);
    const session = await openApp(browser, { family: fixture.family, viewport: { width: 960, height: 4096 } });
    try {
      await session.send(fixture.result, fixture.input); await session.rendered(); await session.assertPassive();
      const box = await session.root.boundingBox();
      assert.ok(box && box.y + box.height <= 4096, `Full native card height ${box?.height}`);
      const grid = await session.root.locator('.sl-research-health').first().evaluate(node => getComputedStyle(node).columnCount);
      assert.equal(grid, '2', 'Desktop health uses two complete columns');
      if (name === 'runs-health-waiting') {
        const text = await session.root.textContent();
        for (const qualifier of ['target_identity_only', 'server_fetch_authorizedfalse', 'stimulus_missingtrue', 'cohort_too_smalltrue'])
          assert.ok(text.includes(qualifier));
      }
    } finally { await session.page.close(); }
  });
