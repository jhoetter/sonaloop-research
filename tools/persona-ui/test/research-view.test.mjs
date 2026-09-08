import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { launchBrowser, openApp, nativeFixtureSet, toolResult, repo, sha, pngDimensions, loadAsset } from './research-browser.mjs';

let browser, fixtures, declarations;
before(async () => { browser = await launchBrowser(); ({ fixtures, declarations } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

test('all four built resources bind the passive manifest, source and declared tools', async () => {
  for (const family of ['notes', 'sections', 'projects', 'search']) {
    const { manifest } = await loadAsset(family, { verifySources: true });
    const tools = declarations.filter(item => item.componentId === manifest.component_id);
    assert.ok(tools.length > 0);
    assert.ok(tools.every(item => item.resourceUri === manifest.resource.uri));
    for (const fixture of fixtures.filter(item => item.family === family))
      assert.ok(tools.some(item => item.tool === fixture.tool));
  }
  assert.equal(new Set(declarations.map(item => item.tool)).size, declarations.length);
});

test('pure sanitizer preserves semantics while stripping active nodes, attributes and navigation', async () => {
  const page = await browser.newPage();
  const requests = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.href === 'http://127.0.0.1:17479/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><main id="root"></main>' });
    if (url.href === 'http://127.0.0.1:17479/view.js') return route.fulfill({ contentType: 'text/javascript', body: await readFile(resolve(repo, 'sonaloop/web/assets/research-view/research-view.js')) });
    requests.push(url.href);
    return route.abort();
  });
  try {
    await page.goto('http://127.0.0.1:17479/');
    const html = `<article class="sl-research-card external" id="clobber" style="background:url(https://forbidden.invalid/css)" onclick="window.compromised=true">
      <header><h2 onmouseover="window.compromised=true">Safe title</h2></header>
      <p class="sl-prose muted small external" contenteditable="true" tabindex="0">Keep <strong>bold</strong>, <em>emphasis</em>, <code>code</code> and <a href="javascript:window.compromised=true" target="_top" download>link text</a>.</p>
      <a href="https://forbidden.invalid/link" ping="https://forbidden.invalid/ping">External text</a>
      <ul><li>List item</li></ul><blockquote>Quote</blockquote><table><tbody><tr><td>Cell</td></tr></tbody></table>
      <script>window.compromised=true</script><style>body{display:none}</style>
      <link rel="stylesheet" href="https://forbidden.invalid/sheet"><meta http-equiv="refresh" content="0;url=https://forbidden.invalid/refresh"><base href="https://forbidden.invalid/base">
      <img src="https://forbidden.invalid/image" onerror="window.compromised=true">
      <iframe src="https://forbidden.invalid/frame" srcdoc="<script>parent.compromised=true</script>"></iframe>
      <object data="https://forbidden.invalid/object"></object><embed src="https://forbidden.invalid/embed">
      <svg onload="window.compromised=true"><a href="https://forbidden.invalid/svg">SVG text</a></svg><math><mi>Math</mi></math>
      <video src="https://forbidden.invalid/video" poster="https://forbidden.invalid/poster"></video><audio src="https://forbidden.invalid/audio"></audio>
      <form action="https://forbidden.invalid/post"><input autofocus onfocus="window.compromised=true"><button>Submit</button>Form secret</form>
      <select onchange="window.compromised=true"><option>Choice text</option></select><textarea>Textarea text</textarea>
      <template><img src="https://forbidden.invalid/template"></template>
      <custom-element data-action="write" onclick="window.compromised=true">Custom text</custom-element>
    </article>`;
    const observed = await page.evaluate(async result => {
      const { acceptPresentation } = await import('/view.js');
      const root = document.querySelector('#root');
      root.replaceChildren(await acceptPresentation(result, 'sonaloop.research.notes-view'));
      for (const node of root.querySelectorAll('*')) for (const event of ['click', 'mouseover', 'error', 'load', 'focus', 'change']) node.dispatchEvent(new Event(event));
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      return { text: root.textContent, html: root.innerHTML, compromised: Boolean(window.compromised),
        attributes: [...root.querySelectorAll('*')].flatMap(node => [...node.attributes].map(attr => attr.name)),
        classes: [...root.querySelectorAll('[class]')].flatMap(node => [...node.classList]),
        forbidden: root.querySelectorAll('a,script,style,img,iframe,object,embed,svg,math,video,audio,form,input,button,select,textarea,template').length };
    }, toolResult(html));
    assert.equal(observed.compromised, false);
    assert.equal(observed.forbidden, 0);
    assert.ok(observed.attributes.every(name => name === 'class'));
    assert.ok(!observed.classes.includes('external'));
    assert.match(observed.html, /<strong>bold<\/strong>/);
    assert.match(observed.html, /<span class="sl-research-link">link text<\/span>/);
    for (const text of ['Safe title', 'List item', 'Quote', 'Cell', 'External text', 'Custom text']) assert.ok(observed.text.includes(text));
    assert.deepEqual(requests, [], 'Parsing and attaching passive HTML must not fetch external assets');
    assert.deepEqual(errors, []);
    for (const text of ['Form secret', 'SVG text', 'window.compromised']) assert.ok(!observed.text.includes(text), `Unexpected stripped subtree text ${text}: ${observed.text}`);
  } finally { await page.close(); }
});

