import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launchBrowser, nativeFixtureSet, openApp } from './research-browser.mjs';

let browser, fixtures;
before(async () => { browser = await launchBrowser(); ({ fixtures } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('Research questions keep native duplicates, supplied frontier counts and local details', async t => {
  const cases = fixtures.filter(item => item.family === 'questions');
  assert.equal(cases.length, 9);
  for (const item of cases) await t.test(item.scenario, async () => {
    const session = await openApp(browser, { family: 'questions', viewport: { width: 390, height: 844 } });
    try {
      await session.send(item.result, item.input); await session.rendered(); await session.assertPassive();
      const text = await session.root.textContent();
      const expected = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.textContent, item.html);
      assert.equal(text, expected);
      assert.equal(await session.root.locator('details[open],a,img,button,form').count(), 0);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      const data = item.result.structuredContent.data;
      const rows = session.root.locator('.sl-research-question-content');
      assert.equal(await rows.count(), data.open_questions.length);
      for (let index = 0; index < data.open_questions.length; index++) {
        const question = data.open_questions[index];
        assert.ok(await rows.nth(index).getByText(question.text, { exact: true }).isVisible());
        assert.ok((await rows.nth(index).textContent()).includes(question.id));
        assert.equal(await rows.nth(index).getByText(question.id, { exact: true }).isVisible(), false);
      }
      if (item.tool === 'get_research_frontier') {
        assert.ok(text.includes(String(data.open_question_count)));
        for (const note of data.notes) assert.ok(text.includes(note));
      }
      const first = session.root.locator('details').first();
      if (await first.count()) {
        await first.locator(':scope > summary').focus(); await session.page.keyboard.press('Enter');
        assert.notEqual(await first.getAttribute('open'), null); assert.equal(await session.root.textContent(), text);
        await session.page.keyboard.press('Space'); assert.equal(await first.getAttribute('open'), null);
      }
      await session.assertPassive();
    } finally { await session.page.close(); }
  });
});
