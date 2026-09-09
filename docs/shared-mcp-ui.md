# Shared Research components and MCP coverage

Research owns its component source, native operations and MCP App resources.
Product pages and MCP Apps reuse the same customer rendering implementation;
the host provides transport, resource isolation and explicit action grants.
Tool names, component declarations and rendered output never grant permission
to call a native operation.

## Existing rendering seams

The Persona profile uses the shared browser module and separate product/MCP
adapters described in [the Persona surface contract](persona-surface-contract.md).
Its native identity, versions, actions and passive input preview retain their
own contracts.

Other product views are Python HTML renderers. `sonaloop/artifacts.py` supplies
shared Statement, Finding, Prompt, Ref and Stance primitives. `sonaloop/web/ui.py`,
`_render.py`, `_report.py` and the page modules compose the existing product
presentation. Extracting a family means separating escaped presentation from
Store access, native validation, source resolution and transport, then reusing
that renderer in the product and the customer MCP resource. Rendering must not
perform hidden Store/provider reads, writes or automatic retries.

Families reflect existing Research concepts. Ideas and concepts are Notes;
interview-style discovery uses Council statements; segments occur in Persona
metadata, Findings and aggregate results. Screenshot flows feed Session replays,
while a Journey prototype has its own browser runtime. These relationships do
not imply a new native entity or one component per tool.

## Per-tool coverage ledger

`sonaloop/ui_components/coverage.json` uses `sonaloop.mcp-ui-coverage.v1` and records
every core tool registered by `build_server`. Optional external entry-point
extensions have separate source ownership and are outside this ledger's scope.
Each row contains the exact tool name, a semantic family, a treatment, an explicit
reason, a status and native source anchors. The top-level `native_source` names
the audited repository and immutable baseline commit.

| Treatment | Meaning |
| --- | --- |
| `surface` | Present the actual native result through a shared semantic family. |
| `action_confirmation` | Present the actual impact/confirmation and terminal result of an action. |
| `export` | Present the native export outcome and authorized delivery reference. |
| `context_only` | Authoring/context input belongs to the agent workflow; the later authored result carries the research view. |
| `reference_only` | Vocabulary, schema or protocol reference belongs in relevant controls/help. |
| `admin_only` | Configuration, external automation or example administration carries its own action/settings outcome. |
| `protocol_only` | Dispatch, checkpoint or admission state belongs to the existing execution protocol. |
| `execution_only` | Live actuation/snapshot control remains execution state; recorded Session evidence supplies the research result. |

`planned` declares intended presentation. `existing` identifies an established
binding; `supported` declares implemented coverage. Neither status alone proves
successful rendering or human acceptance. `not_applicable` requires one of the
five explicit exemption treatments and a nonblank reason. It means no standalone
research component is appropriate for that tool; the ordinary tool output remains
available. Applicable treatments cannot use `not_applicable`, and exemption
treatments cannot claim an implemented result surface.

Native anchors include `module`, `symbol`, `line`, `calls`, `annotation` and
`operation_id`. `calls` records direct syntactic `services.*` and `_service().*`
invocations, not a transitive service graph or proof of HTTP use. The annotation
is the native registry's R/W/D classification. Parameter presence records only
whether the function accepts `operation_id`; it does not establish retry safety,
version checks or permission. Every writer retains its own native contract.

## Static gate and runtime evidence

`coverage_data()` loads a fresh ledger. `coverage_errors()` parses Python source
with AST, follows the core registration functions called by `build_server`, and
checks exact tool membership, duplicates, treatment/status consistency, reasons
and native anchors against the annotation registry. It imports no tool modules,
builds no server and calls no services. Unsupported dynamic registration shapes
produce a diagnostic rather than a partial coverage pass. Source refactors must
update their recorded anchors. The gate does not compare Git HEAD or attest the
current checkout as the declared immutable baseline.

Both functions accept `source_root`; `coverage_errors` also accepts a supplied
ledger for isolated source/contract tests. Run the repository gate with:

