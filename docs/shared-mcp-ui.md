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

Notes, Sections, Projects, Search, Hypotheses, Decisions, Councils, Surveys,
Syntheses/Reports, Sessions, Files and captured URL References
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

The App verifies component, schema, state, size and native-text digest. It then
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

One explicit public DTO mapping handles a reserved JavaScript property name:
`register_remote_prototype` uses `{artifact, note?}` as its public `value`, while
the unchanged native result uses `{prototype, note?, dispatch?}`.
`public_component_value()` prepares that authored example and the pure entry
point maps `artifact` back for the existing renderer. Dispatch data is not a visual
prop. The reserved-key ban remains intact. The fixture harness independently
compares the public DTO's rendered HTML with the original native projection;
native MCP text, structured content and input/result raster hashes are unchanged.

The checked examples are synthetic public content. They contain no private
presentation HTML, native envelope, credentials, dispatch metadata or runtime
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
