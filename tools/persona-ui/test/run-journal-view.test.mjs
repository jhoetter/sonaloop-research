import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, nativeFixtureSet, openApp } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('Run journal cards show actual outcomes and keep local diagnostics without authority', async t => {
  const names = new Set(['start_run', 'run_journal', 'resume_project_run', 'finish_run']);
  const cases = fixtures.filter(item => names.has(item.tool));
  assert.equal(cases.length, 12);
  for (const item of cases) await t.test(item.scenario, async () => {
    const session = await openApp(browser, { family: 'runs', viewport: { width: 390, height: 844 } });
    try {
      await session.send(item.result, item.input); await session.rendered(); await session.assertPassive();
      const complete = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, item.html);
      assert.equal(complete, expected, 'All supplied public Run content stays in the DOM');
      assert.equal(await session.root.locator('details[open],img,iframe,form,input,button,a').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      assert.ok(!complete.includes('dispatch_token') && !complete.includes('operation_id'));
      if (item.tool === 'finish_run') {
        assert.ok(complete.includes(String(item.result.structuredContent.data.steps)));
        assert.ok(complete.includes(item.result.structuredContent.data.status));
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