```sh
python -m pytest -q tests/test_mcp_ui_coverage.py
```

A passing coverage gate proves inventory consistency. Each implemented binding
also needs actual resource registration, native output/schema compatibility,
meaningful family scenarios, empty/error/untrusted-input checks, and packaged
browser rendering evidence. Native results remain authoritative; private UI
metadata stays outside model context. Resource hashes, render receipts and
accepted human review remain separate from the ledger's classifications.

## Passive shared views

Native Persona profiles use a separate passive **Profiles and history** family.
The existing Product fallback hero, goals/tools sections, relationship text and
listing row are shared pure bodies. Product adapters keep avatar resolution and
edit controls. The five interactive Persona surface tools remain unchanged;
older native profiles are never relabelled as surface DTOs. Explicit Product
links open the native profile/history and supplied SOUL document. Those existing
native getters may repair SOUL/runtime fields, as before; the renderer performs
no reads or repairs. Returned calendar/experience/daily/pain/reflection records
stay in closed local disclosures. Avatar paths and metadata are unloaded
references, not proof that image pixels were rendered.

**Cohort diagnostics** shares the existing Product cohort-integrity body and
adds explicit stored-report, selection-history and coverage inspection. A
historical preflight keeps its recorded verdict; only the existing Product
adapter checks current freshness. Structural diversity, aggregate memory counts,
coverage, recorded critic and selection/checkpoint flags remain distinct.
The global report page reads persisted assessments rather than invoking the
diversity writer. An empty project cohort never calls the native all-Persona
depth query. Full provenance and overlap details remain supplied data, not new
grounding or evidence. Unknown/invalid records preserve a truthful fallback.

**Persona records and sources** displays stored identity revisions, voice checks
and attached sources through the same Product record inspector. Revisions show
their authored changes and references without recomputing current identity.
Voice checks retain their recorded verdict and zero-valued scores; the candidate
text is not returned, and a suggested rewrite is not that original text. Evidence
paths, URLs and supplied prose remain literal; rendering never loads or verifies
them. The Product checks active-workspace Persona ownership before reading the
three histories. No new persistence or execution authority is introduced.

**Persona catalog and import provenance** shares the existing Product title/role
row and original Catalog-origin badge/tooltip. The Product still prepares its
avatar, local status and CSRF action controls; passive cards receive only the
native result. Search keeps native totals, pagination, facet counts and explicit
ignored-filter notes. Recommendations show actual reported scores, selection
reasons, facet coverage and warnings; they do not establish research coverage.
When the optional local catalog package is unavailable, its native explanation
remains visible. The two explicit Product links read status or recommendations;
opening these pages never imports a Persona.

Import outcomes retain actual landed identities/provenance, reported processing
counts and skipped local/premium profiles. A repeated import is not described as
net growth. The same provenance body uses `p.provenance.catalog` in the Product
and `catalog_pull.landed[].provenance` in the result, without reconstructing an
original invocation from later state. The existing import POST and redirect are
unchanged. Catalog/source/avatar metadata is literal; passive rendering does not
fetch profile files, portraits, credentials or remote resources. Product native
reads retain their existing catalog access rules. The optional real algorithm
qualification supplies synthetic profiles through a private test transport and
pins that external source separately; it is not a live catalog or provider run.

**Research plans and recorded tasks** share the Product Plan header and task
bodies. `get_plan` displays the supplied ordered tasks and recorded history;
`add_task`, `record_frame` and `link_evidence` display their actual returned task.
Judgment, progress and parked/unparked evidence results retain their real
verdict, rationale, references, timestamps and counts. Free bucket/status text,
zero counts, false verdicts and negative minimum-input requirements are not
normalized. Plan task completion does not declare the research Run finished.
No gate evaluation, evidence lookup or dispatch occurs while rendering.

