# Customer MCP App reference host

This small local host connects an operator-selected MCP executable over stdio,
discovers its tools and resources, and renders standard MCP Apps. It contains no
Persona component, profile schema, image workflow, customer database or capture
service connection. Product-specific UI and operations come from the installed
customer MCP package. This is a local integration example, not a cloud agent platform.

## Run independently

Install Node 22+ and the customer Python wheel into a separate virtual environment.
Copy this example directory (or unpack `npm pack`) outside the repository:

```sh
npm ci
npm run build
cp config.example.json config.json
# Edit absolute command/cwd/data paths and the explicit allowedTools policy.
# Keep credentials outside config.json; inject OPENAI_API_KEY through the process environment.
MCP_APP_HOST_CONFIG=/absolute/customer/config.json npm start
```

Open the exact `hostOrigin`, by default `http://127.0.0.1:16007`. The card sandbox
uses the same forwarded port with an opaque iframe and a restrictive CSP. There is
no second browser port to forward. The optional operator-selected `productProxy`
mounts a local native product at its original paths, so product detail links can
be opened on the same port. Remove that setting if only the agent is needed.

The native MCP process receives configured `env`, PATH and optional OPENAI_API_KEY.
Set `SONALOOP_DATA_DIR` explicitly for a dedicated synthetic test store. Native
product and MCP processes must use the same data directory and authority context.
Production cloud authentication, multi-user provisioning and entitlement policy
belong in the customer's deployment and are not supplied by this local example.

## Tool and UI policy

`allowedTools` is an explicit installation policy, applied to live tools/list
schemas. Model calls cannot select app-only tools. App calls are constrained to
admitted tools associated with the same declared resource. Read-only hints guide
confirmation UX; the connected server remains responsible for actual authorization
and truthful semantics. UI metadata never grants database access.

Writes require an exact one-use host confirmation unless the operator explicitly
lists the tool in `autoApproveTools`. For an isolated owned test store, an operator
may enable direct card edits and image actions there; leave this list empty for
per-action confirmation. The generic host shows the tool name and exact arguments
and does not manufacture product-specific consent or a Persona workflow.

Resources are read only from the connected MCP server, bounded, hashed and pinned
to the successful call's view. Changed bytes fail closed on frame load. Metadata
URLs are never fetched. The sandbox denies network, storage origin, forms and nested
frames; validated private image data can arrive through the MCP result's `_meta`.
That private metadata is omitted from model input.

