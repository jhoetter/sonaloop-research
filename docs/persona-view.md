# Research PersonaView

Research owns a single browser component used by the native persona detail page,
its SPA/drawer fragment, and the portable MCP App. The component edits the same
native persona and avatar in all three contexts. It does not maintain a second
profile store or depend on a separate product host.

## User flow

Click a displayed name, role, age, location, goal list or challenge list to edit
that field. Enter or the check button submits only that field; Escape cancels.
Lists use Shift+Enter for another line. The avatar opens a compact prompt dialog.
Generate sends that prompt to native Research image generation and stores the
result on the same persona. The prompt does not overwrite the profile's portrait
description; that field can be edited explicitly under Details.

The UI preserves typed input and the last confirmed image after failure. A
conflicting version blocks another save until the user explicitly reloads the
canonical profile. An uncertain write blocks further writes; Check status reads
the durable native operation and does not repeat the request or provider call. Closing an editor or prompt does not clear that
uncertainty: navigation and MCP host dirty-state guards remain active until an
explicit status read and canonical refresh succeed.
Imported profile shapes remain readable. Unsupported fields have no edit action;
capability reasons are available under Details. Profile edits retain native ID
and slug. An existing face is labelled stale when it belongs to an older profile.

Labels are German and English. Controls use normal keyboard focus, labelled
inputs, a modal dialog and live status messages. On a narrow screen, goal and
challenge sections stack; the avatar remains reachable at its display location.
The native page retains its server-rendered profile fallback, current state,
readiness, calendar, research findings, tools, relationships and memory links.

## Optional customer agent chat

The generic reference host in [examples/mcp-app-host](../examples/mcp-app-host/README.md)
can display this same MCP App inside its chat. The customer configures the MCP
server and permitted tools; the host contains no Persona-specific execution.
Host 0.2 defaults to `gpt-5.6-terra` and sends `reasoning: {effort: "none"}`.
`OPENAI_MODEL` takes precedence over the configured model. The API key stays on
the server, and the UI displays the model actually configured at the host.

Sending a message clears the composer immediately. You can type the next draft
while the current turn runs; finishing that turn does not erase the new draft.
When a request is explicitly rejected before acceptance, its text can be restored
only if the composer has not changed. Text streams as it is generated. Tool
preparation, approval, execution and results appear in their actual order, with
expandable arguments and results. A tool's MCP App stays attached to that tool
result when later text arrives. Required model-tool approvals appear beside the
proposed action; approval continues the same turn and is consumed once.

**Stop** fences further model work and tool dispatches in that turn. It does not
undo a completed action or promise cancellation of an already admitted native
write. A running action retains its eventual result; an ambiguous transport
outcome stays explicitly uncertain. Check the native operation's saved status
before deciding what to do next. A later model failure also preserves earlier
tool results. Actions initiated directly inside an MCP App retain their own
confirmation and operation status.

Connection recovery reads the existing, cookie-owner-bound turn snapshot using
`GET /api/host/chat/turns/:turnId`. If the first stream event was lost, the client
can look up the same snapshot through
`GET /api/host/chat/requests/:clientTurnId`. Neither route runs a model or tool.
Recovery does not automatically resend a POST. A missing snapshot alone does not
prove that a previously sent request could never have been accepted. Unknown
native write outcomes must not be treated as permission to repeat the write.

This reference host keeps chat state in process memory: at most 20 sessions,
40 turns, six model rounds per turn and four concurrent stream observers per
turn. Request identities remain available within that process so a repeated
`clientTurnId` replays its result instead of repeating its effects. Restarting
the host clears chat/replay state; native Research data remains in its own store.
Provider streams and retained results have explicit size limits; an oversized
tool result gets a text notice without changing the native action's outcome.
The [stream contract](../examples/mcp-app-host/stream-contract.mjs) defines the
versioned transport. Legacy JSON chat and direct MCP App tool calls remain
supported. Model inputs exclude private MCP `_meta`; owner-bound App results
still carry the metadata required by the component.

## Shared source and adapters

`sonaloop/web/assets/persona-view/persona-view.js` exports:

```js
const view = createPersonaView(root, {
  value, locale, avatarSource,
  actions: { update, generateAvatar, refresh },
  onDirtyChange,
});
view.update({ value, avatarSource });
view.hasUnsavedChanges();
view.dispose();
```

The view only renders the versioned DTO and calls injected callbacks. Each action
resolves `{value, avatarSource}`. It has no fetch, MCP client, cookie, bearer token
or persistence code. Native field projection, compatibility and write authority
are specified in [the surface contract](persona-surface-contract.md).

`persona-product.js` mounts and disposes instances on full pages and `spa:load`.
It sends authenticated same-origin requests to the native surface API, with the
request-local CSRF token for writes. Avatar bytes use the private native avatar
route, versioned by the returned hash. SPA and drawer navigation emit a cancelable
`sonaloop:before-navigation` event before discarding edits; full browser navigation
uses the standard before-unload guard.

`persona-mcp.js` mounts the same view through the MCP Apps SDK. It accepts a tool
result, refreshes `get_persona_surface` before presenting the current version,
and forwards explicit actions to the advertised App tools. Native PNG bytes come
from `_meta["sonaloop/avatarDataUri"]`, with bounded size/dimensions, SHA256 and
browser decode verification. Private media never enters text fallback. MCP hosts
own authorization of tool calls; UI metadata and capabilities are not grants.

`persona-actions.js` is the adapters' common operation controller. Writes carry a
fresh operation ID and the current native version. Transport/validation failures
with an unknown outcome preserve the pending operation ID. Recovery explicitly
reads the operation status and then fetches the current canonical persona. No
automatic write or image-generation retry exists.

## Reproducible package assets

```sh
cd tools/persona-ui
npm ci --no-audit --no-fund
npm run build
npm test
```

The lockfile pins MCP Apps 1.7.5, MCP SDK 1.30.0 and esbuild 0.25.12. Browser tests
use Playwright Core and `RESEARCH_BROWSER_EXECUTABLE` when set. Tests use synthetic
HTTP/tool results and PNG data; they never call a model or image provider.

The builder emits content-hashed product JavaScript/CSS under
`sonaloop/web/assets/persona-view/built/`, self-contained
`sonaloop/mcp_server/ui/persona.html`, and `persona.manifest.json`. These ship in
the Python package; a customer running an installed wheel needs no Node build.
The repository/source distribution carries reproducible source and tooling.

The generic manifest schema is `sonaloop.customer-ui-build.v1`. It declares the
component and DTO IDs, resource URI/MIME/file/hash/byte length, product asset
files/hashes, a source-path-to-SHA256 map, fields, App tool names, states and a
text fallback. `build_id` is SHA256 of every manifest field except `build_id`,
serialized as recursively sorted JSON keys, UTF-8, no spaces and no trailing
newline. Source hashes bind both adapters to the same component source. There is
no timestamp, absolute path or source commit inside the manifest; a release
receipt binds the immutable manifest bytes to its source commit separately.

Python tests check exact packaged hashes, inert request-local seeds, native
full-page/drawer mounts, cache policy and one-time shell asset registration.
Browser fixtures exercise the actual product bundle and self-contained MCP
resource through a real AppBridge in an opaque iframe. They establish component
and adapter compatibility, not live provider or production acceptance.