These native Plan outputs map explicitly to the closed authored
`sonaloop.research-plan-view.v1` public DTO. Dynamic evidence-kind counts become
ordered `{kind,count}` rows; native output stays untouched. Native dispatch
operation aliases and receipt keys are omitted execution context, not alleged
authorization bearers. Public examples enter the renderer directly and never
reconstruct a native result. A linked judgment and a subsequently checkpointed
result remain different states; a replay label is shown only when actually
returned. The Product prepares its existing evidence links, marks and framework
outside the pure body. Native-valid older extension fields keep the Product's
base header/tasks and a details-unavailable notice; unsupported public details
fail closed instead of changing the business validator.

`iterate_task` uses the same stored iteration-record body as the Product Plan
history and adds only the actual `cloned` tasks returned by that invocation.
Rounds, rewired dependencies, cleared frames and preserved requirements stay
visible. Calling the existing writer again can create another round: its result
is not labelled a deduplicated retry. The native registered-form descriptions
and both supported declaration spellings are retained in local details.
`set_project_methodology` reuses the Project header with its returned methodology
and integrity requirements. Its Project result supplies neither the reseeded
tasks nor a Run completion verdict; rendering does not reseed or read a Plan.

**Recorded Product Understanding** uses the actual Product capability grouping
and observation body. Its closed `sonaloop.product-understanding-view.v1`
presentation maps scalar target, inventory and verification attributes to
explicit named rows. Complete native reference fields, supersession, revision
rationale, zero attempts and false flags remain visible or in local details.
The native outputs, validation and persistence are unchanged. Only known
operation/correlation aliases are omitted from public presentation; this is
not a generic recursive key filter or a claim that those aliases are bearers.

The manifest recorder retains the exact stimulus binding, coverage checklist
and bounded observation scope. `served_to_host` does not mean an image was
inspected or a capability verified. Rendering fetches no target URL, asset or
evidence. Native getter history contains identity and revision fields, so it
does not receive the richer Product history's capability/conflict counts.
The Product prepares full stored history summaries, scoped links and local
timestamps outside the pure body. Unsupported compound extension fields retain
the Product's original capability display and an explicit details-unavailable
notice; they are not silently flattened into a purported valid public DTO.

**Run journals and outcomes** reuse a read-only, project-owned Product inspector.
`start_run` and `run_journal` retain supplied steps, references, dispatch lifecycle,
critic verdicts, timestamps and replay markers. `resume_project_run` is a
continuation receipt, not a complete Health assessment; `finish_run` reports its
actual status, step count and repeated-receipt flag, without inventing a project
or a full journal. The Project result details link to its actual known Run.
Opening the inspector reads once and checks active-workspace Project and Run
ownership before rendering; it does not advance or finish the Run.

For these four tools, `public_component_value` explicitly projects native results
into the closed authored `sonaloop.run-view.v1` presentation model. Public
`{name,value}` examples enter `render_view` directly, with a matching view tag;
no native result is reconstructed or guessed. Every nested record is validated.
Native scope/correlation tokens and operation aliases are omitted execution
context, not alleged authorization bearers. The unchanged native MCP transport
retains its original fields. Dispatch arguments, next calls and host trace
queries are not display props; references remain literal and are not resolved.
Local disclosures retain the supplied public diagnostics without tool calls.

**Persona conversations and continuity proposals** shares stored chat, exchange,
summary and proposal bodies with read-only Persona-scoped Product inspectors.
`chat_with_persona` prepares a new reply and can open an empty chat; its supplied
message is not a saved exchange. `record_chat_turn` returns the actual saved count
and timestamp, not the authored text. Only `get_chat` supplies complete stored
turns. List pages retain their native offset and continuation state; the summary
is the last user message, not an invented Persona reply. Full authoring context
remains in a closed disclosure, with no recomputation or new model call.

Continuity proposals preserve their actual pending/approved/rejected state,
review reason, selected turn indices and supplied references. They do not modify
identity, facts or lived memory. The native record operation can replace a prior
reviewed proposal with a new pending record; this UI does not claim immutable
reviews or change that service contract. Supplied reference indices can remain
unresolved, and rendering does not verify their targets. Product inspectors first
check the active Persona, then chat and proposal ownership; they expose no create,
reply or review mutation. This persisted Research conversation is separate from
the optional agent host's process-local conversational session.

