import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, nativeFixtureSet, openApp } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('Product Understanding and methodology show native meaning with local details only', async t => {
  const cases = fixtures.filter(item => item.family === 'understanding' || item.tool === 'set_project_methodology');
  assert.equal(cases.length, 10);
  assert.equal(new Set(cases.map(item => item.tool)).size, 4);
  for (const item of cases) await t.test(item.scenario, async () => {
    const session = await openApp(browser, { family: item.family, viewport: { width: 390, height: 844 } });
    try {
      await session.send(item.result, item.input); await session.rendered(); await session.assertPassive();
      const complete = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, item.html);
      assert.equal(complete, expected, 'Every supplied public field remains in the DOM');
      assert.equal(await session.root.locator('details[open],img,iframe,form,input,button,a').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      const data = item.result.structuredContent.data;
      if (item.tool === 'set_project_methodology') {
        assert.ok(complete.includes(data.methodology) && complete.includes('does not include tasks'));
        assert.ok(await session.root.getByText(data.methodology, { exact: true }).first().isVisible());
      } else {
        assert.ok(!complete.includes('operation_id') && !complete.includes('operation_fingerprint'));
        assert.ok(!complete.includes('dispatch_token'));
        for (const claim of data.capabilities) assert.ok(complete.includes(claim.claim));
        if (item.scenario.includes('bounded')) {
          assert.ok(complete.includes('served_to_host') && complete.includes(data.stimulus_manifest.manifest_digest));
          assert.ok(complete.includes('does not fetch URLs'));
          assert.ok(!(await session.root.locator('details').filter({ hasText: data.stimulus_manifest.manifest_digest }).first().getAttribute('open')));
        }
        if ('idempotent_replay' in data) assert.ok(complete.includes(String(data.idempotent_replay)));
        if ('history' in data) for (const row of data.history) assert.ok(complete.includes(row.id));
      }
      const first = session.root.locator('details').first();
      await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
      assert.notEqual(await first.getAttribute('open'), null);
      assert.equal(await session.root.textContent(), complete);
      await session.page.keyboard.press('Space'); assert.equal(await first.getAttribute('open'), null);
      await session.assertPassive();
    } finally { await session.page.close(); }
  });
});
