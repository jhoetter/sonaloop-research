import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, openApp, nativeFixtureSet } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('native conversation and continuity cards retain supplied content without effects', async t => {
  const cases = fixtures.filter(item => item.family === 'chats');
  assert.equal(cases.length, 18);
  assert.equal(new Set(cases.map(item => item.tool)).size, 8);
  for (const fixture of cases) await t.test(fixture.scenario, async () => {
    const session = await openApp(browser, { family: 'chats', viewport: { width: 390, height: 844 } });
    try {
      await session.send(fixture.result, fixture.input); await session.rendered(); await session.assertPassive();
      const complete = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, fixture.html);
      assert.equal(complete, expected, 'Full native supplied conversation and references remain in DOM');
      assert.equal(await session.root.locator('img,iframe,form,input,button').count(), 0);
      assert.equal(await session.root.locator('details[open]').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      if (fixture.tool === 'chat_with_persona') {
        assert.ok(complete.includes('It does not record this message or a new Persona reply.'));
        const context = session.root.locator('details').filter({ hasText: 'Supplied authoring context' });
        assert.equal(await context.count(), 1);
        assert.ok((await context.textContent()).includes(fixture.result.structuredContent.data.agent_context));
      }
      if (fixture.tool === 'record_chat_turn')
        assert.ok(complete.includes('it does not contain the exchange text.'));
      if (fixture.scenario === 'chats-list-page') assert.ok(complete.includes('· …'));
      if (fixture.scenario === 'chats-list-next') assert.ok(!complete.includes('· …'));
      const first = session.root.locator('details.sl-research-disclosure').first();
      if (await first.count()) {
        await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
        assert.notEqual(await first.getAttribute('open'), null);
        assert.equal(await session.root.textContent(), complete);
        await session.page.keyboard.press('Space'); assert.equal(await first.getAttribute('open'), null);
        await session.assertPassive();
      }
    } finally { await session.page.close(); }
  });
});