Notes, Sections, Projects, Search, Hypotheses, Decisions, Councils, Surveys,
Syntheses/Reports, Sessions, Files, Prototypes, Plans, Calendars, Memory and captured URL References
have passive MCP resources registered on
existing native tools. `registry.py` names each exact tool/result projection;
only those names receive `supported` rows. The Note and Section detail pages,
Project heading and server-rendered command-palette hit content call the same
functions as these resources. Product navigation and native editing stay in their
existing adapters. This is shared semantic content, not a copy of the complete
product shell inside chat.

Hypothesis views use the product's prediction/observation body and display the
recorded status; they never recalculate a verdict. A dropped hypothesis includes
its native retirement note in both product and App. Decision views reuse the
decision body, evidence references, rejected alternatives and supersession links.
The product adapter resolves references before rendering. Passive Apps show only
references supplied in the result; they do not resolve missing records or titles.
Their reference mode keeps full supplied text and `kind:id#anchor` visible because
the passive surface does not have the product's tooltip or deep-link affordance.
Long decision text stays fully visible because the passive App has no expand action.
When a native supersession result supplies both predecessor and successor, both
records are shown. Writer results are projected from their actual nested
`hypothesis` or `decision` object; read and list envelopes retain their native shapes.

Council detail views share the product's authored summary and statement grouping.
Product adapters prepare resolved persona/avatar/reference fragments before the
pure statement renderer; the passive App uses only supplied participant IDs,
statement text, input snapshots, stance labels and source addresses. Each
statement keeps its own trust/context information even when grouped with other
statements by the same persona. List summaries show the native participant,
voice and vote counts without inventing a transcript. Full records must contain
native `statements`; legacy or unknown shapes retain ordinary tool output.
Head-to-head, price-ladder and red-team results reuse the complete product format
bodies: supplied preferences, abstentions, variant metadata, price responses and
recorded aggregate counts, objections, endorsements and roles. The renderer never
recomputes a preference, acceptable price range or acceptance drop. Missing answers
remain unanswered; repeated price responses retain their native count. A theme may
contain more entries than resolved persona voices, so both native quantities remain
visible. Writer results retain their full Council voices and claim-posture notices;
flattened getters do not invent a transcript. Offset-based Council queries keep their
integer statement/vote/question counts separate from cursor-based list summaries.
An unrenderable optional/legacy format keeps the product detail and transcript
readable with a local format notice; the MCP wrapper retains its unchanged native
output without a card. Native free-text direction values such as `both` remain literal labels in passive
findings; they do not become a normalized numeric stance.

Survey instruments share the product question body and distinguish an unknown
response count from an actual zero. Result views show native per-option counts
and the canonical prediction-versus-real-answer table, including its source
references. Every supplied free-text answer remains visible; when the native
result retains fewer answers than the answered count, the view shows both
numbers. A native multi-choice import can contain repeated selections; if a
recorded option count exceeds the answered count, both numbers remain visible
with a notice and no proportion bar. Import receipts say how many responses were **processed**, because a
replayed import need not add that many new rows. Exported survey forms and
evidence attachment keep their existing native workflows; these passive cards
do not submit responses, export forms or attach evidence.

Synthesis and Report views share the product's report cover, narrative sections,
findings, statements and citations after the product adapter has resolved its
own context. Passive views retain the native `scope` and `status`; an outline
stays explicitly unfinished. Figures without supplied pixels remain labeled
references, and missing figure slots never shift a later `![[fig:N]]` reference.
The renderer neither loads a cited study nor recreates Council aggregates from
unavailable records. Full report and convergence records retain their own prose
and explicit source addresses; unknown legacy shapes fall back to native text.

