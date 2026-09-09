// Selected presentation and integration inputs, not a transitive Python install.
// The immutable customer release still pins all repository bytes. SDK code is
// separately bound by the lockfile and the complete bundled resource digest.
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

export const commonSourceInputs = [
  // Shared browser transport, sanitizer, styles and build inputs.
  'sonaloop/web/assets/research-view/research-mcp.js',
  'sonaloop/web/assets/research-view/research-view.js',
  'sonaloop/web/assets/research-view/research.css',
  'tools/persona-ui/build-research.mjs', 'tools/persona-ui/build-component-declarations.mjs',
  'tools/persona-ui/research-source-inputs.mjs', 'tools/persona-ui/test/research-browser.mjs',
  'tools/persona-ui/package.json', 'tools/persona-ui/package-lock.json',
  // Common registration, coverage, public props and primitive presentation.
  'sonaloop/mcp_server/_research_ui.py',
  'sonaloop/ui_components/__init__.py', 'sonaloop/ui_components/registry.py',
  'sonaloop/ui_components/coverage.py', 'sonaloop/ui_components/coverage.json',
  'sonaloop/ui_components/component_props.py', 'sonaloop/ui_components/library.py',
  'sonaloop/ui_components/statements.py',
  // Canonical product wiring and shared semantic helpers. These remain explicit
  // shared identities even when a particular scenario uses only part of a file.
  'sonaloop/web/pages/_ctx.py', 'sonaloop/web/_html.py', 'sonaloop/web/_i18n.py',
  'sonaloop/web/_i18n_strings.py', 'sonaloop/web/_components.py', 'sonaloop/web/_render.py',
  'sonaloop/web/_presence.py', 'sonaloop/web/_primitive_taxonomy.py', 'sonaloop/web/_vm.py',
  'sonaloop/web/ui.py', 'sonaloop/artifacts.py', 'sonaloop/suggestions/stance_scale.json',
];

