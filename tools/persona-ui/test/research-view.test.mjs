import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { launchBrowser, openApp, nativeFixtureSet, toolResult, repo, sha, pngDimensions, loadAsset } from './research-browser.mjs';

let browser, fixtures, declarations, noteFixture;
before(async () => { browser = await launchBrowser(); ({ fixtures, declarations } = await nativeFixtureSet()); noteFixture = fixtures.find(item => item.scenario === 'notes-ready'); assert.equal(noteFixture.tool, 'list_notes'); });
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
    await session.send(noteFixture.result, noteFixture.input);
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
  for (const family of ['preparation', 'runs', 'memory', 'calendar', 'plans', 'prototypes', 'references', 'assets', 'notes', 'sections', 'projects', 'search', 'hypotheses', 'decisions', 'surveys', 'councils', 'syntheses', 'sessions']) {
    const { manifest } = await loadAsset(family, { verifySources: true });
    const tools = declarations.filter(item => item.componentId === manifest.component_id);
    assert.ok(tools.length > 0);
    assert.ok(tools.every(item => item.resourceUri === manifest.resource.uri));
    for (const fixture of fixtures.filter(item => item.family === family))
      assert.ok(tools.some(item => item.tool === fixture.tool));
  }
  assert.equal(new Set(declarations.map(item => item.tool)).size, declarations.length);
  assert.deepEqual(new Set(fixtures.map(item => item.tool)), new Set(declarations.map(item => item.tool)),
    'Every supported tool has its own authored result fixture; no raster is relabelled');
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
        value: fixture.public_value });
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
      <dl class="sl-research-fields" onclick="window.compromised=true"><dt id="private">Recorded field</dt><dd style="color:red">Native value</dd></dl>
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
    assert.match(observed.html, /<dl class="sl-research-fields"><dt>Recorded field<\/dt><dd>Native value<\/dd><\/dl>/);
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
    await session.send(toolResult(noteFixture.passive_reference_html));
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