Session views share the product's step, outcome, prediction and funnel bodies.
They show the supplied screen description, action, persona monologue, friction,
continue/drop decision and stored outcome. Screenshot paths stay literal
references: no filesystem or browser media is read. Supplied focus rectangles
remain stated salience hypotheses, never measured gaze. Recorded prototype
versions and state references are shown without looking up a current prototype.
Native verification is displayed only when the result actually supplies it.
Funnel views preserve native entered/continued/dropped counts, drop reasons and
completed totals; they do not run another session or recompute its verdict.
All existing recording, memory, authorization and idempotency rules stay in the
original native tool; displaying the result adds no new operation.

File views reuse the product's file identity, full supplied excerpt and provenance
body. They retain native filenames, media types, size, source, timestamps and
supersession references. Image metadata does not become an image fetch: these cards
say when no pixels were supplied. `view_asset` image results are not yet registered
by this passive metadata family. Confirmed detach results show the native count,
including zero, and state that content-addressed file bytes are retained.

Prototype views reuse the product detail body and prepared property projection.
The product prepares its sandboxed preview, replay/session rows and navigation
before rendering; the same body also shows the recorded prototype notes. Native
MCP artifact responses supply metadata and locations, so their passive card does
not fetch or execute a preview. Local running state is shown only when supplied.
A remote `run_prototype` result exposes its hosted address with `pid: null` and
`running: false`; it does not establish a local process or website availability.
Local start/reuse receipts retain the reported process ID. Stop and delete cards
show the native outcome, including a missing process or zero removed records;
prototype files remain retained after deletion. These display-only views do not
change native runner authorization or retry behavior.

Recorded plans, current state, calendar periods and activity details reuse the
Persona inspector's extracted bodies. The product includes the selected day's
and period's stored plans. Plans describe intentions, not completed work. Current
state preserves its supplied timestamp and synthetic-data notice. A calendar
block without an activity stays planned; activity prose, conversation, zero-valued
measurements, quotes and source references remain literal supplied data. Passive
week/month agendas retain every supplied row; a year uses a readable supplied
agenda instead of implying a complete distribution from a capped heatmap. Native
period totals and truncation notices remain visible. Product navigation, avatar
resolution and clock-dependent today decorations are prepared outside the pure
renderer. Invalid legacy optional shapes preserve a truthful product fallback.

Project creation, offset queries, lineage, archive, deletion and icon results use
the same Product header, lineage notice and stored icon specification bodies.
Creation preserves warnings, operation identity and replay without claiming a run
started. Archive preserves evidence; deletion shows actual table counts, including
zero. A supersession keeps the recorded predecessor/successor direction. An icon
specification never executes supplied SVG or loads its file/URL. Native icon
generation is deterministic, not a newly introduced model call.

The graph view uses the Product outline's five shared semantic row cells. The
Product retains its own grouping, filters, media, dates and controls. The passive
inventory keeps every supplied native node and edge, including unknown phases,
literal voices counts, resolved Persona stub IDs, references and graph counts. It
does not fetch the Product's additional session or decision records and does not
turn supplied graph metadata into image pixels or execution authority.

The Project inspector links to **Native study result** at `/jobs/{project_id}/results`.
Only that explicit navigation requests the native automation result; ordinary
project navigation and the cheap global run widget do not add another deep result
query. This Product page and MCP compose the existing Project, lean Council,
Synthesis, Health and prediction bodies. Missing nullable projections remain
unavailable and are not retried by the renderer. Graph counts are not completion
or displayed-row counts. A legacy native result that omits a bare-ID synthesis
remains incomplete; the view does not silently fetch another record.

