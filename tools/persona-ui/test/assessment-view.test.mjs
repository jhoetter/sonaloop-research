import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, nativeFixtureSet, openApp } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('Computed Plan assessment and supplied Markdown preserve every value with local disclosure', async t => {
  const cases = fixtures.filter(item => item.family === 'assessment');
  assert.equal(cases.length, 10);
  for (const item of cases) await t.test(item.scenario, async () => {
    const session = await openApp(browser, { family: 'assessment', viewport: { width: 390, height: 844 } });
    try {
      await session.send(item.result, item.input); await session.rendered(); await session.assertPassive();
      const text = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, item.html);
      assert.equal(text, expected, 'Every supplied public field is retained in the DOM');
      assert.equal(await session.root.locator('details[open],img,iframe,form,input,button,a').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      const value = item.result.structuredContent.data;
      if (item.tool === 'assess_project') {
        if (value.goal) assert.ok(await session.root.getByText(value.goal, { exact: true }).isVisible());
        else assert.equal(await session.root.locator(".sl-research-plan-assessment > p").first().textContent(), "");
        const labels = { frame: 'Frame the questions', act: 'Continue research', converge: 'Consolidate findings', finish: 'Prepare the handoff', complete: 'Plan complete', blocked: 'Blocked' };
        assert.ok(await session.root.getByText(labels[value.recommendation], { exact: true }).isVisible());
        assert.equal(await session.root.getByText(value.recommendation, { exact: true }).first().isVisible(), false);
        assert.equal(await session.root.getByText('Computed plan assessment. Run status is tracked separately.', { exact: true }).isVisible(), false);
        assert.ok(text.includes(String(value.complete)) && text.includes(String(value.tasks_complete)));
        assert.ok(!text.includes('engine_finished'));
        for (const gap of value.gaps) assert.ok(text.includes(gap));
        if (item.scenario === 'assessment-stale-handoff') assert.ok(text.includes('latest_stale') && text.includes('synthetic-report'));
      } else {
        assert.equal(await session.root.locator('pre').textContent(), value.markdown, 'Exact original Markdown is inspectable');
        assert.equal(await session.root.getByText('Exported plan with decisions and sources.', { exact: true }).isVisible(), false);
        assert.ok(await session.root.locator('.md').count() || await session.root.getByText('Research plan', { exact: false }).count());
        if (item.scenario === 'assessment-document-decisions') assert.ok(text.includes('superseded by:') && text.includes('The state remained unclear.'));
      }
      const first = session.root.locator('details').first();
      await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
      assert.notEqual(await first.getAttribute('open'), null);
      assert.equal(await session.root.textContent(), text);
      await session.page.keyboard.press('Space'); assert.equal(await first.getAttribute('open'), null);
      await session.assertPassive();
    } finally { await session.page.close(); }
  });
});