The direct tool panel works without a language-model key. A tool itself may call
an external provider, according to its semantics and the customer's policy. The
chat path uses the [OpenAI Responses function-calling flow](https://developers.openai.com/api/docs/guides/function-calling):
discovered MCP schemas become function definitions, the host executes chosen calls,
then returns bounded tool output to the model. `store:false`, serial tool calls and
round/context limits are set. The default is **GPT-5.6 Terra** (`gpt-5.6-terra`),
with explicit `reasoning.effort: none` to preserve the prior interactive latency
baseline. `OPENAI_MODEL` overrides the configured model. No silent fallback to an
older model occurs. Model access is checked by the real API, not inferred from a
label in the UI.

## Integration checks

```sh
npm test
npm run build
```

Protocol/security checks and browser fixtures are separate from native customer
execution. A successful synthetic fixture is not proof of a real provider call or
third-party host support. For a release, install the customer wheel outside its
checkout, inspect tools/list + resources/read, compare product/card native changes,
and test with the capture/governance service unreachable.

## Chat interaction and recovery

The composer clears the submitted text immediately and keeps focus. You can write
another draft while the response streams; finishing, stopping or approving the
current turn never erases that draft. Enter sends, Shift+Enter inserts a newline,
and IME composition does not submit. New chat resets the conversation after active
work finishes; unsaved edits in an MCP App must be completed first.

Text, tool preparation/execution/results and follow-up text arrive in chronological
parts. Tool details are collapsed by default. Customer MCP App frames remain
mounted while text streams, preserving their edit state. Write approvals appear
inside the corresponding tool step. App-initiated writes retain their exact generic
confirmation dialog. Tools and connection settings live behind the header button.

Scrolling follows new content only while you are near the bottom. After scrolling
up, use **Zur neuesten Nachricht** to follow again. The composer remains at the
bottom of short/mobile viewports. Markdown is parsed with pinned Marked and
sanitized with DOMPurify; arbitrary HTML, embedded media, scripts and event handlers
are not admitted into the chat DOM. Executable customer UI remains in its separate
opaque MCP App sandbox.

**Stop** requests a server-side fence against future work. A tool that already
started may still finish; its actual result is retained and the UI says so.
Stopping is not a rollback. If the stream disconnects, the host reads the saved turn
snapshot to recover completed effects, without repeating the original request.
The same browser can resolve its `clientTurnId` if the connection broke before
the first event. Unreachable status offers **Status prüfen**; it does not cause
an automatic POST retry. Text-only mode hides an existing App without remounting it.
Provider failures after a successful tool preserve its visible result/card.
The local host keeps bounded in-memory sessions/turns, not durable chat history
across host restarts (20 sessions, 40 turns per process). Native customer operations
retain their own durable authority. Displayed call payloads are bounded to 12 MiB
each and 48 MiB in aggregate per agent, including private rendering metadata.
A completed oversized result has an explicit text fallback; it never triggers a
repeat action. These limits also accommodate customer images encoded as data.

`stream-contract.mjs` describes the generic SSE/event/snapshot contract. The
production stream is actual OpenAI Responses + connected MCP execution. The
[shadcn AI SDK helper](https://ui.shadcn.com/docs/helpers/ai-sdk) informed the chat,
message-part, tool-state and approval interaction patterns; its predefined demo
transport is not used as a production agent. The existing framework-free host
keeps the customer package independent of a frontend framework migration.

Run the additional deterministic browser journey with `npm run test:chat-browser`.
It uses the real host, MCP fixture and AppBridge with a clearly synthetic provider
stream. It checks draft preservation, streamed text, inline approval, stable card
mounts, Stop, retained effects on failure, markdown and small viewports. No real
provider call or customer data write occurs in that test. `CHROMIUM_PATH` can name
an installed browser. The optional `HOST_UX_SCREENSHOTS` directory receives evidence.

Transport-failure regressions run with `npm run test:chat-recovery-browser`: stale
snapshots, recoverable approval, manual status recovery, early Stop and stable App
identity. These use injected local failures and make no real provider calls.

## Input previews before confirmation

For a tool that declares an MCP App resource, the host can load that same customer
resource while the action is waiting for approval. It sends the exact proposed
arguments through standard `tool-input`, with the discovered tool in standard
`hostContext.toolInfo`. It does not manufacture a successful tool result. A
compatible customer App can show an explicit unsaved preview; older Apps retain
technical input details as fallback. Resource initialization alone is not proof
that a customer preview rendered.

The preview is passive. Its owner/resource/hash-bound token permanently denies all
App tool calls, including reads, before approval-token creation or dispatch. The
native action uses the original frozen arguments only after the user's decision.
Decline/Stop before dispatch sends `tool-cancelled` and does not create data.
A generated portrait cannot appear in a proposal that contains no image.

After actual execution, the same resource/hash keeps its iframe and receives the
real tool result. The host switches to the new actual-result action grant and does
not send `tool-input` again. A changed resource requires a newly verified frame;
a native failure keeps the preview passive. An uncertain admitted write is never
reported as cancelled or automatically repeated.

Run `npm run test:input-preview-browser` for the generic fixture: zero tool dispatch
before approval, passive card before controls, frozen arguments, cancellation,
source/frame identity, real result promotion, restored App actions and error state.
The customer component remains responsible for preview projection and rendering.