**Project Health and Run Diagnostics** is a separate Component because its native
v2 diagnostic shape is extensive. The existing Product support disclosure and
attention sentence are shared; Product copy buttons and target links are prepared
outside the body. Passive health preserves journal/lifecycle/preflight/evidence
and recovery values, empty suggested arguments and required input paths.
Preflight blockers, target identity/evidence restrictions, nested action metadata
and the full supplied Product target remain visible as escaped native data. It grants
no tool execution. Ready-to-display never means the engine finished, and unknown
external host connectivity is not rewritten as a disconnected host. Its synthetic
finished-state fixture is a prepared journal-boundary test, not evidence that a
real research run passed finish gates. Project, graph and health cards keep meaningful titles, status and results visible.
Native details disclosures initially close record IDs, inventory grids and
diagnostics. Enter and Space toggle them locally, without MCP or network calls.
All technical fields remain in the DOM and unchanged native result; execution
grants are redacted from passive presentation only. Existing Product copy actions
keep their native arguments. The fixture raster records its default closed state
in `checks.disclosures`; it does not claim that hidden detail text is visible in
the PNG. Mobile tests also open and close the same native disclosure.

Prediction aggregates show recorded estimates rather than observed behavior.
Counts count prediction records, not unique people; supplied likelihood means are
not recalculated, and null is distinct from zero. Native references may be capped
at five per group. Both the native prediction tool and the Product result page
use the same body and preserve its source addresses without loading the sources.

Persona preparation views reuse the existing Product readiness and capability
bodies. The Persona page links to **Persona preparation**: its read-only history
and detail pages load existing snapshots/builds, never prepare a context, start a
build or execute a returned stage. Immutable contexts keep their supplied task,
cutoff, references and full agent context in local disclosures. A ready score is
structural readiness, not observed behavior; native false capability and null
critic fields remain distinct. Durable build journals show literal status/cursor
and the returned stage purpose; dispatch parameters/grants are excluded from
presentation while native MCP output stays unchanged. The same journal body also
presents `persona_build_step`, whose returned persisted progress is meaningful
UI even though it is a writer. Its prior no-UI classification was re-evaluated;
rendering the response does not run another step. Seeded ready/completed fixtures
are synthetic native records, not proof that preceding authoring gates ran.

Memory views share the Persona inspector's entity, fact, thread, recall and
document bodies. Its collapsed whole-record overview uses the same digest and
experience-summary content, independently of the search and historical-state
panels above it. `get_project` retains the native current status and current fact
validity; an `as_of` filter does not turn those fields into a historical snapshot.
`get_state_at` displays the supplied historical state. Threads included as open
at that date may retain a later closure in their stored fields. Timeline cards
keep the native cap notice, total quantities and every supplied row. Lean event
rows do not acquire invented IDs. Recall scores remain ranking measurements,
with native excerpt and embedding-mismatch notices; they are not probabilities.
The product's compact twenty-thread section stays compact; passive tool results
retain every supplied thread. Resolved entities can be viewed directly, while a
native null resolution remains empty.

Digest text, themes, arcs, trends and period identity remain authored records.
Experience summaries preserve native event/day totals and the native selection
of up to twenty completed entries and the latest ten open-loop entries. Pain
observations reuse the existing Finding body, retain their recorded frequency
and severity, and explicitly identify absent event evidence. `extract_pain_points`
persists those observations, so its MCP annotation is write-bearing (`W`), not a
read-only declaration. The product overview does not invoke it. Day, month and
memory-delta outcomes display exactly the reported processing counts, including
zero; retries can replace existing records, so those counts do not claim net
growth. Rendering never repeats a writer. The native day recorder keeps its
guarded Persona type through persistence and converts only the final public
return. Timeline entity filters verify that the entity belongs to the requested
Persona before reading facts. MEMORY.md cards render the supplied text; export
cards show the actual destination and byte count without loading the file.

Captured URL References reuse the product snapshot body. The passive view keeps
all supplied headings and text; the product retains its compact clamped layout.
A skipped capture stays distinct from a failed capture or a successful snapshot.
A successful empty page is labeled as captured without text in both product and App.
URLs remain literal text, and no view recaptures or navigates to them. A confirmed
reference deletion displays only the native deletion count.

The MCP adapter calls each original native function once. FastMCP's original
input/output metadata remains in place, including the bare `search` and `fetch`
connector contracts. Text and structured output are preserved byte-for-byte
through the SDK conversion. Additive `CallToolResult._meta["sonaloop/presentation"]`
contains the rendered semantic fragment, its component/state and the SHA-256 of
all native text blocks joined by one newline. This metadata is private to a host
and App; hosts must keep it out of model context. A malformed or oversized
projection preserves the successful native output without a card or retry.

