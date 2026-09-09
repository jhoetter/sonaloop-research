import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { componentSourceInputs, componentSourceHashes, familySourceInputs } from '../research-source-inputs.mjs';
import { repo, canonical, sha } from './research-browser.mjs';

test('every family has bounded explicit ownership and only its own declaration', async () => {
  const covered = new Set();
  for (const family of Object.keys(familySourceInputs)) {
    const inputs = componentSourceInputs(family);
    assert.ok(inputs.length < 64);
    assert.deepEqual(inputs.filter(path => path.includes('/declarations/')), [`sonaloop/ui_components/declarations/${family}.json`]);
    for (const path of inputs) { assert.ok((await readFile(resolve(repo, path))).length > 0); covered.add(path); }
  }
  for (const file of await readdir(resolve(repo, 'sonaloop/ui_components')))
    if (file.endsWith('.py')) assert.ok(covered.has(`sonaloop/ui_components/${file}`), `Unassigned presentation source ${file}`);
  assert.throws(() => componentSourceInputs('unknown'), /No source ownership/);
});

test('owned and shared source mutations change exact families without editing the checkout', async () => {
  const names = Object.keys(familySourceInputs), cache = new Map();
  const read = async path => { if (!cache.has(path)) cache.set(path, await readFile(path)); return cache.get(path); };
  const identity = async (family, changed) => sha(canonical(await componentSourceHashes(repo, family,
    async path => changed === path ? Buffer.concat([await read(path), Buffer.from('\n# Synthetic mutation\n')]) : read(path))));
  const baseline = new Map(await Promise.all(names.map(async family => [family, await identity(family)])));
  for (const [path, affected] of [
    ['sonaloop/ui_components/surveys.py', ['surveys', 'sessions']],
    ['sonaloop/ui_components/councils.py', ['councils']],
    ['sonaloop/ui_components/calendar.py', ['calendar']],
    ['sonaloop/ui_components/plans.py', ['plans']],
    ['sonaloop/ui_components/memory.py', ['memory', 'preparation']],
    ['sonaloop/ui_components/project_graph.py', ['projects']],
    ['sonaloop/ui_components/projects_rows.py', ['projects', 'search', 'runs', 'preparation', 'profiles', 'cohorts', 'records', 'chats']],
    ['sonaloop/ui_components/project_health.py', ['projects', 'runs']],
    ['sonaloop/ui_components/memory_rows.py', ['memory', 'preparation']],
    ['sonaloop/ui_components/memory_outcomes.py', ['memory']],
    ['tools/persona-ui/fixtures/memory.json', ['memory']],
    ['sonaloop/ui_components/prototypes.py', ['prototypes', 'projects']],
    ['tools/persona-ui/fixtures/calendar-plans.json', ['calendar', 'plans']],
    ['sonaloop/suggestions/finding_kinds.json', ['syntheses', 'projects']],
    ['sonaloop/web/_synthesis.py', ['councils', 'syntheses', 'sessions', 'projects']],
    ['sonaloop/ui_components/declarations/notes.json', ['notes']],
    ['sonaloop/ui_components/statements.py', names],
    ['sonaloop/web/_html.py', names],
  ]) for (const family of names)
    assert.equal(await identity(family, resolve(repo, path)) !== baseline.get(family), affected.includes(family), `${path} → ${family}`);
});

test('published manifests match the selected ownership map exactly', async () => {
  for (const family of Object.keys(familySourceInputs)) {
    const manifest = JSON.parse(await readFile(resolve(repo, `sonaloop/mcp_server/ui/${family}.manifest.json`)));
    assert.deepEqual(manifest.sources, await componentSourceHashes(repo, family));
  }
});

test('public schemas remain bounded after nested projection groups and nullable fields', async () => {
  for (const family of Object.keys(familySourceInputs)) {
    const declaration = JSON.parse(await readFile(resolve(repo, `sonaloop/ui_components/declarations/${family}.json`)));
    const pending = [{ value: declaration.propsSchema, depth: 0 }];
    let nodes = 0;
    while (pending.length) {
      const { value, depth } = pending.pop();
      assert.ok(++nodes <= 2048 && depth <= 12, `${family}: public schema traversal budget`);
      if (value && typeof value === 'object')
        for (const child of Object.values(value)) pending.push({ value: child, depth: depth + 1 });
    }
    assert.ok(Buffer.byteLength(canonical(declaration.propsSchema)) <= 24576);
  }
});
