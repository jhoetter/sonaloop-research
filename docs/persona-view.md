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