export const familySourceInputs = {
  catalog: ["sonaloop/ui_components/persona_catalog.py", "sonaloop/ui_components/persona_catalog_rows.py", "sonaloop/ui_components/projects_rows.py", "sonaloop/web/pages/personas.py", "sonaloop/web/pages/_catalog_results.py", "tools/persona-ui/fixtures/catalog.json"],
  chats: ["sonaloop/ui_components/chats.py", "sonaloop/ui_components/chat_rows.py", "sonaloop/ui_components/chat_proposals.py", "sonaloop/ui_components/projects_rows.py", "sonaloop/web/pages/personas.py", "sonaloop/web/pages/_persona_chats.py", "tools/persona-ui/fixtures/chats.json"],
  records: ['sonaloop/ui_components/persona_records.py', 'sonaloop/ui_components/persona_record_rows.py', 'sonaloop/ui_components/projects_rows.py', 'sonaloop/web/pages/personas.py', 'sonaloop/web/pages/_persona_records.py', 'tools/persona-ui/fixtures/records.json'],
  profiles: ['sonaloop/ui_components/persona_profiles.py', 'sonaloop/ui_components/persona_profile_rows.py', 'sonaloop/ui_components/projects_rows.py', 'sonaloop/web/pages/personas.py', 'sonaloop/web/pages/_persona_profiles.py', 'sonaloop/web/_routes_lists.py', 'tools/persona-ui/fixtures/profiles.json'],
  cohorts: ['sonaloop/ui_components/cohort.py', 'sonaloop/ui_components/cohort_rows.py', 'sonaloop/ui_components/cohort_preflight.py', 'sonaloop/ui_components/projects_rows.py', 'sonaloop/web/_cohort_integrity_view.py', 'sonaloop/web/pages/_cohort_results.py', 'sonaloop/web/pages/personas.py', 'sonaloop/web/pages/projects.py', 'tools/persona-ui/fixtures/cohorts.json'],
  preparation: ["sonaloop/ui_components/persona_preparation.py", "sonaloop/ui_components/persona_preparation_rows.py", "sonaloop/ui_components/projects_rows.py", "sonaloop/ui_components/memory.py", "sonaloop/ui_components/memory_rows.py", "sonaloop/web/pages/personas.py", "sonaloop/web/pages/_persona_preparation.py", "tools/persona-ui/fixtures/preparation.json"],
  runs: ['sonaloop/ui_components/run_journal.py', 'sonaloop/ui_components/run_journal_rows.py', 'sonaloop/web/pages/_run_journal.py', 'sonaloop/web/pages/projects.py', 'tools/persona-ui/fixtures/run-journal.json', 'tools/persona-ui/fixtures/project-health.json', 'sonaloop/ui_components/project_health.py', 'sonaloop/ui_components/projects_rows.py', 'sonaloop/web/_runs_widget.py'],
  memory: ['tools/persona-ui/fixtures/memory.json', 'sonaloop/ui_components/memory.py', 'sonaloop/ui_components/memory_rows.py', 'sonaloop/ui_components/memory_outcomes.py', 'sonaloop/web/pages/personas.py'],
  calendar: ['tools/persona-ui/fixtures/calendar-plans.json', 'sonaloop/ui_components/calendar.py', 'sonaloop/web/pages/personas.py', 'sonaloop/web/pages/_calendar.py'],
  plans: ['tools/persona-ui/fixtures/calendar-plans.json', 'sonaloop/ui_components/plans.py', 'sonaloop/web/pages/personas.py'],
  prototypes: ['sonaloop/ui_components/prototypes.py', 'sonaloop/web/pages/library.py'],
  references: ['sonaloop/ui_components/references.py', 'sonaloop/web/pages/library.py'],
  assets: ['sonaloop/ui_components/assets.py', 'sonaloop/web/pages/assets.py'],
  notes: ['sonaloop/web/pages/library.py'],
  sections: ['sonaloop/web/pages/library.py'],
  projects: ['sonaloop/ui_components/project_graph.py', 'sonaloop/ui_components/project_results.py',
    'sonaloop/ui_components/project_health.py', 'sonaloop/ui_components/predictions.py',
    'sonaloop/ui_components/assets.py', 'sonaloop/ui_components/references.py', 'sonaloop/ui_components/prototypes.py',
    'sonaloop/ui_components/council_formats.py', 'sonaloop/ui_components/syntheses.py', 'sonaloop/ui_components/reports.py',
    'sonaloop/web/_graph_outline.py', 'sonaloop/web/_runs_widget.py', 'sonaloop/web/_report.py',
    'sonaloop/web/_synthesis.py', 'sonaloop/charts_catalogue.py', 'sonaloop/_charts.py',
    'sonaloop/suggestions/finding_kinds.json', 'tools/persona-ui/fixtures/projects.json', 'sonaloop/ui_components/projects.py', 'sonaloop/ui_components/projects_rows.py', 'sonaloop/ui_components/discovery.py', 'sonaloop/web/pages/projects.py'],
  search: ['sonaloop/ui_components/projects_rows.py', 'sonaloop/ui_components/discovery.py', 'sonaloop/web/_routes_api.py', 'sonaloop/web/_palette.py'],
  hypotheses: ['sonaloop/ui_components/bets.py', 'sonaloop/web/pages/hypotheses.py'],
  decisions: ['sonaloop/ui_components/bets.py', 'sonaloop/web/pages/decisions.py'],
  // Product Council sentiment and Session funnel charts share _synthesis.py;
  // they do not use the Synthesis family's full report renderer.
  councils: ['tools/persona-ui/fixtures/council-formats.json', 'sonaloop/ui_components/councils.py', 'sonaloop/ui_components/council_formats.py', 'sonaloop/web/pages/councils.py', 'sonaloop/web/_synthesis.py'],
  surveys: ['sonaloop/ui_components/surveys.py', 'sonaloop/web/pages/surveys.py'],
  syntheses: ['sonaloop/ui_components/syntheses.py', 'sonaloop/ui_components/reports.py',
    'sonaloop/web/_report.py', 'sonaloop/web/_synthesis.py', 'sonaloop/web/pages/syntheses.py',
    'sonaloop/charts_catalogue.py', 'sonaloop/_charts.py', 'sonaloop/suggestions/finding_kinds.json'],
  // Passive Session funnels reuse the actual Survey count_row helper.
  sessions: ['sonaloop/ui_components/sessions.py', 'sonaloop/ui_components/session_steps.py',
    'sonaloop/ui_components/session_funnels.py', 'sonaloop/ui_components/surveys.py',
    'sonaloop/web/pages/sessions.py', 'sonaloop/web/_synthesis.py',
    'sonaloop/suggestions/friction_levels.json', 'sonaloop/suggestions/likelihood_levels.json'],
};

export function componentSourceInputs(family) {
  if (!Object.hasOwn(familySourceInputs, family)) throw new Error(`No source ownership declared for ${family}`);
  const inputs = [...new Set([...commonSourceInputs, ...familySourceInputs[family],
    `sonaloop/ui_components/declarations/${family}.json`])].sort();
  if (inputs.length > 64) throw new Error(`Component ${family} exceeds the source manifest limit`);
  return inputs;
}

export async function componentSourceHashes(repo, family, read = readFile) {
  const sources = {};
  for (const path of componentSourceInputs(family))
    sources[path] = createHash('sha256').update(await read(resolve(repo, path))).digest('hex');
  return sources;
}
