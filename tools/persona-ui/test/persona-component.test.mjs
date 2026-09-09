import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { build } from 'esbuild';
import Ajv2020 from 'ajv/dist/2020.js';
import { chromium } from 'playwright-core';
import { PERSONA_PROPS_SCHEMA, validatePersonaProps } from '../../../sonaloop/web/assets/persona-view/persona-public-props.js';
import { personaPublicProps, personaComponentScenario, PERSONA_COMPONENT_SCENARIO } from './persona-component-fixtures.mjs';

const repo = new URL('../../../', import.meta.url);
const declaration = JSON.parse(await readFile(new URL('sonaloop/ui_components/declarations/persona.json', repo)));
const validateSchema = new Ajv2020({ strict: true, allErrors: true }).compile(declaration.propsSchema);

test('Persona declaration describes the actual JSON entry and honest state limits', () => {
  assert.equal(declaration.schemaVersion, 'sonaloop.customer-component.v1');
  assert.deepEqual(declaration.propsSchema, PERSONA_PROPS_SCHEMA);
  assert.equal(declaration.scenarios.length, 1);
  const scenario = declaration.scenarios[0];
  assert.equal(scenario.id, PERSONA_COMPONENT_SCENARIO);
  assert.equal(scenario.state, 'ready', 'Missing avatar is valid content, not an empty Persona');
  assert.deepEqual(scenario.props, personaPublicProps());
  assert.ok(validateSchema(scenario.props), JSON.stringify(validateSchema.errors));
  assert.deepEqual(validatePersonaProps(scenario.props), scenario.props);
  assert.equal(JSON.stringify(scenario.props).includes('_meta'), false);
  const states = Object.fromEntries(declaration.requiredStates.map(item => [item.state, item]));
  assert.equal(Object.keys(states).length, 6);
  for (const state of ['focus', 'loading', 'error']) {
    assert.equal(states[state].disposition, 'applicable');
    assert.deepEqual(states[state].scenarioIds, []);
  }
  assert.equal(states.empty.disposition, 'not_applicable');
  for (const state of ['success', 'disabled']) assert.deepEqual(states[state].scenarioIds, [scenario.id]);
  assert.equal(declaration.accessibility.keyboard, 'not_reviewed');
  assert.equal(declaration.accessibility.screenReader, 'not_reviewed');
  const bridge = personaComponentScenario();
  assert.deepEqual(bridge.input, { persona_id: scenario.props.value.persona_id });
  assert.deepEqual(bridge.result.structuredContent, scenario.props.value);
  assert.deepEqual(JSON.parse(bridge.result.content[0].text), scenario.props.value);
});

const mutations = [
  ['actions', p => { p.actions = {}; }],
  ['transport', p => { p.operation_id = 'not-authority'; }],
  ['private metadata', p => { p.value._meta = {}; }],
  ['editable capabilities', p => { p.value.capabilities.edit = ['display_name']; }],
  ['generation capability', p => { p.value.capabilities.generate_avatar = true; }],
  ['null Persona', p => { p.value = null; }],
  ['wrong native field', p => { p.value.fields.goals = {}; }],
  ['missing version', p => { delete p.value.version; }],
  ['empty identity', p => { p.value.persona_id = ''; }],
  ['unsupported locale', p => { p.locale = 'unknown'; }],
  ['image source', p => { p.avatarSource = 'https://example.invalid/image.png'; }],
];
for (const [label, mutate] of mutations) test(`Closed Persona props reject ${label}`, () => {
  const props = personaPublicProps(); mutate(props);
  assert.equal(validateSchema(props), false);
  assert.throws(() => validatePersonaProps(props));
});

test('Native hash syntax remains stricter than the bounded public schema', () => {
  const props = personaPublicProps(); props.value.avatar.sha256 = 'Z'.repeat(64);
  assert.ok(validateSchema(props), 'Frozen public schema allows bounded text, not pattern validation');
  assert.throws(() => validatePersonaProps(props), /Invalid Persona surface/);
});

test('Public props enforce JSON traversal/byte bounds without narrowing optional empty fields', () => {
  const optional = personaPublicProps();
  Object.assign(optional.value.fields, { age: null, location: null, role_title: null, portrait_description: null,
    goals: [], pain_points: [] });
  assert.ok(validateSchema(optional)); assert.deepEqual(validatePersonaProps(optional), optional);
  const huge = personaPublicProps(); huge.value.fields.goals = Array(10).fill('x'.repeat(1000));
  assert.throws(() => validatePersonaProps(huge), /byte limit/);
  const nonfinite = personaPublicProps(); nonfinite.value.fields.age = NaN;
  assert.throws(() => validatePersonaProps(nonfinite), /finite JSON/);
  const cyclic = personaPublicProps(); cyclic.value.warnings = [cyclic];
  assert.throws(() => validatePersonaProps(cyclic), /traversal limits/);
  const reserved = personaPublicProps(); reserved.value.fields = JSON.parse('{"constructor":"not-a-prop"}');
  assert.throws(() => validatePersonaProps(reserved), /reserved/);
});

test('Actual browser JSON entry updates escaped fields and never installs transport/actions', { timeout: 20000 }, async () => {
  const bundle = (await build({ stdin: { contents:
    `import {createPersonaFromProps} from './sonaloop/web/assets/persona-view/persona-public-props.js';window.persona=createPersonaFromProps(document.querySelector('main'),window.props);`,
    resolveDir: repo.pathname }, bundle: true, format: 'iife', write: false, target: 'es2022' })).outputFiles[0].text;
  const browser = await chromium.launch({ executablePath: process.env.RESEARCH_BROWSER_EXECUTABLE || chromium.executablePath(), headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 1000 } });
  const requests = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => { requests.push(route.request().url()); return route.abort(); });
  try {
    await page.setContent('<main></main>');
    await page.evaluate(props => { window.props = props; }, personaPublicProps());
    await page.addScriptTag({ content: bundle });
    const card = page.locator('.sl-persona-view');
    assert.equal(await card.locator('button:enabled').count(), 0);
    assert.equal(await card.locator('[data-field],img,form,dialog').count(), 0);
    await card.locator('summary').focus();
    assert.ok(await card.locator('summary').evaluate(node => node === document.activeElement), 'Details remains focusable');
    await card.locator('summary').press('Enter');
    assert.equal(await card.locator('details[open]').count(), 1);
    assert.deepEqual(await page.evaluate(() => window.props), personaPublicProps());
    const next = personaPublicProps(); next.locale = 'de'; next.value.version = 'fixture-version-2';
    next.value.fields.display_name = '<img src=x onerror="window.bad=true">';
    await page.evaluate(props => window.persona.update(props), next);
    assert.equal(await card.locator('h2').innerText(), next.value.fields.display_name);
    assert.equal(await card.locator('img').count(), 0);
    assert.equal(await page.evaluate(() => window.bad), undefined);
    assert.equal(await card.locator('summary').innerText(), 'Details');
    assert.ok(await card.getByText('Rolle', { exact: true }).isVisible());
    const writable = personaPublicProps(); writable.value.capabilities.generate_avatar = true;
    await assert.rejects(page.evaluate(props => window.persona.update(props), writable), /read-only/);
    assert.equal(await card.locator('h2').innerText(), next.value.fields.display_name, 'Rejected update retains the current card');
    await page.evaluate(() => window.persona.dispose());
    assert.equal(await page.locator('.sl-persona-view').count(), 0);
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
  } finally { await browser.close(); }
});