The App verifies component, schema, state, size and native-text digest.
Only explicitly marked customer disclosure details and their direct summaries
remain locally interactive. The sanitizer discards supplied open/group/handler
attributes, so every new result starts closed; other action controls stay removed. It then
copies a narrow semantic element/class allowlist into a new document fragment;
it strips scripts, event handlers, styles, images, forms and navigation.
Count bars use an HTML `meter` with a strictly validated 0–1 value and accessible
label. No arbitrary style, SVG or resource URL is admitted to represent a count. The
passive resources make no network request, invoke no tool, and declare no actions.
The original tool text remains available when a host cannot render MCP Apps.
Static CSS and translation assets are customer package inputs; renderers resolve
no additional research records, media or providers. Large results retain their
native output when the 192 KiB presentation budget is exceeded.
The App shows a localized loading state until a result arrives. Optional host
logging failures do not replace a successful view. Product CSS is registered at
bootstrap so opening the first shared card cannot change the release shell token.

Build with `node tools/persona-ui/build-research.mjs` using the pinned
`tools/persona-ui` dependencies. Each generated manifest binds Python/product
sources, App source, CSS, translations and the exact self-contained HTML resource.
A pure SSR product view has a stylesheet and no browser script; its declaration
has `actions: []`. Manifests remain declarations, not authority or execution proof.
Run `tests/test_research_ui.py` for native/schema/product compatibility and
`tests/test_mcp_ui_coverage.py` for inventory consistency. Browser fixture receipts
identify their synthetic data explicitly and cannot establish customer runtime
execution or human acceptance.

## Public Component examples

`sonaloop/ui_components/declarations/*.json` contains customer-owned
`sonaloop.customer-component.v1` declarations. For the passive SSR families, the
public entry point is `component_props.render_component_props(component_id,
props)`. `props.name` selects an existing pure family projection;
`props.value` supplies its authored view-model DTO. The helper calls the same
`Surface.render` used after native MCP envelope validation. It never calls the
named MCP tool, opens a Store or adds action permission.

Persona uses its existing shared browser view instead of the Python renderer.
`persona-view/persona-public-props.js` exposes
`createPersonaFromProps(root, {value, locale})` and `validatePersonaProps(props)`.
The example is a complete authored `sonaloop.persona-surface.v1` value with read-only
capabilities and a missing portrait; the existing `validateSurface` contract still
validates the DTO. The wrapper accepts no action, transport or media callback.
Changing example fields updates only the local view. It creates no Persona and
grants no native editing or image-generation permission. A missing portrait in an
otherwise valid Persona remains a ready card, not an empty Persona record.

The Persona descriptor binds that JSON entry point and its synthetic fixture in
the Persona build manifest. Its public scenario is
`persona-component-readonly-placeholder`. Browser checks compare the actual
shared-view DOM with the same props passed through the unchanged packaged MCP
App and a simulated `get_persona_surface` response. The App's automatic refresh is
answered by that fixture; no native tool or image provider is invoked. Export with
`node tools/persona-ui/test/persona-scenario-browser.mjs --public-component <output>`
after `node tools/persona-ui/build.mjs`. These are new fixture renders, not renamed
screenshots from an earlier release. Focus, loading and error still require their
own declared scenario evidence; the readonly example covers success and disabled
editing. This JSON example does not attest the live adapter's mutation workflow.

An explicit public DTO mapping handles a reserved JavaScript property name:
`register_remote_prototype` uses `{artifact, note?}` as its public `value`, while
the unchanged native result uses `{prototype, note?, dispatch?}`.
`public_component_value()` prepares that authored example and the pure entry
point maps `artifact` back for the existing renderer. Dispatch data is not a visual
prop. The reserved-key ban remains intact. The fixture harness independently
compares the public DTO's rendered HTML with the original native projection;
native MCP text, structured content and input/result raster hashes are unchanged.

