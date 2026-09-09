// Synthetic, transport-real customer UI qualification. Never invokes a native tool.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import { readFile, writeFile, mkdir, mkdtemp, link } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { build } from 'esbuild';
import { chromium } from 'playwright-core';

const execFile = promisify(execFileCallback);
export const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
export const browserExecutable = process.env.RESEARCH_BROWSER_EXECUTABLE || chromium.executablePath();
export const sha = bytes => createHash('sha256').update(bytes).digest('hex');
export const canonical = value => JSON.stringify(value, (_, item) =>
  item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const origin = 'http://127.0.0.1:17479'; // Intercepted entirely: no socket is bound.

const hostSource = `import {AppBridge,PostMessageTransport} from '@modelcontextprotocol/ext-apps/app-bridge';
const frame=document.querySelector('iframe'),seed=await(await fetch('/fixture/seed')).json();
const bridge=window.bridge=new AppBridge(null,{name:'Synthetic passive customer host',version:'1'},
  {logging:{}},{hostContext:{locale:seed.locale,theme:'light'}});
window.logs=[];window.calls=[];window.initialized=false;
bridge.onloggingmessage=value=>logs.push(value);
bridge.oncalltool=async value=>{calls.push(value);throw new Error('Fixture host grants no execution');};
bridge.onsizechange=({height})=>{frame.style.height=Math.max(100,Math.ceil(height))+'px';};
bridge.oninitialized=()=>{window.initialized=true;};
await bridge.connect(new PostMessageTransport(frame.contentWindow,frame.contentWindow));
frame.src='/fixture/app';`;
let hostBundlePromise;
async function hostBundle() {
  hostBundlePromise ||= build({ stdin: { contents: hostSource, resolveDir: resolve(repo, 'tools/persona-ui') },
    bundle: true, format: 'esm', write: false, target: 'es2022' }).then(value => value.outputFiles[0].text);
  return hostBundlePromise;
}

export async function loadAsset(family, { verifySources = false } = {}) {
  assert.match(family, /^[a-z]+$/);
  const manifestBytes = await readFile(resolve(repo, `sonaloop/mcp_server/ui/${family}.manifest.json`));
  const manifest = JSON.parse(manifestBytes);
  const resource = await readFile(resolve(repo, 'sonaloop/mcp_server/ui', manifest.resource.file));
  assert.equal(sha(resource), manifest.resource.sha256, 'Packaged resource digest');
  assert.equal(resource.length, manifest.resource.bytes, 'Packaged resource byte count');
  const { build_id, ...declaration } = manifest;
  assert.equal(sha(canonical(declaration)), build_id, 'Manifest build identity');
  assert.deepEqual(manifest.actions, [], 'Passive resource exposes no actions');
  if (verifySources) for (const [path, digest] of Object.entries(manifest.sources))
    assert.equal(sha(await readFile(resolve(repo, path))), digest, `Stale manifest source: ${path}`);
  return { manifest, manifestBytes, resource };
}

export async function launchBrowser() {
  return chromium.launch({ executablePath: browserExecutable, headless: true });
}

async function resourceWithLoggingFailure(resource) {
  // Opaque WindowProxy access bypasses a parent's postMessage monkey-patch.
  // Inject a single notification failure at the real SDK boundary instead. The
  // actual adapter, initialization, result notifications and bridge stay intact.
  // This fixture resource is never used by exportScenarios or bound to receipts.
  const sdk = fileURLToPath(import.meta.resolve('@modelcontextprotocol/ext-apps'));
  const injected = await build({ entryPoints: [resolve(repo, 'sonaloop/web/assets/research-view/research-mcp.js')],
    bundle: true, format: 'iife', write: false, target: 'es2022', plugins: [{ name: 'reject-log-notification',
      setup(plugin) {
        plugin.onResolve({ filter: /^@modelcontextprotocol\/ext-apps$/ }, () => ({ path: 'logging-failure', namespace: 'fixture' }));
        plugin.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ loader: 'js', resolveDir: dirname(sdk), contents:
          `import {App as NativeApp} from ${JSON.stringify(sdk)};
           export class App extends NativeApp {
             async notification(message, ...options) {
               if (message.method === 'notifications/message') {
                 globalThis.__loggingTransportFailures = (globalThis.__loggingTransportFailures || 0) + 1;
                 throw new Error('Synthetic logging transport failure');
               }
               return super.notification(message, ...options);
             }
           }` }));
      } }] });
  const script = injected.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
  return Buffer.from(resource.toString().replace(/<script>[\s\S]*<\/script>/, () => `<script>${script}</script>`));
}

export async function openApp(browser, { family = 'notes', locale = 'en',
  viewport = { width: 960, height: 900 }, deviceScaleFactor = 1, rejectLogging = false } = {}) {
  const asset = await loadAsset(family), bundle = await hostBundle();
  const resource = rejectLogging ? await resourceWithLoggingFailure(asset.resource) : asset.resource;
  const page = await browser.newPage({ viewport, deviceScaleFactor });
  page.setDefaultTimeout(7000);
  const errors = [], blockedRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { blockedRequests.push(url.href); return route.abort(); }
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body:
      `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><iframe title="Research ${family}" sandbox="allow-scripts" style="display:block;width:100%;border:0"></iframe><script type="module">${bundle}</script></body></html>` });
    if (url.pathname === '/fixture/seed') return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ locale }) });
    if (url.pathname === '/fixture/app') return route.fulfill({ contentType: 'text/html', body: resource,
      headers: { 'Content-Security-Policy': "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; form-action 'none'" } });
    blockedRequests.push(url.href);
    return route.abort();
  });
  await page.goto(origin);
  await page.waitForFunction(() => window.initialized);
  const frame = page.frameLocator('iframe'), root = frame.locator('[data-research-app]');
  return { page, frame, root, asset, errors, blockedRequests, injectedLoggingFailure: rejectLogging,
    async send(result, input = {}) {
      await page.evaluate(async ({ result, input }) => {
        await window.bridge.sendToolInput({ arguments: input });
        await window.bridge.sendToolResult(result);
      }, { result, input });
    },
    async rendered() { await page.waitForFunction(() => window.logs.some(log => log.data?.event === 'view-rendered')); },
    async assertPassive() {
      assert.deepEqual(await page.evaluate(() => window.calls), []);
      assert.deepEqual(errors, []);
      assert.deepEqual(blockedRequests, []);
      assert.equal(await root.locator('a,script,style,img,iframe,object,embed,svg,math,video,audio,form,input,button,select,textarea').count(), 0);
    } };
}