for (const scenario of ['plans-put-day-plan', 'plans-get-day-plan', 'plans-put-period-plan', 'plans-get-period-plan', 'plans-list-period-plans', 'calendar-get-current-state', 'calendar-get-calendar', 'calendar-get-calendar-period', 'calendar-get-activity', 'calendar-period-day', 'calendar-period-week', 'calendar-period-year', 'plans-plan-null', 'plans-period-plan-null', 'plans-plans-empty', 'calendar-calendar-empty', 'calendar-period-empty', 'calendar-state-before-events', 'prototypes-scaffolded', 'prototypes-registered', 'prototypes-remote', 'prototypes-detail', 'prototypes-list', 'prototypes-empty', 'prototypes-running', 'prototypes-reused', 'prototypes-hosted', 'prototypes-stopped', 'prototypes-idle', 'prototypes-deleted', 'prototypes-missing', 'notes-ready', 'notes-empty', 'sections-ready', 'sections-empty', 'sections-detail',
  'projects-ready', 'projects-empty', 'projects-detail', 'search-ready', 'search-empty', 'search-detail',
  'hypotheses-open', 'hypotheses-observed', 'hypotheses-dropped', 'hypotheses-empty',
  'decisions-proposed', 'decisions-adopted', 'decisions-superseded', 'decisions-empty',
  'surveys-instrument', 'surveys-ready', 'surveys-comparison', 'surveys-repeated-choice', 'surveys-text', 'surveys-empty', 'surveys-imported',
  'councils-voices', 'councils-input', 'councils-list', 'councils-empty',
  'syntheses-convergence', 'syntheses-report', 'syntheses-outline', 'syntheses-empty',
  'sessions-completed', 'sessions-dropped', 'sessions-salience', 'sessions-prototype', 'sessions-funnel', 'sessions-funnel-empty', 'sessions-empty',
  'councils-record-head-to-head', 'councils-get-head-to-head', 'councils-record-price-ladder', 'councils-get-price-ladder', 'councils-price-ladder-analysis', 'councils-record-red-team', 'councils-get-red-team', 'councils-query-councils',
  'references-added', 'references-detail', 'references-list', 'references-empty', 'references-failed', 'references-deleted',
  'assets-attached', 'assets-detail', 'assets-list', 'assets-empty', 'assets-shot', 'assets-admitted', 'assets-detached', 'assets-missing',
  'notes-created', 'notes-data', 'sections-created', 'sections-updated', 'sections-added', 'sections-removed', 'sections-members-set',
  'hypotheses-result-recorded', 'surveys-detail', 'syntheses-recorded', 'sessions-flow-funnel', 'councils-recorded'])
  test(`actual packaged MCP Apps bridge renders shared native ${scenario} HTML`, async () => {
    const fixture = fixtures.find(item => item.scenario === scenario);
    const height = ['sessions', 'syntheses', 'councils', 'prototypes', 'calendar'].includes(fixture.family) ? 3800 : 844;
    const session = await openApp(browser, { family: fixture.family, viewport: { width: 390, height } });
    try {
      await session.send(fixture.result, fixture.input);
      await session.rendered();
      await session.assertPassive();
      if (['notes-ready', 'notes-created', 'notes-data'].includes(scenario)) {
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
      } else if (['sections-detail', 'sections-created', 'sections-updated', 'sections-added', 'sections-removed', 'sections-members-set'].includes(scenario)) {
        assert.deepEqual(await session.root.locator('.sl-research-references li').allTextContents(), fixture.native.data.member_ids);
        assert.equal(await session.root.getByRole('heading', { name: fixture.native.data.title, exact: true }).count(), 1);
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
        if (['hypotheses-observed', 'hypotheses-result-recorded'].includes(scenario)) {
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
        if (['surveys-instrument', 'surveys-detail'].includes(scenario)) {
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
      } else if (scenario.startsWith('councils-') && ['record-head-to-head', 'get-head-to-head', 'record-price-ladder', 'get-price-ladder', 'price-ladder-analysis', 'record-red-team', 'get-red-team', 'query-councils'].some(suffix => scenario === 'councils-' + suffix)) {
        const text = await session.root.innerText();
        assert.ok(text.includes('What changes the handover?'));
        if (scenario.includes('price')) {
          assert.ok(text.includes('Not answered') && text.includes('bargain: 2'));
          if (!scenario.includes('analysis')) assert.ok(text.includes('Repeated authored response.'));
          else assert.ok(!text.includes('Repeated authored response.'));
        } else if (scenario.includes('head-to-head')) {
          for (const value of ['Neither fits the night shift.', 'Intensity: 0', 'B → A', 'variant_a']) assert.ok(text.includes(value), value);
          const voters = session.root.locator('th').filter({ hasText: /^Voters$/ });
          assert.equal(await voters.count(), 1);
          assert.equal(await voters.evaluate(node => { const range = document.createRange(); range.selectNodeContents(node); return range.getClientRects().length; }), 1,
            'The Voters heading stays a readable unbroken word at 390px');
        }
        else if (scenario.includes('red-team')) for (const value of ['The final owner can still be absent.', 'unknown-native-token']) assert.ok(text.includes(value), value);
        else assert.ok(text.includes('Offset 0') && text.includes('1 statements · 0 votes · 0 questions'));
        if (scenario.includes('-record-')) assert.ok(text.includes('Keep the full final context.') && await session.root.locator('.sl-research-claim-notice').count() > 0);
        else assert.equal(await session.root.locator('.sl-research-council-voices').count(), 0);
      } else if (scenario.startsWith('councils-') && scenario !== 'councils-empty') {
        const text = await session.root.innerText();
        assert.ok(text.includes('What interrupts the handover?'));
        if (['councils-voices', 'councils-recorded'].includes(scenario)) {
          assert.equal(await session.root.locator('.sl-research-statement').count(), 1);
          const labels = session.root.locator('.sl-research-statement-body > .sl-research-statement-head > span');
          assert.equal(await labels.count(), scenario === 'councils-recorded' ? 1 : 2);
          if (scenario === 'councils-voices') {
            const stanceBox = await labels.nth(0).boundingBox(), postureBox = await labels.nth(1).boundingBox();
            assert.ok(postureBox.x >= stanceBox.x + stanceBox.width + 4 || postureBox.y >= stanceBox.y + stanceBox.height,
              'Each recorded stance and claim label remains visually separated');
          }
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
        if (['syntheses-convergence', 'syntheses-recorded'].includes(scenario)) {
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
        if (scenario.includes('funnel')) {
          assert.ok(text.includes(scenario.endsWith('-empty') ? 'Completed: 0 / 0' : 'Completed: 2 / 3'));
          if (['sessions-funnel', 'sessions-flow-funnel'].includes(scenario)) {
            assert.ok(text.includes('3 entered · 1 dropped') && text.includes('The next action was missing'));
            assert.deepEqual(await session.root.locator('meter').evaluateAll(nodes => nodes.map(node => node.value)), [0.666666666667, 0.333333333333]);
            if (scenario === 'sessions-flow-funnel') for (const value of ['Handover flow', 'Choose the next handover action', 'Dropped at step 0: 1', 'persona_fixture']) assert.ok(text.includes(value), value);
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
      } else if (fixture.family === 'plans') {
        const text = await session.root.innerText();
        if (fixture.state === 'empty') assert.ok(text.includes('No plan is recorded for this period.'));
        else for (const value of ['Keep the handover visible.', 'Confirm the owner', 'A named next shift', 'Less rushed', '2026-06-02', 'does not establish completed activity']) assert.ok(text.includes(value), value);
        assert.ok(!text.includes('Completed activity'));
      } else if (fixture.family === 'calendar') {
        const text = await session.root.innerText();
        assert.ok(!text.includes('<span') && !text.includes('<div'), 'Prepared semantic fragments are not printed as markup');
        if (fixture.state === 'empty') assert.ok(text.includes('No activity records supplied.'));
        else if (fixture.tool === 'get_current_state') {
          assert.ok(text.includes(fixture.native.data.at_time));
          assert.ok(text.includes(fixture.native.data.synthetic_notice));
          assert.ok(text.includes(fixture.native.data.current_activity));
          if (scenario === 'calendar-get-current-state') assert.ok(text.includes('Confirm the delivery') && text.includes('Waiting for delivery'));
        } else if (fixture.tool === 'get_calendar_period') {
          for (const value of ['Shift handover', '2026-06-02', 'uncertain', 'Events in this period: 1']) assert.ok(text.includes(value), value);
          assert.ok(text.includes(fixture.native.data.view));
          if (['day', 'year'].includes(fixture.native.data.view)) assert.ok(text.includes('Supplied activity records'));
        } else {
          for (const value of ['I will carry the pending issue.', 'Keep the issue visible.', 'note:note_fixture#line:2', 'A supplied source description.', 'disputed', 'simulated_episode', 'Recorded confidence']) assert.ok(text.includes(value), value);
          assert.equal(await session.root.locator('dt').filter({ hasText: /^Recorded confidence$/ }).locator('xpath=following-sibling::dd[1]').innerText(), '0');
          if (fixture.tool === 'get_calendar') assert.ok(text.includes('Planned review') && text.includes('Calendar block without a recorded activity'));
          for (const label of await session.root.locator('dt').filter({ hasText: /^(Participants|energy_delta)$/ }).all())
            assert.equal(await label.evaluate(node => { const range = document.createRange(); range.selectNodeContents(node); return range.getClientRects().length; }), 1,
              'Nested mobile definition labels remain whole readable words');
        }
        assert.equal(await session.root.locator('a,img,iframe,button').count(), 0);
      } else if (scenario.startsWith('prototypes-') && scenario !== 'prototypes-empty') {
        const text = await session.root.innerText();
        if (['prototypes-deleted', 'prototypes-missing'].includes(scenario)) {
          assert.ok(text.includes(`Prototype records deleted: ${scenario === 'prototypes-deleted' ? 1 : 0}`));
          assert.ok(text.includes('Files on disk remain'));
        } else if (['prototypes-stopped', 'prototypes-idle'].includes(scenario)) {
          assert.ok(text.includes(scenario === 'prototypes-stopped' ? 'native runner reports' : 'No local process was found'));
          assert.equal(text.includes('prototype_fixture'), scenario === 'prototypes-stopped');
        } else {
          assert.ok(text.includes('neither loaded nor executed'));
          assert.ok(await session.root.locator('dl dt').count() > 0);
          assert.equal(await session.root.locator('dt').count(), await session.root.locator('dd').count());
          if (scenario === 'prototypes-running') assert.ok(text.includes('Local process started') && text.includes('12345'));
          else if (scenario === 'prototypes-reused') assert.ok(text.includes('Existing local process') && text.includes('12345'));
          else if (scenario === 'prototypes-hosted') assert.ok(text.includes('Hosted prototype address') && !text.includes('Process ID'));
          else {
            assert.ok(text.includes('v0.'));
            if (scenario === 'prototypes-remote') assert.ok(text.includes('Handover needs a visible owner'));
            if (scenario === 'prototypes-detail') assert.ok(text.includes('No local process') && text.includes('Synthetic authored artifact metadata.'));
          }
        }
        assert.equal(await session.root.locator('a,img,iframe,button').count(), 0);
      } else if (scenario.startsWith('references-') && scenario !== 'references-empty') {
        const text = await session.root.innerText();
        if (scenario === 'references-deleted') assert.ok(text.includes('1 references removed'));
        else {
          assert.ok(text.includes('Handover concept') && text.includes('https://example.invalid/handover'));
          if (scenario === 'references-added') assert.ok(text.includes('Capture skipped') && !text.includes('next shift'));
          else if (scenario === 'references-failed') assert.ok(text.includes('Synthetic capture failure'));
          else assert.ok(text.includes('Only the supplied snapshot is shown.') && text.includes('Current owner'));
        }
        assert.equal(await session.root.locator('a,img,iframe,button').count(), 0);
      } else if (scenario.startsWith('assets-') && scenario !== 'assets-empty') {
        const text = await session.root.innerText();
        if (['assets-detached', 'assets-missing'].includes(scenario)) {
          assert.ok(text.includes(`${scenario === 'assets-detached' ? 1 : 0} files detached`));
          assert.ok(text.includes('file contents remain'));
        } else {
          assert.ok(text.includes('Handover') && text.includes('Provenance'));
          assert.ok(text.includes(scenario === 'assets-detail' ? 'synthesis:synthesis_fixture' : scenario === 'assets-shot' ? 'prototype:prototype_fixture' : scenario === 'assets-admitted' ? 'remote_mcp:direct_upload' : 'Authored fixture text'));
          if (['assets-admitted', 'assets-shot'].includes(scenario)) assert.ok(text.includes('image pixels were not supplied'));
          if (scenario === 'assets-list') assert.ok(!text.includes('Keep the owner clear.'));
          if (scenario === 'assets-detail') assert.ok(text.includes('handover-v1.txt') && text.includes('Keep the owner clear.'));
        }
        assert.equal(await session.root.locator('img,a,button,details').count(), 0);
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
    const result = structuredClone(noteFixture.result);
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

test('only the explicit native disclosure primitive survives and always starts closed', async () => {
  const session = await openApp(browser);
  try {
    await session.send(toolResult('<details class="sl-research-disclosure" open onclick="window.compromised=true" name="cross-card"><summary tabindex="4" onclick="window.compromised=true">Local details</summary><p>Retained information</p></details><details open><summary>Legacy details</summary><p>Still flat</p></details>'));
    await session.rendered();
    assert.equal(await session.root.locator('details').count(), 1);
    assert.equal(await session.root.locator('summary').count(), 1);
    const details = session.root.locator('details');
    assert.deepEqual(await details.evaluate(node => Array.from(node.attributes, x => x.name)), ['class']);
    assert.equal(await details.locator('summary').evaluate(node => node.attributes.length), 0);
    assert.ok((await session.root.textContent()).includes('Retained information'));
    assert.ok(!(await session.root.innerText()).includes('Retained information'));
    await details.locator('summary').click();
    assert.ok((await session.root.innerText()).includes('Retained information'));
    assert.equal(await session.frame.locator('body').evaluate(() => window.compromised), undefined);
    await session.assertPassive();
  } finally { await session.page.close(); }
});
