import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, openApp, nativeFixtureSet } from './research-browser.mjs';
let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });
test('every native preparation fixture retains supplied content through the passive bridge', async t => {
  const cases = fixtures.filter(value => value.family === 'preparation');
  assert.equal(cases.length, 17);
  assert.equal(new Set(cases.map(value => value.tool)).size, 9);
  for (const fixture of cases) await t.test(fixture.scenario, async () => {
    const session = await openApp(browser, { family: 'preparation', viewport: { width: 390, height: 844 } });
    try {
      await session.send(fixture.result, fixture.input); await session.rendered(); await session.assertPassive();
      const complete = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, fixture.html);
      assert.equal(complete, expected, 'Supplied record is retained without another tool or lookup');
      assert.equal(await session.root.locator('details[open]').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      const box = await session.root.boundingBox();
      assert.ok(box && box.y + box.height <= 844, `Default card is bounded: ${box?.height}`);
      if (fixture.tool.includes('build') && fixture.state === 'ready') {
        assert.ok(complete.includes('This view executes no next step.'));
        const data = fixture.result.structuredContent?.data;
        if (data?.dispatch?.params?.dispatch_token) assert.ok(!complete.includes(data.dispatch.params.dispatch_token));
      }
      const first = session.root.locator('details.sl-research-disclosure').first();
      if (await first.count()) {
        await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
        assert.notEqual(await first.getAttribute('open'), null);
        assert.equal(await session.root.textContent(), complete);
        await session.assertPassive();
      }
    } finally { await session.page.close(); }
  });
});