The cohort selection and recorded-preflight public DTOs omit exactly
`dispatch.dispatch_token`. No recursive field deletion or other domain-data
transformation occurs. The pure renderer does not read that authority field;
tests compare identical rendered HTML before and after this mapping and verify
that native MCP outputs remain unchanged. Authored repository render fixtures
use an inert placeholder for transient synthetic dispatch tokens; original
isolated native-test output stays in private qualification evidence. Public
Component declarations contain the mapped view model without that grant field.

The checked examples are synthetic public content. They contain no private
presentation HTML, native envelope, credentials, execution grants or runtime
record copy. Their bounded JSON Schemas describe supported authored example
shapes, rather than replacing the native business input/output schemas. Deep
compound fields retain type-only checks within the public schema depth budget;
the existing projection checks its required fields when rendering. Editing
a public string prop changes the shared renderer's content; invalid props do not
become a native operation. Each scenario ID and state matches the customer raster
exporter's actual fixture. These associations are declared by the customer;
external registries must keep them separate from independently attested pixels.

The passive SSR axis values are `default`, `responsive` and `light`; the public
Persona example declares its actual `readonly` variant. Responsive
means the same CSS adapts to the host width; no unimplemented size prop is implied.
Ready and empty examples are supplied. Loading/error are applicable App transport
states with missing public-DTO scenario coverage; they are not invented renderer
props. Focus and disabled states do not apply to passive cards without controls.
Keyboard and screen-reader review remain explicitly `not_reviewed`.

Regenerate with `node tools/persona-ui/build-component-declarations.mjs`, then
`node tools/persona-ui/build-research.mjs`; the build binds declarations, generator,
public entry point and synthetic fixture source. The exporter checks every public
example against its corresponding pure native-result projection. Third-party
registration supplies its own workspace/source/revision/render identifiers;
those identities never enter these customer declarations.

## Component source ownership

`tools/persona-ui/research-source-inputs.mjs` explicitly lists shared presentation
and integration inputs plus each family's renderer/product adapters and its own
public declaration. Each build remains below the existing 64-file source limit;
a missing, unknown or over-budget source set fails before resource files are
written. Adding a family requires an explicit ownership entry and review of its
real shared helper calls, not a directory-wide inclusion of unrelated renderers.

Shared files deliberately affect all consumers. For example, Session funnels use
Survey `count_row`, while product Session and Council charts use helpers from
`web/_synthesis.py`. Shared statements live in `ui_components/statements.py`;
that does not make the complete Council renderer an input of every statement
consumer. Synthesis product figures additionally bind `charts_catalogue.py` and
`_charts.py`, and its grouping binds `suggestions/finding_kinds.json`. Notes and Sections retain the product Library adapter; Search binds
both the server route and command-palette adapter.

These are selected presentation and integration source hashes. They do not claim
a complete transitive Python installation or environment attestation. The exact
customer release pins the whole repository, the dependency lockfile and bundled
resource digest bind browser dependencies, and execution/raster receipts retain
their separate runtime and synthetic-data boundaries. Mutation tests show which
shared and family-owned source changes alter each Component identity without
modifying actual source files during testing.

A family with more than eight projection names uses nested, disjoint `oneOf`
groups. Every union level retains the existing eight-branch bound and each tool
name retains its own required view-model fields. This does not merge unlike
writer/getter shapes or loosen native validation. The static Council format
examples come from isolated temporary-Store compatibility tests, with fixture ID
aliases and transient execution/navigation fields removed. Rendering these
examples never invokes their recorded tool inputs.

The customer scenario exporter shares byte-identical source/bridge/resource files
within each new private run using filesystem hardlinks after the first write
finishes. Every path keeps its own receipt hash and is independently verified.
It does not edit earlier runs or share writable runtime state; receipts remain
independent files. This reduces duplicate artifact storage without reducing
scenario coverage or changing raster bytes.
