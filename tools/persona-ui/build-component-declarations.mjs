// Customer-owned public examples; only the pure synthetic fixture renderer runs.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { canonical, nativeFixtureSet, repo } from './test/research-browser.mjs';

function alternatives(values) {
  const unique = [...new Map(values.map(value => [canonical(value), value])).values()];
  assert.ok(unique.length <= 8, 'Split an over-broad Component prop union explicitly');
  return unique.length === 1 ? unique[0] : { anyOf: unique };
}
function shape(values) {
  const types = new Map();
  for (const value of values) {
    const type = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
    types.set(type, [...(types.get(type) || []), value]);
  }
  return alternatives([...types].map(([type, samples]) => {
    if (type === 'null') return { type: 'null' };
    if (type === 'array') {
      const items = samples.flat();
      return { type: 'array', maxItems: items.length ? 32 : 0, items: items.length ? shape(items) : false };
    }
    if (type === 'object') {
      const keys = [...new Set(samples.flatMap(value => Object.keys(value)))];
      return { type: 'object', additionalProperties: false,
        properties: Object.fromEntries(keys.map(key => [key, shape(samples.filter(value => key in value).map(value => value[key]))])),
        required: keys.filter(key => samples.every(value => key in value)) };
    }
    if (type === 'string') return { type: 'string', maxLength: 6000 };
    if (type === 'number') return { type: samples.every(Number.isInteger) ? 'integer' : 'number' };
    assert.equal(type, 'boolean');
    return { type: 'boolean' };
  }));
}
function boundSchema(value, depth = 0, detailDepth = 10) {
  if (Array.isArray(value)) return value.map(item => boundSchema(item, depth + 1, detailDepth));
  if (!value || typeof value !== 'object') return value;
  // The public schema format shares a 12-level traversal budget with examples.
  // Deep compound values keep an explicit JSON type. Complete shape/business
  // validation remains in the existing customer renderer, never in this catalog.
  if (depth >= detailDepth && typeof value.type === 'string') return { type: value.type };
  return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, boundSchema(child, depth + 1, detailDepth)]));
}
function jsonDepth(value) {
  return value && typeof value === 'object' ? Math.max(0, ...Object.values(value).map(child => 1 + jsonDepth(child))) : 0;
}
const labels = { preparation: "Persona preparation", runs: 'Project Health and Run Diagnostics', memory: 'Memory and Recorded Experience', calendar: 'Recorded Calendar and Activities', plans: 'Recorded Plans', prototypes: 'Prototypes', references: 'Captured References', assets: 'Files and Evidence', notes: 'Notes', sections: 'Sections', projects: 'Projects', search: 'Search',
  hypotheses: 'Hypotheses', decisions: 'Decisions', councils: 'Councils', surveys: 'Surveys',
  syntheses: 'Syntheses and Reports', sessions: 'Sessions and Funnels' };
const { fixtures } = await nativeFixtureSet();
const directory = resolve(repo, 'sonaloop/ui_components/declarations');
await mkdir(directory, { recursive: true });
for (const [family, name] of Object.entries(labels)) {
  const examples = fixtures.filter(item => item.family === family);
  const scenarios = examples.map(item => ({ id: item.scenario,
    label: item.scenario.split('-').slice(1).join(' ').replace(/^./, letter => letter.toUpperCase()),
    state: item.state, variant: 'default', size: 'responsive', theme: 'light',
    props: { name: item.tool, value: item.public_value } }));
  for (const item of scenarios) assert.ok(Buffer.byteLength(canonical(item.props)) <= 8192);
  const projectionNames = [...new Set(scenarios.map(item => item.props.name))];
  const selectors = projectionNames.map(name => ({ type: 'object', additionalProperties: false,
    properties: { name: { type: 'string', const: name },
      value: shape(scenarios.filter(item => item.props.name === name).map(item => item.props.value)) },
    required: ['name', 'value'] }));
  // Name selectors remain disjoint and retain each projection's own required
  // fields. Nested bounded groups preserve the eight-branch schema limit.
  const selection = selectors.length <= 8 ? selectors : Array.from({ length: Math.ceil(selectors.length / 8) },
    (_, index) => ({ type: 'object', oneOf: selectors.slice(index * 8, index * 8 + 8) }));
  assert.ok(selection.length <= 8, 'Too many distinct public projection selectors');
  const authoredSchema = { $schema: 'https://json-schema.org/draft/2020-12/schema', type: 'object',
    description: 'Authored public input to render_component_props(component_id, {name, value}). Name selects an existing pure projection; value supplies its synthetic view-model DTO. Deep compound values retain their JSON type; the selected renderer checks its required presentation fields. This does not replace native business validation or call an MCP tool.',
    oneOf: selection };
  let propsSchema = boundSchema(authoredSchema);
  // Preserve existing bounded declarations. Deeper grouped nullable fields
  // need room for the union array, its branch and the branch's type value.
  if (jsonDepth(propsSchema) > 12) propsSchema = boundSchema(authoredSchema, 0, 8);
  assert.ok(jsonDepth(propsSchema) <= 12, 'Public schema still exceeds its traversal budget');
  const disclosures = ['projects', 'runs', 'preparation'].includes(family);
  const requiredStates = ['focus', 'loading', 'disabled', 'empty', 'error', 'success'].map(state => ({ state,
    disposition: state === 'disabled' || state === 'focus' && !disclosures ? 'not_applicable' : 'applicable',
    scenarioIds: scenarios.filter(item => item.state === ({ empty: 'empty', success: 'ready' }[state] || '')).map(item => item.id),
    reason: state === 'focus' ? disclosures ? 'Local native disclosure summaries are keyboard focusable; automated keyboard checks exist, but no public focus-state raster is supplied.' : 'This passive result surface has no focusable controls or actions.'
      : state === 'disabled' ? 'This passive result surface grants no actions to disable.'
      : ['loading', 'error'].includes(state) ? 'The App supports this transport state; a public DTO scenario and matching raster are not supplied in this declaration.'
      : 'Examples use authored synthetic view-model values and the shared customer renderer.' }));
  const declaration = { schemaVersion: 'sonaloop.customer-component.v1', name,
    description: 'Shared Research product and passive MCP result content. Public examples are synthetic; they prove no customer runtime execution or research finding.',
    propsSchema, axes: { variants: ['default'], sizes: ['responsive'], themes: ['light'] }, scenarios, requiredStates,
    accessibility: { keyboard: 'not_reviewed', screenReader: 'not_reviewed',
      notes: (disclosures ? 'Native details disclosures start closed and toggle locally without tools or network. ' : '') + 'Passive semantic headings, text, lists and tables; no action controls. Automated checks preserve passive semantics and bounded table header scopes. No human keyboard or screen-reader acceptance is claimed.' } };
  assert.ok(Buffer.byteLength(canonical(propsSchema)) <= 24576);
  assert.ok(Buffer.byteLength(canonical(declaration)) <= 98304);
  await writeFile(resolve(directory, `${family}.json`), `${canonical(declaration)}\n`);
  console.log(JSON.stringify({ family, scenarios: scenarios.length, schemaBytes: Buffer.byteLength(canonical(propsSchema)) }));
}
