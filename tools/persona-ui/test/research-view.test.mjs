import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { launchBrowser, openApp, nativeFixtureSet, toolResult, repo, sha, pngDimensions, loadAsset } from './research-browser.mjs';

let browser, fixtures, declarations;
before(async () => { browser = await launchBrowser(); ({ fixtures, declarations } = await nativeFixtureSet()); });
after(async () => { await browser?.close(); });

for (const [locale, label] of [['en', 'Loading view…'], ['de', 'Ansicht wird geladen…']])
  test(`localized loading is visible before any tool result (${locale})`, async () => {
    const session = await openApp(browser, { locale });
    try {
      await session.root.getByText(label, { exact: true }).waitFor();
      assert.equal(await session.root.locator('.sl-research-card').count(), 0);
      assert.equal(await session.page.evaluate(() => window.logs.length), 0);
      await session.assertPassive();
    } finally { await session.page.close(); }
  });

test('logging notification failure cannot erase a successfully rendered native result', async () => {
  const session = await openApp(browser, { rejectLogging: true });
  try {
    await session.send(fixtures[0].result, fixtures[0].input);
    await session.root.evaluate(async () => {
      for (let attempt = 0; attempt < 120 && !globalThis.__loggingTransportFailures; attempt++)
        await new Promise(resolve => requestAnimationFrame(resolve));
      if (!globalThis.__loggingTransportFailures) throw new Error('Logging failure was not injected');
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    assert.equal(await session.root.evaluate(() => globalThis.__loggingTransportFailures), 1);
    assert.equal(await session.root.getByRole('heading', { name: 'Handover needs a visible owner' }).count(), 1);
    assert.equal(await session.root.getByText('This view is unavailable.', { exact: false }).count(), 0);
    assert.deepEqual(await session.page.evaluate(() => window.logs), [], 'Only the rejected log is missing');
    await session.assertPassive();
  } finally { await session.page.close(); }
});

test('all built resources bind the passive manifest, source and declared tools', async () => {
  for (const family of ['notes', 'sections', 'projects', 'search', 'hypotheses', 'decisions', 'surveys', 'councils', 'syntheses', 'sessions']) {
    const { manifest } = await loadAsset(family, { verifySources: true });
    const tools = declarations.filter(item => item.componentId === manifest.component_id);
    assert.ok(tools.length > 0);
    assert.ok(tools.every(item => item.resourceUri === manifest.resource.uri));
    for (const fixture of fixtures.filter(item => item.family === family))
      assert.ok(tools.some(item => item.tool === fixture.tool));
  }
  assert.equal(new Set(declarations.map(item => item.tool)).size, declarations.length);
});

test('customer declarations name exact authored props, fixture scenarios and resource states', async () => {
  for (const family of new Set(fixtures.map(item => item.family))) {
    const declaration = JSON.parse(await readFile(resolve(repo, `sonaloop/ui_components/declarations/${family}.json`)));
    const { manifest } = await loadAsset(family);
    for (const scenario of declaration.scenarios) {
      const fixture = fixtures.find(item => item.family === family && item.scenario === scenario.id);
      assert.ok(fixture, `${family}/${scenario.id}`);
      assert.equal(scenario.state, fixture.state);
      assert.ok(manifest.states.includes(scenario.state));
      assert.deepEqual(scenario.props, { name: fixture.tool,
        value: ['search', 'fetch'].includes(fixture.tool) ? fixture.native : fixture.native.data });
      assert.equal(JSON.stringify(scenario.props).includes('"_meta"'), false);
    }
  }
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

test('passive native reference keeps the final qualifier and source anchor after sanitizing', async () => {
  const session = await openApp(browser, { viewport: { width: 390, height: 900 } });
  try {
    await session.send(toolResult(fixtures[0].passive_reference_html));
    await session.rendered();
    const text = await session.root.innerText();
    assert.ok(text.includes('An observation with substantial context. '.repeat(12).trim()));
    assert.ok(text.includes('Only applies during the pilot.'));
    assert.equal(await session.root.locator('code').innerText(), 'council:council_real#statement_3');
    assert.equal(await session.root.locator('[href],[title]').count(), 0);
    await session.assertPassive();
  } finally { await session.page.close(); }
});

test('passive report semantics and table header scope survive without arbitrary attributes', async () => {
  const session = await openApp(browser);
  try {
    await session.send(toolResult('<section class="sl-research-report-section" onclick="bad()"><h2>Recorded figure</h2><figure><table><thead><tr><th scope="col">Series</th><th scope="col">Value</th></tr></thead><tbody><tr><th scope="row">Pilot</th><td>0</td></tr><tr><th scope="bad" data-secret="discard">Unknown</th><td>-2.5</td></tr></tbody></table><figcaption>Supplied values, no image</figcaption></figure></section>'));
    await session.rendered();
    assert.equal(await session.root.locator('section figure figcaption').innerText(), 'Supplied values, no image');
    assert.deepEqual(await session.root.locator('th[scope]').evaluateAll(nodes => nodes.map(node => node.getAttribute('scope'))), ['col', 'col', 'row']);
    assert.equal(await session.root.locator('[onclick],[data-secret],[scope="bad"]').count(), 0);
    await session.assertPassive();
  } finally { await session.page.close(); }
});

test('native count meters admit only a passive unit quantity and accessible label', async () => {
  const session = await openApp(browser);
  try {
    await session.send(toolResult('<p>2 of 3 responses</p><meter class="sl-research-meter" min="0" max="1" value="0.666666666667" aria-label="Named owner" onclick="window.compromised=true" style="background:url(https://forbidden.invalid)">2 / 3</meter>'));
    await session.rendered();
    const meter = session.root.locator('meter');
    assert.equal(await meter.getAttribute('aria-label'), 'Named owner');
    assert.equal(await meter.evaluate(node => node.value), 0.666666666667);
    assert.equal(await meter.getAttribute('min'), '0');
    assert.equal(await meter.getAttribute('max'), '1');
    assert.equal(await session.root.locator('[style],[onclick]').count(), 0);
    await session.assertPassive();
    for (const attributes of ['min="0" max="1" value="NaN"', 'min="0" max="1" value="1.1"',
      'min="0" max="1" value="-0.1"', 'min="0" max="20" value="0.5"', 'min="0" max="1" value="1e-7"']) {
      await session.send(toolResult(`<p>Invalid native quantity</p><meter ${attributes}>Raw count remains in tool text</meter>`));
      await session.root.getByText('This view is unavailable.', { exact: false }).waitFor();
      assert.equal(await session.root.locator('meter').count(), 0);
    }
    await session.assertPassive();
  } finally { await session.page.close(); }
});

for (const scenario of ['notes-ready', 'notes-empty', 'sections-ready', 'sections-empty', 'sections-detail',
  'projects-ready', 'projects-empty', 'projects-detail', 'search-ready', 'search-empty', 'search-detail',
  'hypotheses-open', 'hypotheses-observed', 'hypotheses-dropped', 'hypotheses-empty',
  'decisions-proposed', 'decisions-adopted', 'decisions-superseded', 'decisions-empty',
  'surveys-instrument', 'surveys-ready', 'surveys-comparison', 'surveys-repeated-choice', 'surveys-text', 'surveys-empty', 'surveys-imported',
  'councils-voices', 'councils-input', 'councils-list', 'councils-empty',
  'syntheses-convergence', 'syntheses-report', 'syntheses-outline', 'syntheses-empty',
  'sessions-completed', 'sessions-dropped', 'sessions-salience', 'sessions-prototype', 'sessions-funnel', 'sessions-funnel-empty', 'sessions-empty'])
  test(`actual packaged MCP Apps bridge renders shared native ${scenario} HTML`, async () => {
    const fixture = fixtures.find(item => item.scenario === scenario);
    const height = ['sessions', 'syntheses'].includes(fixture.family) ? 1800 : 844;
    const session = await openApp(browser, { family: fixture.family, viewport: { width: 390, height } });
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
      } else if (scenario.startsWith('hypotheses-') && scenario !== 'hypotheses-empty') {
        assert.equal(await session.root.getByRole('heading', { name: 'A named owner reduces handover time' }).count(), 1);
        const text = await session.root.innerText();
        assert.ok(text.includes('minutes → 4 ±1 · Confidence 80%'));
        if (scenario === 'hypotheses-observed') {
          assert.ok(text.includes('4.5') && text.includes('The pilot falls within the predicted range.'));
          assert.ok(text.includes('Synthetic observation, not research evidence'));
        }
        if (scenario === 'hypotheses-dropped') assert.ok(text.includes('The team no longer uses this handover process.'));
      } else if (scenario.startsWith('decisions-') && scenario !== 'decisions-empty') {
        assert.equal(await session.root.getByRole('heading', { name: 'Name a handover owner' }).count(), 1);
        const text = await session.root.innerText();
        assert.ok(text.includes('Show the current owner before the next shift begins.'));
        assert.ok(text.includes('The alternative has no explicit owner.'));
        assert.ok(text.includes('hyp_fixture'));
        if (scenario === 'decisions-superseded') {
          assert.equal(await session.root.locator('.sl-research-card').count(), 2);
          assert.equal(await session.root.getByRole('heading', { name: 'Make the current owner visible' }).count(), 1);
        }
      } else if (scenario.startsWith('surveys-') && scenario !== 'surveys-empty') {
        const text = await session.root.innerText();
        if (scenario === 'surveys-instrument') {
          assert.ok(text.includes('Named owner') && text.includes('Longer email'));
          assert.ok(!text.includes('0 responses'));
          assert.equal(await session.root.locator('meter').count(), 0);
        } else if (scenario === 'surveys-ready') {
          assert.deepEqual(await session.root.locator('meter').evaluateAll(nodes => nodes.map(node => node.value)), [0.666666666667, 0.333333333333]);
          assert.ok(text.includes('3 responses'));
        } else if (scenario === 'surveys-comparison') {
          assert.ok(text.includes('Council prediction (2)') && text.includes('Real answers (3)'));
          assert.ok(text.includes('council:council_fixture'));
          const rows = await session.root.locator('tbody tr').allTextContents();
          assert.ok(rows.some(row => row.includes('Support') && row.endsWith('21')));
          assert.ok(rows.some(row => row.includes('Oppose') && row.endsWith('02')));
        } else if (scenario === 'surveys-repeated-choice') {
          assert.ok(text.includes('Named owner: 2') && text.includes('answered count (2 / 1)'));
          assert.equal(await session.root.locator('.sl-research-count-overflow meter').count(), 0);
        } else if (scenario === 'surveys-text') {
          assert.equal(await session.root.locator('blockquote').count(), 2);
          assert.ok(text.includes('Only applies during the pilot.') && text.includes('2 / 3'));
        } else assert.ok(text.includes('1 responses processed') && text.includes('3 responses'));
      } else if (scenario.startsWith('councils-') && scenario !== 'councils-empty') {
        const text = await session.root.innerText();
        assert.ok(text.includes('What interrupts the handover?'));
        if (scenario === 'councils-voices') {
          assert.equal(await session.root.locator('.sl-research-statement').count(), 1);
          const labels = session.root.locator('.sl-research-statement-body > .sl-research-statement-head > span');
          assert.equal(await labels.count(), 2);
          const stanceBox = await labels.nth(0).boundingBox(), postureBox = await labels.nth(1).boundingBox();
          assert.ok(postureBox.x >= stanceBox.x + stanceBox.width + 4 || postureBox.y >= stanceBox.y + stanceBox.height,
            'Each recorded stance and claim label remains visually separated');
          for (const value of ['persona_fixture', 'Where is ownership unclear?', 'cannot identify the owner', '-1 · skeptical', 'Synthetic fixture, not observed research']) assert.ok(text.includes(value), value);
        } else if (scenario === 'councils-input') {
          assert.ok(text.includes('Show the current owner before the next shift begins.'));
          assert.ok(text.includes('Who changes the owner?') && text.includes('uncertain → support'));
          assert.equal(await session.root.locator('details,summary').count(), 0, 'Passive input snapshots remain visible');
        } else {
          assert.ok(text.includes('Participants: 2') && text.includes('Voices: 3'));
          assert.ok(text.includes('support: 1') && text.includes('oppose: 1'));
          assert.ok(!text.includes('persona_fixture'), 'Summary counts never invent participant identities');
        }
      } else if (scenario.startsWith('syntheses-') && scenario !== 'syntheses-empty') {
        const text = await session.root.innerText();
        assert.equal(await session.root.locator('.sl-research-report-cover').count(), 1);
        assert.equal(await session.root.locator('details,summary,pre').count(), 0);
        if (scenario === 'syntheses-convergence') {
          assert.ok(text.includes('A named owner makes the handover easier.'));
          assert.ok(text.includes('Keep the current owner visible.'));
        } else if (scenario === 'syntheses-report') {
          for (const value of ['Only observed during the pilot.', 'council:fixture', 'The owner is clear.', 'asset:asset_fixture',
            'A recorded reference; no image pixels supplied.', 'Synthetic component example.']) assert.ok(text.includes(value), value);
          assert.equal(await session.root.locator('.sl-research-figure').count(), 1);
          assert.equal(await session.root.locator('.sl-research-report-citations ol').evaluate(node => getComputedStyle(node).listStyleType), 'none',
            'Authored citation numbers do not acquire duplicate browser numbering');
          const citation = session.root.locator('.sl-research-report-citations li > span');
          const number = await citation.nth(0).boundingBox(), source = await citation.nth(1).boundingBox();
          assert.ok(source.x >= number.x + number.width + 7, 'Citation number and source stay visibly separate');
          assert.equal(await session.root.locator('section.sl-research-report-section figure figcaption').count(), 1,
            'The passive bridge preserves report and figure document semantics');
        } else {
          assert.ok(text.includes('not yet authored'));
          assert.ok(!text.includes('Only observed during the pilot.'));
          assert.notEqual(await session.root.locator('.sl-research-status').innerText(),
            await session.root.evaluate((_, html) => new DOMParser().parseFromString(html, 'text/html').querySelector('.sl-research-status').textContent, fixtures.find(item => item.scenario === 'syntheses-report').html), 'An outline does not claim a completed report');
        }
      } else if (scenario.startsWith('sessions-') && scenario !== 'sessions-empty') {
        const text = await session.root.innerText();
        if (scenario.startsWith('sessions-funnel')) {
          assert.ok(text.includes(scenario.endsWith('-empty') ? 'Completed: 0 / 0' : 'Completed: 2 / 3'));
          if (scenario === 'sessions-funnel') {
            assert.ok(text.includes('3 entered · 1 dropped') && text.includes('The next action was missing'));
            assert.deepEqual(await session.root.locator('meter').evaluateAll(nodes => nodes.map(node => node.value)), [0.666666666667, 0.333333333333]);
          } else assert.equal(await session.root.locator('meter').count(), 0);
        } else {
          assert.ok(text.includes('Owner panel'));
          assert.ok(text.includes('screenshot pixels are not displayed here'));
          if (scenario === 'sessions-prototype') {
            for (const value of ['Recorded version', 'v0.7', 'The next action is missing']) assert.ok(text.includes(value), value);
            assert.ok(!text.includes('step-4.png') && !text.includes('would drop'));
          } else {
            assert.ok(text.includes('step-0.png') && text.includes('I can find the person responsible.'));
            if (scenario === 'sessions-dropped') assert.ok(text.includes('The handover was abandoned') && text.includes('Dropped at step 0'));
            else assert.ok(text.includes('Found the owner'));
            if (scenario === 'sessions-salience') for (const value of ['Owner salience hypothesis', 'x: 10%', 'not eye-tracking']) assert.ok(text.includes(value), value);
          }
        }
      } else assert.equal(await session.root.locator('.sl-research-empty').count(), 1);
      assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth));
      const box = await session.root.boundingBox();
      assert.ok(box.width <= 390 && box.height <= height);
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