export function toolResult(html, { family = 'notes', state = 'ready', text = 'Synthetic fixture result', tool = 'list_notes' } = {}) {
  return { content: [{ type: 'text', text }], _meta: { 'sonaloop/presentation': {
    schema_version: 'sonaloop.research-presentation.v1', component_id: `sonaloop.research.${family}-view`,
    tool, state, html, text_sha256: sha(text),
  } } };
}

// Calls only the pure renderer using authored DTOs. No server build, Store, service,
// provider, native tool invocation or runtime dataset is involved.
const fixturePython = String.raw`
import ast, json, sys
from pathlib import Path
def audit(event, args):
    if event in {"sqlite3.connect", "socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("Fixture renderer attempted runtime access: " + event)
sys.addaudithook(audit)
from sonaloop.ui_components.registry import render_tool, SURFACES
from sonaloop.ui_components.component_props import render_component_props, public_component_value
from sonaloop.ui_components.library import note_content
from sonaloop.ui_components.discovery import project_heading, search_hit_content
from sonaloop.web._render import render_ref
from sonaloop import artifacts
from sonaloop.web._i18n import _UI_LANG
_UI_LANG.set("en")
note = {"id": "note_fixture", "kind": "observation", "title": "Handover needs a visible owner",
        "text": "The team loses context when a shift changes.\n\n**Observation:** a short summary helps the next person begin.\n\n- Show the current owner\n- Keep unresolved questions visible\n\n> Synthetic example for component review, not research evidence."}
section = {"id": "section_fixture", "title": "Handover observations", "note": "Two references, supplied by the fixture.",
           "member_ids": ["note:note_fixture", "note:note_second"]}
members = [{"id": "note_fixture", "kind": "note", "title": note["title"], "summary": "The next shift needs context and a named owner.", "href": "/notes/note_fixture"},
           {"id": "note_second", "kind": "note", "title": "Open questions remain visible", "summary": "Unresolved issues stay attached to the handover.", "href": "/notes/note_second"}]
project = {"id": "project_fixture", "title": "Understanding shift handovers",
           "goal": "Learn what the next shift needs to continue the work.",
           "description": "A synthetic project for shared component review."}
hit = {"id": "project:project_fixture", "title": project["title"], "text": project["goal"], "url": "/projects/project_fixture"}
fetched = {**hit, "text": "## Handover questions\n\nWhat context helps the next shift?\n\n- Who owns the open issue?\n- What has already been checked?\n\n**Fixture:** this is a readable example, not collected research.",
           "metadata": {"kind": "project"}}
hypothesis = {"id": "hyp_fixture", "text": "A named owner reduces handover time",
              "prediction": {"metric": "minutes", "expected_value": 4, "tolerance": 1, "confidence": .8},
              "status": "open", "result": None, "derived_from": [{"kind": "council", "id": "council_fixture"}]}
resolved = {**hypothesis, "status": "validated", "result": {"observed_value": 4.5,
            "note": "The pilot falls within the predicted range.", "source": {"kind": "external", "text": "Synthetic observation, not research evidence"}}}
dropped = {**hypothesis, "status": "dropped", "drop_note": "The team no longer uses this handover process."}
decision = {"id": "dec_fixture", "title": "Name a handover owner", "decision": "Show the current owner before the next shift begins.\nKeep unresolved questions visible.",
            "status": "proposed", "based_on": [{"kind": "hypothesis", "id": "hyp_fixture"}],
            "rejected": [{"kind": "council", "id": "council_fixture", "note": "The alternative has no explicit owner."}]}
adopted = {**decision, "status": "adopted"}
successor = {**adopted, "id": "dec_next", "title": "Make the current owner visible", "supersedes": "dec_fixture"}
question = {"id": "q1", "text": "What helps the next shift?", "kind": "single", "options": ["Named owner", "Longer email"]}
survey = {"id": "survey_fixture", "title": "Handover feedback", "intro": "Synthetic survey instrument.",
          "status": "draft", "questions": [question], "derived_from": []}
survey_results = {"survey_id": "survey_fixture", "title": survey["title"], "status": "open", "responses": 3,
                  "questions": [{"question_id": "q1", "text": question["text"], "kind": "single", "answered": 3,
                                 "counts": {"Named owner": 2, "Longer email": 1}}]}
stance_counts = {term["term"]: 0 for term in artifacts.stance_terms()}
comparison = {"predicted": {"n": 2, "counts": {**stance_counts, "support": 2}, "refs": [{"kind": "council", "id": "council_fixture"}]},
              "actual": {"n": 3, "counts": {**stance_counts, "support": 1, "oppose": 2}}}
survey_comparison = {**survey_results, "questions": [{"question_id": "q1", "text": "Does a named owner help?", "kind": "scale",
    "answered": 3, "stance_mapped": True, "counts": {"Support": 1, "Oppose": 2}, "comparison": comparison}]}
survey_text = {**survey_results, "questions": [{"question_id": "q2", "text": "Why?", "kind": "text", "answered": 3,
    "answers": ["The next shift can find the owner.", "Only applies during the pilot."]}]}
council = {"id": "council_fixture", "prompt": "What interrupts the handover?", "persona_ids": ["persona_fixture"],
           "statements": [{"id": "s1", "persona_id": "persona_fixture", "text": "The next shift cannot identify the owner.",
                           "about": {"kind": "prompt", "id": "q0"}, "stance": {"value": -1, "label": "skeptical"},
                           "meta": {"claim_posture": "simulated"},
                           "refs": [{"kind": "external", "text": "Synthetic fixture, not observed research"}]}],
           "prompts": [{"id": "q0", "kind": "question", "text": "Where is ownership unclear?"}],
           "exec_summary": "Keep the current owner visible.", "votes": [], "findings": []}
# An ordinary non-Reaction writer fixture does not opt into governed claim posture.
# The distinct legacy getter below retains its supplied posture as a read projection.
council_recorded = {**council, "statements": [{**council["statements"][0], "meta": {}}]}
council_input = {**council, "prompts": [], "exec_summary": "",
                 "statements": [{"persona_id": "persona_fixture", "text": "This change helps during onboarding.",
                     "meta": {"input": "Show the current owner before the next shift begins.", "grounded": False,
                              "claim_posture": "simulated", "pushback": ["Who changes the owner?"]},
                     "shift": {"from": "uncertain", "to": "support", "trigger": "Explicit owner"}}]}
council_list = {"items": [{"id": "council_fixture", "prompt": council["prompt"], "personas": 2, "turns": 3,
                           "votes": {"support": 1, "oppose": 1}, "created_at": "2026-09-08T12:00:00Z"}],
                "total": 1, "has_more": False, "next_cursor": None}
from copy import deepcopy
synthesis = {"id": "synthesis_fixture", "title": "Handover synthesis", "scope": "convergence", "status": "done",
    "created_at": "2026-09-09T01:00:00Z", "start_input": "What helps the next shift?", "arc_narrative": "",
    "gesamtbild": "A named owner makes the handover easier.", "positionierung": "", "council_ids": [],
    "statements": [], "findings": [{"kind": "recommendation", "text": "Keep the current owner visible."}], "sections": []}
report_section = {"id": "section1", "heading": "Handover finding", "markdown": "Only observed during the pilot. ![[fig:1]]",
    "citations": [{"study_id": "council:fixture", "quote": "The owner is clear."}], "source_study_ids": ["council:fixture"],
    "figures": [{"kind": "asset", "id": "asset_fixture", "caption": "A recorded reference; no image pixels supplied."}]}
report = {**synthesis, "title": "Handover report", "scope": "project", "gesamtbild": "", "start_input": "", "findings": [],
    "sections": [report_section], "limitations": [{"original_status": "simulated", "rationale": "Synthetic component example."}]}
outline = {**report, "status": "in_progress", "limitations": [], "sections": [{**report_section, "markdown": "", "figures": [], "citations": []}]}
session_step = {"index": 0, "action": {"type": "look", "target": "Owner", "detail": "Read the owner panel"},
    "state": {"screen": "Owner panel", "screenshot": "step-0.png"}, "monologue": "I can find the person responsible.",
    "friction": {"level": "none", "note": ""}, "verdict": {"would_continue": True, "reason": "Owner is visible"}}
session_record = {"id": "session_fixture", "persona_id": "persona_fixture", "date": "2026-09-09", "fidelity": "artifact",
    "subject": {"kind": "flow", "id": "flow_fixture", "label": "Handover trace"}, "steps": [session_step], "statements": [],
    "outcome": {"completed": True, "dropoff_step": None, "summary": "Found the owner", "predicted_behaviors": []}}
session_dropped = deepcopy(session_record)
session_dropped["steps"][0]["verdict"] = {"would_continue": False, "reason": "The next action was missing"}
session_dropped["outcome"] = {"completed": False, "dropoff_step": 0, "summary": "The handover was abandoned", "predicted_behaviors": []}
session_salience = deepcopy(session_record)
session_salience["steps"][0]["state"]["focus"] = {"x": 10, "y": 20, "width": 30, "height": 40, "label": "Owner salience hypothesis"}
prototype_reaction = {"verdict": "The owner is clear", "observed_state_refs": ["Owner panel"],
    "timeline": [{"step": 4, "action": "Read the owner panel", "monolog": "The next action is missing", "observed": "Owner panel"}]}
prototype_session = {"id": "ps_fixture", "persona_id": "persona_fixture", "prototype_id": "prototype_fixture", "date": "2026-09-09",
    "prototype_version": "v0.7", "grounded_verified": False, "reaction": prototype_reaction}
funnel = {"subject": {"kind": "flow", "key": "flow_fixture"}, "sessions": 3, "completed": 2,
    "rows": [{"step": 0, "entered": 3, "continued": 2, "dropped": 1, "drop_reasons": ["The next action was missing"]}]}
asset = {"id": "asset_fixture", "kind": "document", "filename": "handover.txt", "title": "Handover evidence",
    "notes": "Synthetic file for component review, not research evidence.", "source": "Authored fixture text", "direction": "in",
    "media_type": "text/plain", "bytes": 21, "text_excerpt": "Keep the owner clear.", "created_at": "2026-09-09T00:00:00Z"}
asset_image = {**asset, "kind": "screenshot", "filename": "handover.png", "title": "Handover screenshot metadata",
    "media_type": "image/png", "bytes": 70, "text_excerpt": "", "source": "prototype:prototype_fixture"}
asset_prototype_shot = {**asset_image, "filename": "0123456789abcdef.png", "bytes": 74832}
asset_deliverable = {**asset, "direction": "out", "source": "synthesis:synthesis_fixture", "supersedes": [
    {"id": "asset_previous", "filename": "handover-v1.txt", "created_at": "2026-09-08T00:00:00Z"}]}
reference = {"id": "reference_fixture", "kind": "variant", "url": "https://example.invalid/handover", "title": "Handover concept", "label": "A", "captured_at": "2026-09-09T00:00:00Z",
    "snapshot": {"ok": True, "mode": "text", "description": "Synthetic captured page content.", "headings": ["Current owner", "Unresolved questions"], "text": "The next shift can find the current owner.\nOnly the supplied snapshot is shown."}}
reference_skipped = {**reference, "snapshot": {"ok": False, "mode": "skipped", "description": "", "headings": [], "text": ""}}
prototype = {"id": "prototype_fixture", "slug": "handover", "project_id": "project_fixture", "name": "Handover prototype", "version": "v0.2", "kind": "web", "type": "prototype", "path": "prototypes/handover", "entry": "index.html", "run": "static", "run_cmd": None, "notes": "Keep the owner visible.\nSynthetic authored artifact metadata.", "created_at": "2026-09-09T00:00:00Z", "fidelity": "midfi", "tags": ["midfi"], "url": ""}
remote_prototype = {**prototype, "id": "remote_fixture", "slug": "handover-remote", "name": "Hosted handover", "path": "", "entry": "", "run": "remote", "url": "https://example.invalid/handover", "fidelity": "hifi", "tags": ["hifi"]}
specs = [
    ("prototypes-scaffolded", "prototypes", "scaffold_prototype", {"slug": "handover", "name": prototype["name"], "concept": {"title": "Handover", "screens": [{"id": "home", "title": "Handover", "elements": []}]}, "project_id": "project_fixture", "fidelity": "midfi"}, {**prototype, "version": "v0.1", "notes": ""}),
    ("prototypes-registered", "prototypes", "register_prototype", {"slug": "handover", "name": prototype["name"], "path": prototype["path"], "version": "v0.2", "project_id": "project_fixture", "notes": prototype["notes"]}, prototype),
    ("prototypes-remote", "prototypes", "register_remote_prototype", {"slug": remote_prototype["slug"], "name": remote_prototype["name"], "url": remote_prototype["url"], "project_id": "project_fixture", "version": "v0.2", "note_id": "note_fixture"}, {"prototype": remote_prototype, "note": note}),
    ("prototypes-detail", "prototypes", "get_prototype", {"prototype_id": "prototype_fixture"}, {**prototype, "running": False}),
    ("prototypes-list", "prototypes", "list_prototypes", {"project_id": "project_fixture"}, [{**remote_prototype, "running": False}]),
    ("prototypes-empty", "prototypes", "list_prototypes", {"project_id": "project_fixture"}, []),
    ("prototypes-running", "prototypes", "run_prototype", {"prototype_id": "prototype_fixture"}, {"prototype_id": "prototype_fixture", "url": "http://127.0.0.1:17471/index.html", "pid": 12345}),
    ("prototypes-reused", "prototypes", "run_prototype", {"prototype_id": "prototype_fixture"}, {"prototype_id": "prototype_fixture", "url": "http://127.0.0.1:17471/index.html", "pid": 12345, "already_running": True}),
    ("prototypes-hosted", "prototypes", "run_prototype", {"prototype_id": "remote_fixture"}, {"prototype_id": "remote_fixture", "url": remote_prototype["url"], "pid": None, "running": False, "remote": True}),
    ("prototypes-stopped", "prototypes", "stop_prototype", {"prototype_id": "prototype_fixture"}, {"stopped": True, "prototype_id": "prototype_fixture"}),
    ("prototypes-idle", "prototypes", "stop_prototype", {"prototype_id": "prototype_fixture"}, {"stopped": False}),
    ("prototypes-deleted", "prototypes", "delete_prototype", {"prototype_id": "prototype_fixture"}, {"deleted": 1}),
    ("prototypes-missing", "prototypes", "delete_prototype", {"prototype_id": "prototype_missing"}, {"deleted": 0}),
    ("references-added", "references", "add_artifact", {"project_id": "project_fixture", "url": reference["url"], "kind": "variant", "title": reference["title"], "label": "A", "capture": False}, reference_skipped),
    ("references-detail", "references", "get_artifact", {"project_id": "project_fixture", "artifact_id": "reference_fixture"}, reference),
    ("references-list", "references", "list_artifacts", {"project_id": "project_fixture"}, [reference]),
    ("references-empty", "references", "list_artifacts", {"project_id": "project_fixture"}, []),
    ("references-failed", "references", "get_artifact", {"project_id": "project_fixture", "artifact_id": "reference_fixture"}, {**reference, "snapshot": {"ok": False, "mode": "unavailable", "headings": [], "error": "Synthetic capture failure"}}),
    ("references-deleted", "references", "delete_artifact", {"project_id": "project_fixture", "artifact_id": "reference_fixture"}, {"deleted": 1}),
    ("assets-attached", "assets", "attach_asset", {"project_id": "project_fixture", "content_base64": "S2VlcCB0aGUgb3duZXIgY2xlYXIu", "filename": asset["filename"], "title": asset["title"], "notes": asset["notes"], "source": asset["source"]}, asset),
    ("assets-detail", "assets", "get_asset", {"project_id": "project_fixture", "asset_id": "asset_fixture"}, asset_deliverable),
    ("assets-list", "assets", "list_assets", {"project_id": "project_fixture"}, [{key: value for key, value in asset.items() if key != "text_excerpt"}]),
    ("assets-empty", "assets", "list_assets", {"project_id": "project_fixture"}, []),
    ("assets-shot", "assets", "attach_prototype_shot", {"project_id": "project_fixture", "prototype_id": "prototype_fixture", "title": asset_prototype_shot["title"], "notes": asset_prototype_shot["notes"]}, asset_prototype_shot),
    ("assets-admitted", "assets", "admit_remote_screenshot", {"project_id": "project_fixture", "run_id": "run_fixture", "operation_id": "upload_fixture",
        "content_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "filename": "handover.png", "media_type": "image/png",
        "captured_at": "2026-09-09T00:00:00Z", "target_revision": "fixture_v1", "title": asset_image["title"], "dispatch_token": "synthetic_dispatch"},
        {**asset_image, "source": "remote_mcp:direct_upload", "notes": "", "idempotent_replay": False}),
    ("assets-detached", "assets", "remove_asset", {"project_id": "project_fixture", "asset_id": "asset_fixture"}, {"deleted": 1}),
    ("assets-missing", "assets", "remove_asset", {"project_id": "project_fixture", "asset_id": "asset_missing"}, {"deleted": 0}),
    ("notes-ready", "notes", "list_notes", {"project_id": "project_fixture"}, {"items": [note], "total": 1, "has_more": False}),
    ("notes-empty", "notes", "list_notes", {"project_id": "project_fixture"}, {"items": [], "total": 0, "has_more": False}),
    ("sections-ready", "sections", "get_section_members", {"section_id": "section_fixture"}, {"section": section, "members": members}),
    ("sections-empty", "sections", "list_sections", {"project_id": "project_fixture"}, []),
    ("sections-detail", "sections", "get_section", {"section_id": "section_fixture"}, section),
    ("projects-ready", "projects", "list_research_projects", {}, [project]),
    ("projects-empty", "projects", "list_research_projects", {}, []),
    ("projects-detail", "projects", "create_research_project", {key: project[key] for key in ("title", "goal", "description")}, project),
    ("search-ready", "search", "search", {"query": "handover"}, {"results": [hit]}),
    ("search-empty", "search", "search", {"query": "unmatched synthetic phrase"}, {"results": []}),
    ("search-detail", "search", "fetch", {"id": hit["id"]}, fetched),
    ("hypotheses-open", "hypotheses", "record_hypothesis", {"project_id": "project_fixture", "text": hypothesis["text"], "prediction": hypothesis["prediction"]}, {"hypothesis": hypothesis}),
    ("hypotheses-observed", "hypotheses", "get_hypothesis", {"hypothesis_id": "hyp_fixture"}, resolved),
    ("hypotheses-dropped", "hypotheses", "drop_hypothesis", {"hypothesis_id": "hyp_fixture", "note": dropped["drop_note"]}, {"hypothesis": dropped}),
    ("hypotheses-empty", "hypotheses", "list_hypotheses", {"project_id": "project_fixture"}, {"hypotheses": []}),
    ("decisions-proposed", "decisions", "record_decision", {"project_id": "project_fixture", **{key: decision[key] for key in ("title", "decision", "based_on", "rejected")}}, {"decision": decision}),
    ("decisions-adopted", "decisions", "get_decision", {"decision_id": "dec_fixture"}, adopted),
    ("decisions-superseded", "decisions", "update_decision", {"decision_id": "dec_fixture", "superseded_by": "dec_next"}, {"decision": {**decision, "status": "superseded", "superseded_by": "dec_next"}, "successor": successor}),
    ("decisions-empty", "decisions", "list_decisions", {"project_id": "project_fixture"}, {"decisions": []}),
    ("surveys-instrument", "surveys", "record_survey", {"project_id": "project_fixture", "title": survey["title"], "questions": [question]}, {"survey": survey}),
    ("surveys-ready", "surveys", "survey_results", {"survey_id": "survey_fixture"}, survey_results),
    ("surveys-comparison", "surveys", "survey_results", {"survey_id": "survey_fixture"}, survey_comparison),
    ("surveys-repeated-choice", "surveys", "survey_results", {"survey_id": "survey_fixture"}, {**survey_results, "responses": 1,
        "questions": [{"question_id": "q1", "text": question["text"], "kind": "multi", "answered": 1,
                       "counts": {"Named owner": 2, "Longer email": 0}}]}),
    ("surveys-text", "surveys", "survey_results", {"survey_id": "survey_fixture"}, survey_text),
    ("surveys-empty", "surveys", "list_surveys", {"project_id": "project_fixture"}, {"surveys": []}),
    ("surveys-imported", "surveys", "import_survey_responses", {"survey_id": "survey_fixture", "responses": [{"respondent_key": "fixture-response", "answers": [{"question_id": "q1", "value": "Named owner"}]}]}, {"survey_id": "survey_fixture", "imported": 1, "total_responses": 3}),
    ("syntheses-convergence", "syntheses", "get_synthesis", {"synthesis_id": "synthesis_fixture"}, synthesis),
    ("syntheses-report", "syntheses", "record_synthesis_section", {"project_id": "project_fixture", "section_id": "section1",
        "content": {key: report_section[key] for key in ("markdown", "citations", "figures")}}, report),
    ("syntheses-outline", "syntheses", "record_synthesis_outline", {"project_id": "project_fixture", "outline": {"title": outline["title"], "sections": outline["sections"]}}, outline),
    ("syntheses-empty", "syntheses", "list_syntheses", {}, []),
    ("sessions-completed", "sessions", "get_usability_session", {"session_id": "session_fixture"}, session_record),
    ("sessions-dropped", "sessions", "record_usability_session", {key: session_dropped[key] for key in ("persona_id", "subject", "fidelity", "date", "steps", "outcome")}, {"usability_session": session_dropped}),
    ("sessions-salience", "sessions", "get_usability_session", {"session_id": "session_fixture"}, session_salience),
    ("sessions-prototype", "sessions", "record_prototype_session", {"persona_id": "persona_fixture", "prototype_id": "prototype_fixture", "session_id": "session_fixture", "date": "2026-09-09", "reaction": prototype_reaction}, {"prototype_session": prototype_session}),
    ("sessions-funnel", "sessions", "get_session_funnel", {"subject_kind": "flow", "subject_id_or_url": "flow_fixture"}, funnel),
    ("sessions-funnel-empty", "sessions", "get_session_funnel", {"subject_kind": "flow", "subject_id_or_url": "flow_fixture"}, {**funnel, "sessions": 0, "completed": 0, "rows": []}),
    ("sessions-empty", "sessions", "list_usability_sessions", {"project_id": "project_fixture"}, {"sessions": []}),
    ("notes-created", "notes", "create_note", {"project_id": "project_fixture", "title": note["title"], "text": note["text"]}, {**note, "kind": "note"}),
    ("notes-data", "notes", "set_note_data", {"note_id": "note_fixture", "patch": {"prototype_id": "prototype_fixture"}}, {**note, "kind": "note", "data": {"prototype_id": "prototype_fixture"}}),
    ("sections-created", "sections", "create_section", {"project_id": "project_fixture", "title": section["title"], "note": section["note"], "member_ids": section["member_ids"]}, section),
    ("sections-updated", "sections", "update_section", {"section_id": "section_fixture", "patch": {"title": "Revised handover group"}}, {**section, "title": "Revised handover group"}),
    ("sections-added", "sections", "add_to_section", {"section_id": "section_fixture", "node_ids": ["note:note_third"]}, {**section, "member_ids": [*section["member_ids"], "note:note_third"]}),
    ("sections-removed", "sections", "remove_from_section", {"section_id": "section_fixture", "node_ids": ["note:note_second"]}, {**section, "member_ids": ["note:note_fixture"]}),
    ("sections-members-set", "sections", "set_section_members", {"section_id": "section_fixture", "node_ids": ["note:note_second"]}, {**section, "member_ids": ["note:note_second"]}),
    ("hypotheses-result-recorded", "hypotheses", "record_hypothesis_result", {"hypothesis_id": "hyp_fixture", **resolved["result"]}, {"hypothesis": resolved}),
    ("surveys-detail", "surveys", "get_survey", {"survey_id": "survey_fixture"}, survey),
    ("syntheses-recorded", "syntheses", "record_synthesis", {"title": synthesis["title"], "start_input": synthesis["start_input"], "payload": {key: synthesis[key] for key in ("gesamtbild", "positionierung", "findings")}}, synthesis),
    ("sessions-flow-funnel", "sessions", "flow_funnel", {"project_id": "project_fixture", "flow_id": "flow_fixture"}, {**funnel,
        "rows": [{**funnel["rows"][0], "caption": "Choose the next handover action", "personas": ["persona_fixture"]}],
        "flow": {"id": "flow_fixture", "title": "Handover flow", "steps": 1},
        "biggest_dropoff": {"step": 0, "caption": "Choose the next handover action", "dropped": 1, "reasons": funnel["rows"][0]["drop_reasons"]}}),
    ("councils-recorded", "councils", "record_council", {"project_id": "project_fixture", **{key: council_recorded[key] for key in ("prompt", "persona_ids", "statements", "prompts", "exec_summary")}}, council_recorded),
    ("councils-voices", "councils", "get_council", {"session_id": "council_fixture"}, council),
    ("councils-input", "councils", "get_council", {"session_id": "council_fixture"}, council_input),
    ("councils-list", "councils", "list_councils", {"limit": 25}, council_list),
    ("councils-empty", "councils", "list_councils", {"limit": 25}, {"items": [], "total": 0, "has_more": False, "next_cursor": None}),
]
# Check authored inputs against actual native Python signatures without building
# a server or invoking tools. These receipts must identify a possible tool call.
signatures = {}
for path in Path("sonaloop/mcp_server").glob("_tools*.py"):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool" for d in node.decorator_list):
            positional = node.args.posonlyargs + node.args.args
            names = {arg.arg for arg in positional + node.args.kwonlyargs}
            required = {arg.arg for arg in positional[:len(positional) - len(node.args.defaults)]}
            required |= {arg.arg for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults) if default is None}
            signatures[node.name] = names, required
output = []
# Checked synthetic DTOs from isolated native compatibility tests; never execute inputs.
for case in json.loads(Path("tools/persona-ui/fixtures/council-formats.json").read_text())["cases"]:
    specs.append(("councils-" + case["tool"].replace("_", "-"), "councils", case["tool"], case["input"], case["value"]))
for case in json.loads(Path("tools/persona-ui/fixtures/calendar-plans.json").read_text())["cases"]:
    family = "plans" if case["tool"] in {"put_day_plan", "get_day_plan", "put_period_plan", "get_period_plan", "list_period_plans"} else "calendar"
    specs.append((family + "-" + case["scenario"].replace("_", "-"), family, case["tool"], case["input"], case["value"]))
for family in ("cohorts", "profiles", "records", "chats", "catalog", "researchplan", "understanding"):
    for case in json.loads(Path("tools/persona-ui/fixtures/" + family + ".json").read_text()):
        specs.append((case["scenario"].replace("_", "-"), family, case["tool"], case["input"], case["value"]))
for case in json.loads(Path("tools/persona-ui/fixtures/preparation.json").read_text()):
    specs.append(("preparation-" + case["scenario"].replace("_", "-"), "preparation", case["tool"], case["input"], case["value"]))
for case in json.loads(Path("tools/persona-ui/fixtures/run-journal.json").read_text()):
    specs.append((case["scenario"], "runs", case["tool"], case["input"], case["value"]))
for case in json.loads(Path("tools/persona-ui/fixtures/project-health.json").read_text()):
    specs.append(("runs-" + case["scenario"].replace("_", "-"), "runs", case["tool"], case["input"], case["value"]))
for case in json.loads(Path("tools/persona-ui/fixtures/projects.json").read_text()):
    specs.append(("projects-" + case["scenario"].replace("_", "-"), "projects", case["tool"], case["input"], case["value"]))
for case in json.loads(Path("tools/persona-ui/fixtures/memory.json").read_text())["cases"]:
    specs.append(("memory-" + case["scenario"].replace("_", "-"), "memory", case["tool"], case["input"], case["value"]))
for scenario, family, tool, arguments, data in specs:
    names, required = signatures[tool]
    assert set(arguments) <= names and required <= set(arguments), (scenario, "Invalid native fixture arguments")
    envelope = data if tool in {"search", "fetch"} else {"tool": tool, "data": data}
    html, state = render_tool(tool, envelope)
    public_value = public_component_value(tool, data)
    public_html, public_state = render_component_props(SURFACES[tool].component_id, {"name": tool, "value": public_value})
    assert str(public_html) == str(html) and public_state == state, "Public props and native projection diverged"
    output.append(dict(scenario=scenario, family=family, tool=tool, input=arguments, native=envelope,
                       html=str(html), state=state, public_value=public_value))
shared = dict(note_content=str(note_content(note)), project_heading=str(project_heading(project, level="h2")),
    search_hit_content=str(search_hit_content(hit["title"], hit["text"])), fetched_content=str(note_content(fetched)),
    passive_reference_html=str(render_ref({"kind": "council", "id": "council_real", "anchor": "statement_3",
        "quote": "An observation with substantial context. " * 12 + "Only applies during the pilot."}, passive=True)))
declarations = [dict(tool=name, componentId=surface.component_id, resourceUri=surface.uri)
                for name, surface in sorted(SURFACES.items())]
print(json.dumps(dict(fixtures=output, declarations=declarations, shared=shared)))
`;

