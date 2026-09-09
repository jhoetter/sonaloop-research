import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, nativeFixtureSet, openApp } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('Research Plan cards retain task and judgment semantics with only local disclosures', async t => {
  const cases = fixtures.filter(item => item.family === 'researchplan');
  assert.equal(cases.length, 22);
  assert.equal(new Set(cases.map(item => item.tool)).size, 8);
  for (const item of cases) await t.test(item.scenario, async () => {
    const session = await openApp(browser, { family: 'researchplan', viewport: { width: 390, height: 844 } });
    try {
      await session.send(item.result, item.input); await session.rendered(); await session.assertPassive();
      const complete = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, item.html);
      assert.equal(complete, expected, 'All supplied public Plan content remains in the DOM');
      assert.equal(await session.root.locator('details[open],img,iframe,form,input,button,a').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      assert.ok(!complete.includes('operation_id') && !complete.includes('dispatch_token'));
      if (item.tool === 'record_judgment') {
        const native = item.result.structuredContent.data;
        assert.ok(complete.includes(native.rationale));
        assert.ok(complete.includes(String(native.decided)));
        if (native.dispatch) assert.ok(complete.includes(native.dispatch.state));
      }
      if (item.tool === 'get_plan' && item.result.structuredContent.data?.tasks.length)
        for (const task of item.result.structuredContent.data.tasks) assert.ok(complete.includes(task.title));
      if (await session.root.locator('details').count()) {
        const first = session.root.locator('details').first();
        await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
        assert.notEqual(await first.getAttribute('open'), null);
        assert.equal(await session.root.textContent(), complete);
        await session.page.keyboard.press('Space'); assert.equal(await first.getAttribute('open'), null);
        await session.assertPassive();
      }
    } finally { await session.page.close(); }
  });
});
