import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, nativeFixtureSet, openApp } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('Catalog cards retain actual rankings, native status and import outcomes without effects', async t => {
  const cases = fixtures.filter(item => item.family === 'catalog');
  assert.equal(cases.length, 16); assert.equal(new Set(cases.map(item => item.tool)).size, 4);
  for (const item of cases) await t.test(item.scenario, async () => {
    const session = await openApp(browser, { family: 'catalog', viewport: { width: 390, height: 844 } });
    try {
      await session.send(item.result, item.input); await session.rendered(); await session.assertPassive();
      const full = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, item.html);
      assert.equal(full, expected, 'Every supplied presentation field remains in the DOM');
      assert.equal(await session.root.locator('img,iframe,form,input,button,a,details[open]').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      if (item.tool === 'catalog_pull') assert.ok(full.includes('Viewing it does not repeat the import.'));
      if (item.scenario === 'catalog-recommend-ranked') assert.ok(full.includes('They do not import personas or establish research coverage.'));
      if (item.scenario === 'catalog-search-first') assert.ok(full.includes('· …'));
      if (item.scenario === 'catalog-search-last') assert.ok(!full.includes('· …'));
      if (item.tool === 'catalog_search' && item.result.structuredContent.data.items.length) {
        const identity = session.root.locator('.sl-research-catalog-identity').first();
        const name = await identity.locator('.sl-research-catalog-name').boundingBox();
        const slug = await identity.locator('.sl-research-catalog-slug').boundingBox();
        assert.ok(name && slug && slug.y >= name.y + name.height, 'Slug occupies its own line below the name');
        assert.ok(await identity.locator('.sl-research-catalog-slug').evaluate(node =>
          Number.parseFloat(getComputedStyle(node).fontSize) < Number.parseFloat(getComputedStyle(node.parentElement).fontSize)));
      }
      if (['catalog-search-local', 'catalog-recommend-ranked', 'catalog-pull-mixed'].includes(item.scenario)) {
        const value = item.result.structuredContent.data;
        const label = item.tool === 'catalog_pull' ? 'Reported import counts' : 'Reported facet coverage';
        const group = session.root.locator('details').filter({ has: session.frame.locator('summary', { hasText: label }) });
        assert.equal(await group.count(), 1);
        assert.equal(await group.getAttribute('open'), null);
        const keys = item.tool === 'catalog_pull' ? Object.keys(value.counts)
          : Object.keys(value.facet_summary || value.coverage);
        for (const key of keys) assert.ok((await group.textContent()).includes(key));
        if (item.tool === 'catalog_pull') {
          for (const row of value.skipped_premium || [])
            assert.ok(await session.root.locator('li', { hasText: row.reason }).isVisible());
          for (const key of ['note', 'hint']) if (value[key]) {
            const note = session.root.locator('p').filter({ hasText: value[key] });
            assert.ok(await note.count()); assert.equal(await note.first().isVisible(), false);
          }
        }
        if (item.tool === 'catalog_recommend') {
          for (const warning of value.warnings)
            assert.ok(await session.root.locator('li', { hasText: warning }).isVisible());
          for (const row of value.personas) for (const reason of row.rationale)
            assert.ok(await session.root.locator('li', { hasText: reason }).first().isVisible());
        }
      }
      const disclosure = session.root.locator('details').first();
      if (await disclosure.count()) {
        await disclosure.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
        assert.notEqual(await disclosure.getAttribute('open'), null);
        assert.equal(await session.root.textContent(), full);
        await session.page.keyboard.press('Space'); assert.equal(await disclosure.getAttribute('open'), null);
        await session.assertPassive();
      }
    } finally { await session.page.close(); }
  });
});
