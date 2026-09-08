# Shared Persona surface contract v1

Research owns the Persona view, its native operations and its MCP App resource.
One browser view is used by the product page and MCP App. Neither the view nor
its adapters own a second Persona, avatar store or provider workflow.

## Native service and data

`sonaloop.persona_surface_contract` defines the transport-neutral DTO and errors.
`sonaloop.services._persona_surface` implements these functions, with keyword-only
`store=None` on all functions:

- `get_persona_surface(persona_id, *, store=None) -> PersonaSurface`
- `update_persona_surface(persona_id, changes, expected_version, operation_id, *, store=None) -> PersonaSurface`
- `record_persona_surface(description, profile, operation_id, segment_hint=None, *, store=None) -> PersonaSurface`
- `generate_persona_surface_avatar(persona_id, prompt, expected_version, operation_id, *, store=None) -> PersonaSurface`
- `get_persona_surface_operation(operation_id, *, store=None) -> dict`

The version is an opaque native-row token. IDs and slugs remain stable on rename.
DTO fields project native display_name, demographics.age/location, role.title,
goals, pain_points and identity_traits.avatar_profile. Older/imported profiles
must not be silently coerced or discarded: unsupported shapes disable that field
and explain the limitation. Age accepts the existing native string/number/null
forms. The view submits only the fields actually changed.

An avatar prompt belongs to the image operation; generating an image must not
implicitly rewrite the profile. `avatar.profile_version` describes the image's
profile basis; `stale` is based on a profile digest, not the avatar write timestamp.
The native avatar remains authoritative. DTOs contain no paths, bearer tokens,
arbitrary URLs or image bytes. Reads do not repair SOUL or mutate the store.

Every write binds an operation ID to the authenticated actor/workspace and exact
request digest. Exact retry rechecks current authority and returns the current
canonical DTO without re-executing the durable operation; mismatched reuse fails.
Operation inspection retains the outcome status but projects its result from the
current authorized record, so replay cannot roll the card back to an older DTO.
Conflicts never overwrite newer values. An unknown provider outcome is durable,
must be inspected, and is never retried automatically. Existing native write paths
must share the atomic protection. SOUL must describe the winning native record.

Public errors use `PersonaSurfaceError` with a bounded code/message, optional
operation_id and safe current DTO. Codes include `validation`, `not_found`,
`forbidden`, `conflict`, `operation_mismatch`, `in_progress`, `outcome_unknown`,
`provider_unavailable`, `provider_error`. Raw provider bodies/secrets stay private.

## Product HTTP adapter

- GET `/api/personas/{persona_id}/surface`: native DTO in `structuredContent`.
- POST `/api/personas/{persona_id}/surface/actions`: JSON `{action, operation_id,
  expected_version, changes?, prompt?, csrf_token}`; action is `update` or
  `generate_avatar`. Strictly reject irrelevant/unknown fields.
- GET `/api/personas/surface-operations/{operation_id}`: durable status.
- Existing private `/personas/{persona_id}/avatar` supplies the product image.

HTTP uses the existing actor/workspace/access and CSRF gate. Model or browser
arguments do not select authority. Success envelope is `{structuredContent: dto}`;
failure is `{error: {code, message, operation_id?, current?}}` with appropriate
HTTP status. Cache-Control is no-store for personal data and operation results.

## MCP adapter and resource

Tools `get_persona_surface` and `record_persona_surface` are model-visible.
`update_persona_surface`, `generate_persona_surface_avatar` and
`get_persona_surface_operation` are app-visible; writes carry truthful annotations.
`get_persona_surface` is also app-visible so a card can refresh. The resource is
`ui://sonaloop/persona/v1`, MIME `text/html;profile=mcp-app`. Tool metadata declares
`_meta.ui.resourceUri` and visibility. Existing native text tools remain compatible.
The optional `_meta["sonaloop/uiManifestUri"]` points to the read-only JSON resource
`sonaloop://ui/persona/manifest`, making the packaged build declaration inspectable
without local source access. It supplies provenance, never runtime permissions.

Successful surface tools return the DTO as `structuredContent` and bounded useful
text in `content`. The optional validated PNG data URI is private to the rendering
host in result `_meta["sonaloop/avatarDataUri"]`. It is not sent in model context.
The adapter validates an 8 MiB byte limit, PNG decode and maximum 2048×2048
dimensions before delivery. User image prompts are limited to 500 characters.
Errors use `isError: true`, bounded text and `structuredContent.error`.
Operation inspection returns `{operation_id, status, result?, error?}`; result is
the safe DTO, never native provider metadata. Terminal statuses are `succeeded`,
`failed`, `conflict`, `outcome_unknown`; running status is `in_progress`.

