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