test('packaged resource keeps hostile result HTML passive inside the MCP Apps sandbox', async () => {
  const session = await openApp(browser);
  try {
    await session.send(toolResult(`<article class="sl-research-card" onclick="window.compromised=true" style="position:fixed">
      <p>Readable result <a href="https://forbidden.invalid/">inert link</a></p>
      <script>window.compromised=true</script><img src="https://forbidden.invalid/image" onerror="window.compromised=true">
      <svg onload="window.compromised=true"><script>window.compromised=true</script></svg>
      <form action="https://forbidden.invalid/post"><input><button>Write</button></form>
      </article>`));
    await session.rendered();
    await session.assertPassive();
    assert.equal(await session.root.locator('[onclick],[style],[href],[src],[action]').count(), 0);
    assert.equal(await session.root.evaluate(() => Boolean(window.compromised)), false);
    assert.equal(await session.root.innerText(), 'Readable result inert link');
  } finally { await session.page.close(); }
});

for (const scenario of ['notes-ready', 'notes-empty', 'sections-ready', 'sections-empty', 'sections-detail',
  'projects-ready', 'projects-empty', 'projects-detail', 'search-ready', 'search-empty', 'search-detail'])
  test(`actual packaged MCP Apps bridge renders shared native ${scenario} HTML`, async () => {
    const fixture = fixtures.find(item => item.scenario === scenario);
    const session = await openApp(browser, { family: fixture.family, viewport: { width: 390, height: 844 } });
    try {
      await session.send(fixture.result, fixture.input);
      await session.rendered();
      await session.assertPassive();
      if (scenario === 'notes-ready') {
        const nativeFragment = await session.root.evaluate((_, html) => {
          const doc = new DOMParser().parseFromString(html, 'text/html');
          return doc.body.firstElementChild.innerHTML;
        }, fixture.note_content);
        assert.equal(await session.root.locator('.sl-research-note-content').innerHTML(), nativeFragment);
        assert.equal(await session.root.getByRole('heading', { name: 'Handover needs a visible owner' }).count(), 1);
      } else if (scenario === 'sections-ready') {
        assert.equal(await session.root.locator('.sl-research-member').count(), 2);
        assert.equal(await session.root.locator('.sl-research-link').count(), 2);
        assert.ok((await session.root.innerText()).includes('Open questions remain visible'));
      } else if (scenario === 'sections-detail') {
        assert.deepEqual(await session.root.locator('.sl-research-references li').allTextContents(), ['note:note_fixture', 'note:note_second']);
        assert.equal(await session.root.locator('.sl-research-member').count(), 0, 'Unresolved references never acquire fabricated titles');
      } else if (scenario === 'projects-ready' || scenario === 'projects-detail') {
        const nativeHeading = await session.root.evaluate(root => root.querySelector('h2').outerHTML + root.querySelector('.lead').outerHTML);
        assert.equal(nativeHeading, fixture.project_heading);
        assert.equal(await session.root.getByRole('heading', { name: 'Understanding shift handovers' }).count(), 1);
      } else if (scenario === 'search-ready') {
        assert.equal(await session.root.locator('.sl-research-search header').innerHTML(), fixture.search_hit_content);
        assert.equal(await session.root.locator('.sl-cmdk-title').innerText(), 'Understanding shift handovers');
      } else if (scenario === 'search-detail') {
        const nativeContent = await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').body.firstElementChild.innerHTML, fixture.fetched_content);
        assert.equal(await session.root.locator('.sl-research-note-content').innerHTML(), nativeContent);
        assert.equal(await session.root.getByRole('heading', { name: 'Handover questions' }).count(), 1);
      } else assert.equal(await session.root.locator('.sl-research-empty').count(), 1);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      const box = await session.root.boundingBox();
      assert.ok(box.width <= 390 && box.height <= 844);
      const png = await session.root.screenshot({ type: 'png' });
      const dimensions = pngDimensions(png);
      assert.ok(png.length <= 2 * 1024 * 1024 && dimensions.width * dimensions.height <= 4 * 1024 * 1024);
    } finally { await session.page.close(); }
  });

