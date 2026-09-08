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

Notes, Sections, Projects, Search, Hypotheses, Decisions, Councils and Surveys
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
Embedded head-to-head/red-team verdicts display their stored aggregates.

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
