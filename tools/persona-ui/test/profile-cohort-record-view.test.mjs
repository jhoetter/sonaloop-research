import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, openApp, nativeFixtureSet } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('all native profile, cohort and record fixtures preserve readable passive content', async t => {
  const cases = fixtures.filter(item => ['profiles', 'cohorts', 'records'].includes(item.family));
  assert.equal(cases.length, 38);
  assert.equal(new Set(cases.map(item => item.tool)).size, 17);
  for (const fixture of cases) await t.test(fixture.scenario, async () => {
    const session = await openApp(browser, { family: fixture.family, viewport: { width: 390, height: 844 } });
    try {
      await session.send(fixture.result, fixture.input); await session.rendered(); await session.assertPassive();
      const complete = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, fixture.html);
      assert.equal(complete, expected, 'Full supplied content is retained, with no additional native calls');
      assert.equal(await session.root.locator('details[open]').count(), 0);
      assert.equal(await session.root.locator('img,iframe,form,input,button').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      assert.ok(!complete.includes('synthetic-dispatch-no-authority'));
      const first = session.root.locator('details.sl-research-disclosure').first();
      if (await first.count()) {
        await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
        assert.notEqual(await first.getAttribute('open'), null);
        assert.equal(await session.root.textContent(), complete);
        await session.page.keyboard.press('Space'); assert.equal(await first.getAttribute('open'), null);
        await session.assertPassive();
      }
      if (fixture.scenario === 'cohort-selected-not-checkpointed') {
        assert.ok(complete.includes('Selection alone does not pass or checkpoint the cohort gate.'));
        assert.ok(complete.includes('false'));
      }
      if (fixture.scenario === 'records-voice-red') {
        assert.ok(complete.includes('The candidate text is not retained in this result.'));
        assert.ok(complete.includes('0 / 5'));
      }
      if (fixture.scenario === 'profiles-get-history') {
        for (const id of ['calendar_profile', 'event_profile', 'day_profile', 'pain_profile', 'reflection_profile'])
          assert.ok(complete.includes(id));
        assert.ok(complete.includes('this view does not load the image or file'));
      }
    } finally { await session.page.close(); }
  });
});