The customer resource bundles the standard MCP Apps App client, the exact shared
view source and styles. Resource loading does not execute a tool. Text-only hosts
can use model-visible tools without any UI claim. Hosts retain sandbox and tool
authorization policy; metadata is not a grant.

## Unsaved input preview

The same resource can render complete standard MCP Apps `toolinput` arguments
before `record_persona_surface` executes. The customer adapter projects the record
request into a separate, closed view model:

```js
createPersonaView(root, {
  preview: { schema_version: 'sonaloop.persona-preview.v1', fields },
  locale,
  previewStatus: 'pending', // optional; also 'cancelled' or 'failed'
});
```

`fields` contains exactly the seven `PersonaFields`: `display_name`, `age`,
`location`, `role_title`, `goals`, `pain_points` and `portrait_description`.
They project the proposed profile's display_name, demographics.age/location,
role.title, goals, pain_points and identity_traits.avatar_profile. The preview
has no persisted ID, slug, version, avatar, capabilities or actions. Its passive
portrait placeholder and explicit unsaved badge distinguish it from a saved
surface; fields and portrait remain non-interactive.

Projection is pure and checks a bounded record-request shape. Optional host
`toolInfo`, when supplied, must identify `record_persona_surface`; without it,
the adapter requires the strict record-argument shape. Unsupported or malformed
input falls back safely without treating strings as markup. The first accepted
complete arguments are frozen for approval. The preview performs no tool calls,
native reads, writes, avatar generation or refresh. This presentation check is
not native profile validation: the native service may normalize or reject the
proposal when the approved operation actually saves it.

The host owns resource preload, approval and grants for each execution phase.
It delivers standard tool input, cancellation and actual tool results; it never
manufactures a successful result to render a card. `toolcancelled` retains the
passive preview with a cancellation label. A failed actual result retains it
with an error label. `pending`, `cancelled` and `failed` describe presentation
lifecycle, not persistence truth or a durable operation inspection.

Only an actual result validated as `sonaloop.persona-surface.v1` promotes the
existing component through `update({value, actions, ...})`, enabling the existing
native actions and normal refresh. Later tool input cannot revert that canonical
view to a proposal. Native services, authorization, persistence and the product
adapter retain their existing contracts; there is no draft store or additional
wire protocol.

## Shared browser view and package

`sonaloop/web/assets/persona-view/persona-view.js` exports
`createPersonaView(root, {value, locale, avatarSource, actions, onDirtyChange})`.
It returns `{update, refresh, dispose, hasUnsavedChanges}`. `update` accepts the next options
object. `actions.update(changes)` and `actions.generateAvatar(prompt)` return
`{value, avatarSource}`; `actions.refresh()` returns the same. Adapters own version,
operation IDs, transport, errors and uncertain-operation recovery. Rejected actions
retain input and the last confirmed image. Errors have `code` and optional `current`.
`refresh()` uses the view's existing reload/error state. After preview promotion,
the confirmed saved result remains visible even if the following canonical read
fails; the user can check status without recreating the Persona.

The view owns presentation, edits, dirty/busy/error states and accessible controls.
It knows no fetch/MCP routes, credentials, provider calls or Lab draft schema.
Click avatar opens the prompt, click name edits it. Multiple mounted instances and
SPA teardown must work. English and German use the native product language.

The product adapter and MCP adapter import that same source. Product assets use
content-hashed URLs because the existing static mount caches immutably. The built
self-contained HTML and a deterministic build manifest are shipped as package
data under `sonaloop/mcp_server/ui/` as `persona.html` and `persona.manifest.json`. The manifest binds source-file SHA-256s,
component ID, DTO and preview schema versions, resource URI, MIME, HTML bytes hash,
fields, actions, persisted and preview states, and text fallback. Its schema remains
`sonaloop.customer-ui-build.v1`; the resource remains `ui://sonaloop/persona/v1`.
Customer CI publishes both assets in the same wheel.
No build timestamp, absolute checkout path, private runtime data or secret is an
input to the reproducible bundle. Source commit/repository are release-envelope
facts, so the bundle does not contain its own circular commit identity.

## Ownership and compatibility

Native services own validation, authorization, concurrency and persistence.
Adapters select transport only. A generic host discovers tools/resources and
renders standard MCP Apps without Persona field names or workflow branches.
The installed customer package operates with capture/governance services offline.
External catalog systems may record exact declared bindings and source evidence;
their review records are separate from customer runtime authorization.
