import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { launchBrowser, openApp, nativeFixtureSet, repo } from './research-browser.mjs';

const cases = JSON.parse(await readFile(resolve(repo, 'tools/persona-ui/fixtures/memory.json'))).cases;
let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

for (const item of cases) test(`Memory App preserves native ${item.scenario} and stays passive`, async () => {
  const fixture = fixtures.find(value => value.scenario === `memory-${item.scenario.replaceAll('_', '-')}`);
  const session = await openApp(browser, { family: 'memory', viewport: { width: 390, height: 3800 } });
  try {
    await session.send(fixture.result, fixture.input);
    await session.rendered();
    await session.assertPassive();
    const visible = await session.root.textContent();
    const expected = await session.root.evaluate((_, html) =>
      new DOMParser().parseFromString(html, 'text/html').body.textContent, fixture.html);
    assert.equal(visible, expected, 'The passive bridge retains every supplied semantic text node');
    const width = await session.root.evaluate(node => ({ content: node.scrollWidth, box: node.clientWidth }));
    assert.ok(width.content <= width.box + 1, 'Memory cards fit a 390px viewport');
    assert.equal(await session.root.locator('a,button,input,iframe,img').count(), 0);
    if (item.tool === 'get_project') {
      assert.equal(await session.root.getByRole('heading', { name: 'Memory projects', exact: true }).count(), 1);
      assert.ok(visible.includes('not a historical snapshot') && visible.includes('approved'));
      assert.ok(visible.includes('Renewal pending') && !visible.includes('Renewal approved'));
    }
    if (['get_project', 'search_entities', 'resolve_entity'].includes(item.tool) && item.state === 'ready') {
      const separated = await session.root.locator('.sl-research-memory-entity-head').evaluate(node => {
        const name = node.querySelector('b'), status = node.querySelector('span');
        return !status || status.getBoundingClientRect().x - name.getBoundingClientRect().right >= 7;
      });
      assert.ok(separated, 'Entity name and stored status have distinct readable space');
    }
    if (item.scenario === 'get_state_at') {
      assert.ok(visible.includes('2026-01-15') && visible.includes('2026-02-02'));
      assert.ok(visible.includes('pending') && !visible.includes('approved'));
      assert.ok(visible.includes('World context') && visible.includes('world_fixture'));
    }
    if (item.scenario === 'get_timeline') {
      assert.ok(visible.includes(item.value.note));
      assert.equal(await session.root.locator('.sl-research-memory-event').count(), 1);
      assert.ok(visible.includes('fact_new') && !visible.includes('fact_old'));
    }
    if (item.tool === 'recall_memory' && item.state === 'ready') {
      assert.ok(visible.includes('Ranking score') && visible.includes('Supplied recall excerpt'));
      for (const hit of item.value.hits) assert.ok(visible.includes(hit.text));
    }
    if (item.tool === 'export_persona_memory') {
      assert.ok(visible.includes(item.value.path) && visible.includes(String(item.value.bytes)));
      assert.ok(visible.includes('its bytes are not loaded by this view'));
    }
    if (['record_day', 'record_month_bundle', 'record_memory_deltas'].includes(item.tool)) {
      assert.ok(visible.includes('Reported processing counts'));
      assert.ok(visible.includes('a retry can replace existing records'));
    }
    if (item.tool === 'extract_pain_points' && item.state === 'ready') {
      assert.ok(visible.includes('supplies no evidence event IDs'));
      for (const pain of item.value) assert.ok(visible.includes(pain.issue) && visible.includes(pain.opportunity));
    }
  } finally { await session.page.close(); }
});