export async function nativeFixtureSet() {
  const python = process.env.RESEARCH_TEST_PYTHON || 'python3';
  const { stdout } = await execFile(python, ['-B', '-c', fixturePython], { cwd: repo,
    env: { PATH: process.env.PATH || '', PYTHONPATH: repo, PYTHONDONTWRITEBYTECODE: '1', LANG: 'C.UTF-8' },
    // This one qualification process collects every independent family fixture.
    // Production result, HTML and public-props budgets remain unchanged.
    maxBuffer: 16 * 1024 * 1024 });
  const { fixtures, declarations, shared } = JSON.parse(stdout);
  return { collectionBytes: Buffer.byteLength(stdout), declarations, fixtures: fixtures.map(value => ({ ...shared, ...value,
    result: { ...toolResult(value.html, { ...value, text: canonical(value.native) }), structuredContent: value.native } })) };
}

export async function nativeFixtures() {
  return (await nativeFixtureSet()).fixtures;
}

export function pngDimensions(png) {
  assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(png.subarray(12, 16).toString(), 'IHDR');
  return { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
}

export async function exportScenarios(outputParent = process.env.RESEARCH_SCENARIO_OUTPUT || resolve(tmpdir(), 'sonaloop-research-ui-scenarios')) {
  await mkdir(outputParent, { recursive: true });
  const output = await mkdtemp(resolve(outputParent, 'run-'));
  const { fixtures, declarations } = await nativeFixtureSet();
  const noteFixture = fixtures.find(item => item.scenario === 'notes-ready');
  assert.ok(noteFixture && noteFixture.tool === 'list_notes' && noteFixture.family === 'notes');
  const failed = { ...noteFixture, scenario: 'notes-error', state: 'unavailable',
    result: { isError: true, content: [{ type: 'text', text: 'Synthetic native tool failure; no operation was invoked.' }] } };
  const scenarios = [...fixtures, failed].map(fixture => ({ fixture, viewport:
    fixture.family === 'runs' || fixture.tool === 'get_study_result' ? { width: 960, height: 4096 }
      : { width: 390, height: ['memory', 'sessions', 'syntheses', 'councils', 'prototypes', 'calendar', 'projects', 'cohorts', 'profiles', 'records', 'chats', 'catalog', 'researchplan', 'understanding'].includes(fixture.family) ? 3800 : 844 } }));
  scenarios.unshift({ fixture: noteFixture, viewport: { width: 960, height: 900 } });
  const rendererBytes = await readFile(fileURLToPath(import.meta.url)), bundle = await hostBundle();
  const { stdout: commit } = await execFile('git', ['rev-parse', 'HEAD'], { cwd: repo });
  const { stdout: dirty } = await execFile('git', ['status', '--porcelain'], { cwd: repo });
  const browser = await launchBrowser();
  const rendererBuild = { harnessSha256: sha(rendererBytes), bridgeBundleSha256: sha(bundle),
    executableSha256: sha(await readFile(browserExecutable)), browserVersion: browser.version() };
  const receipts = [];
  // Only this new private run is shared; earlier evidence is never rewritten.
  // First writes finish before their path becomes a hardlink source.
  const immutableFiles = new Map();
  async function immutableFile(path, bytes) {
    const digest = sha(bytes), existing = immutableFiles.get(digest);
    if (existing) await link(existing, path);
    else { await writeFile(path, bytes); immutableFiles.set(digest, path); }
  }
  try {
    for (const { fixture, viewport } of scenarios) {
      const asset = await loadAsset(fixture.family, { verifySources: true });
      const session = await openApp(browser, { family: fixture.family, viewport });
      try {
        assert.equal(session.asset.manifest.build_id, asset.manifest.build_id, 'Resource remained stable during capture');
        await session.send(fixture.result, fixture.input);
        if (fixture.state === 'unavailable') await session.root.getByText('This view is unavailable.', { exact: false }).waitFor();
        else await session.rendered();
        await session.assertPassive();
        const disclosureCount = await session.root.locator('details.sl-research-disclosure').count();
        assert.ok(disclosureCount <= 4096, 'Bounded default-disclosure capture declaration');
        assert.equal(await session.root.locator('details[open]').count(), 0, 'Capture records default closed disclosures');
        assert.ok(await session.frame.locator('html').evaluate(node => node.scrollWidth <= innerWidth), 'No horizontal overflow');
        await session.frame.locator('body').evaluate(async () => { await document.fonts.ready; await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); });
        const box = await session.root.boundingBox();
        assert.ok(box && box.width > 0 && box.height > 0);
        const crop = { x: Math.floor(box.x), y: Math.floor(box.y), width: Math.ceil(box.x + box.width) - Math.floor(box.x), height: Math.ceil(box.y + box.height) - Math.floor(box.y) };
        assert.ok(crop.x + crop.width <= viewport.width && crop.y + crop.height <= viewport.height, 'Full component fits the captured viewport');
        const png = await session.page.screenshot({ type: 'png', clip: crop, animations: 'disabled' });
        const dimensions = pngDimensions(png);
        assert.equal(dimensions.width, crop.width);
        assert.equal(dimensions.height, crop.height);
        assert.ok(png.length <= 2 * 1024 * 1024 && dimensions.width * dimensions.height <= 4 * 1024 * 1024);
        assert.ok(dimensions.width <= 4096 && dimensions.height <= 4096);
        const name = `${fixture.scenario}-${viewport.width}`, directory = resolve(output, name);
        await mkdir(directory);
        const input = canonical(fixture.input), result = canonical(fixture.result);
        const receipt = { schemaVersion: 'sonaloop.customer-ui-scenario-render.v1',
          componentId: asset.manifest.component_id, buildId: asset.manifest.build_id,
          manifestSha256: sha(asset.manifestBytes), resourceUri: asset.manifest.resource.uri,
          resourceSha256: sha(asset.resource), source: { commit: commit.trim(), dirty: Boolean(dirty),
            sourcesSha256: sha(canonical(asset.manifest.sources)), files: asset.manifest.sources },
          scenario: fixture.scenario, state: fixture.state, mode: 'tool_result', dataKind: 'synthetic_fixture',
          tool: fixture.tool, inputSha256: sha(input), resultSha256: sha(result),
          renderer: { name: 'Playwright Chromium MCP Apps fixture', version: browser.version(), buildSha256: sha(canonical(rendererBuild)) },
          rendererBuild, capturedAt: new Date().toISOString(), viewport: { ...viewport, deviceScaleFactor: 1 }, crop,
          image: { mediaType: 'image/png', sha256: sha(png), bytes: png.length, ...dimensions },
          files: { image: 'view.png', manifest: 'manifest.json', resource: 'resource.html', input: 'input.json', result: 'result.json', renderer: 'renderer.mjs', bridge: 'host.bundle.js' },
          checks: { protocol: 'MCP Apps AppBridge', passive: true, nativeToolCalls: 0, providerCalls: 0,
            ...(disclosureCount ? { disclosures: { count: disclosureCount, open: 0, content: 'retained_in_dom' } } : {}),
            runtimeVerification: 'not_asserted', humanAcceptance: 'not_asserted' } };
        await Promise.all([
          immutableFile(resolve(directory, 'view.png'), png), immutableFile(resolve(directory, 'manifest.json'), asset.manifestBytes),
          immutableFile(resolve(directory, 'resource.html'), asset.resource), immutableFile(resolve(directory, 'input.json'), input),
          immutableFile(resolve(directory, 'result.json'), result), immutableFile(resolve(directory, 'renderer.mjs'), rendererBytes),
          immutableFile(resolve(directory, 'host.bundle.js'), bundle), writeFile(resolve(directory, 'receipt.json'), `${canonical(receipt)}\n`),
        ]);
        receipts.push({ directory, receiptSha256: sha(`${canonical(receipt)}\n`), ...receipt });
      } finally { await session.page.close(); }
    }
    const declaredTools = { source: 'sonaloop/ui_components/registry.py:SURFACES',
      count: declarations.length, declarations };
    await writeFile(resolve(output, 'index.json'), `${canonical({ dataKind: 'synthetic_fixture', declaredTools, scenarios: receipts })}\n`);
    return { output, declaredTools, scenarios: receipts.map(({ directory, image, state, tool }) => ({ directory, image, state, tool })) };
  } finally { await browser.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const report = await exportScenarios(process.argv[2]);
  const stdout = `${JSON.stringify(report, null, 2)}\n`;
  await writeFile(resolve(report.output, 'stdout.json'), stdout);
  process.stdout.write(stdout);
}