const invalid = {
  'missing presentation': result => { delete result._meta; },
  'wrong schema': result => { result._meta['sonaloop/presentation'].schema_version = 'unknown'; },
  'cross-component result': result => { result._meta['sonaloop/presentation'].component_id = 'sonaloop.research.sections-view'; },
  'unknown state': result => { result._meta['sonaloop/presentation'].state = 'saved'; },
  'digest mismatch': result => { result.content[0].text += ' altered after rendering'; },
  'malformed digest': result => { result._meta['sonaloop/presentation'].text_sha256 = 'not-a-digest'; },
  'oversized UTF-8 HTML': result => { result._meta['sonaloop/presentation'].html = `<p>${'🧪'.repeat(50_000)}</p>`; },
  'fully stripped HTML': result => { result._meta['sonaloop/presentation'].html = '<script>bad()</script>'; },
  'actual tool error with plausible HTML': result => { result.isError = true; },
};
for (const [name, mutate] of Object.entries(invalid)) test(`${name} shows truthful fallback and clears prior rendered data`, async () => {
  const session = await openApp(browser);
  try {
    const result = structuredClone(fixtures[0].result);
    await session.send(result);
    await session.rendered();
    mutate(result);
    await session.send(result);
    await session.root.getByText('This view is unavailable. The original tool result remains available in the chat.', { exact: true }).waitFor();
    assert.equal(await session.root.locator('.sl-research-card').count(), 0);
    await session.assertPassive();
    assert.equal(await session.page.evaluate(() => window.logs.filter(log => log.data?.event === 'view-rendered').length), 1, 'Rejected data is never logged as rendered');
  } finally { await session.page.close(); }
});

test('multiple native text blocks bind in order and a localized unavailable state can recover', async () => {
  const session = await openApp(browser, { locale: 'de' });
  try {
    const result = toolResult('<article class="sl-research-card"><p>Recovered content</p></article>');
    result.content = [{ type: 'text', text: 'First block' }, { type: 'image', data: 'aGVsbG8=', mimeType: 'image/png' }, { type: 'text', text: 'Second block' }];
    result._meta['sonaloop/presentation'].text_sha256 = sha('Second block\nFirst block');
    await session.send(result);
    await session.root.getByText('Diese Ansicht ist nicht verfügbar.', { exact: false }).waitFor();
    result._meta['sonaloop/presentation'].text_sha256 = sha('First block\nSecond block');
    await session.send(result);
    await session.rendered();
    assert.equal(await session.root.innerText(), 'Recovered content');
    await session.page.evaluate(() => window.bridge.setHostContext({ locale: 'en', theme: 'dark' }));
    await session.frame.locator('html[data-theme="dark"][lang="en"]').waitFor();
    await session.assertPassive();
  } finally { await session.page.close(); }
});

test('a slow earlier result cannot replace a newer result after digest validation', async () => {
  const session = await openApp(browser);
  try {
    await session.root.evaluate(() => {
      const digest = crypto.subtle.digest.bind(crypto.subtle);
      let first = true;
      crypto.subtle.digest = async (...args) => {
        if (first) { first = false; await new Promise(resolve => { window.releaseDigest = resolve; }); }
        return digest(...args);
      };
    });
    await session.send(toolResult('<p>Older result</p>', { text: 'old' }));
    await session.frame.locator('body').evaluate(async () => {
      while (!window.releaseDigest) await new Promise(resolve => requestAnimationFrame(resolve));
    });
    await session.send(toolResult('<p>Latest result</p>', { text: 'new' }));
    await session.rendered();
    await session.root.evaluate(async () => {
      window.releaseDigest();
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    assert.equal(await session.root.innerText(), 'Latest result');
    assert.equal(await session.page.evaluate(() => window.logs.filter(log => log.data?.event === 'view-rendered').length), 1);
    await session.assertPassive();
  } finally { await session.page.close(); }
});
