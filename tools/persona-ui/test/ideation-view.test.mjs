import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, nativeFixtureSet, openApp } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('HMW questions, actual idea notes and ranked Council summaries remain passive', async t => {
  const cases = fixtures.filter(item => item.family === 'ideation');
  assert.equal(cases.length, 11);
  for (const item of cases) await t.test(item.scenario, async () => {
    const session = await openApp(browser, { family: 'ideation', viewport: { width: 390, height: 844 } });
    try {
      await session.send(item.result, item.input); await session.rendered(); await session.assertPassive();
      const text = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, item.html);
      assert.equal(text, expected, 'Complete supplied text survives native HTML sanitization');
      assert.equal(await session.root.locator('details[open],img,iframe,form,input,button,a').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      const data = item.result.structuredContent.data;
      if (item.tool === 'record_hmw_reframe') {
        for (const row of data.hmw) assert.ok(await session.root.getByText(row.question, { exact: true }).isVisible());
        assert.ok(!text.includes('status'));
      } else if (['record_ideas', 'list_ideas'].includes(item.tool)) {
        for (const row of data.ideas) assert.ok(text.includes(row.text));
        if (item.tool === 'record_ideas') assert.ok(text.includes(data.ideas[0].hmw_question));
        else assert.ok(!text.includes('How might we name the next owner?'));
      } else {
        const block = data.ideation || data;
        const rows = session.root.locator('.sl-research-ideation > ol > li');
        assert.equal(await rows.count(), block.shortlist.length);
        for (let index = 0; index < block.shortlist.length; index++) {
          assert.ok((await rows.nth(index).textContent()).includes(block.shortlist[index].rationale));
          assert.ok(await rows.nth(index).getByText(block.shortlist[index].text, { exact: true }).first().isVisible());
        }
        if (item.tool === 'get_ideation') assert.equal(await session.root.locator('.sl-research-council-voices').count(), 0);
        else {
          assert.ok(text.includes('checkpointed') && text.includes('legacy'));
          if (data.statements.length) assert.ok(text.includes('literal authored field') && text.includes('A supplied quotation'));
        }
      }
      const first = session.root.locator('details').first();
      if (await first.count()) {
        await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
        assert.notEqual(await first.getAttribute('open'), null);
        assert.equal(await session.root.textContent(), text);
        await session.page.keyboard.press('Space'); assert.equal(await first.getAttribute('open'), null);
      }
      await session.assertPassive();
    } finally { await session.page.close(); }
  });
});
