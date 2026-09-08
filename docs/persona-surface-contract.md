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

Successful surface tools return the DTO as `structuredContent` and bounded useful
text in `content`. The optional validated PNG data URI is private to the rendering
host in result `_meta["sonaloop/avatarDataUri"]`. It is not sent in model context.
The adapter validates byte limits, PNG decode and dimensions before delivery.
Errors use `isError: true`, bounded text and `structuredContent.error`.
Operation inspection returns `{operation_id, status, result?, error?}`; result is
the safe DTO, never native provider metadata. Terminal statuses are `succeeded`,
`failed`, `conflict`, `outcome_unknown`; running status is `in_progress`.

The customer resource bundles the standard MCP Apps App client, the exact shared
view source and styles. Resource loading does not execute a tool. Text-only hosts
can use model-visible tools without any UI claim. Hosts retain sandbox and tool
authorization policy; metadata is not a grant.

## Shared browser view and package

`sonaloop/web/assets/persona-view/persona-view.js` exports
`createPersonaView(root, {value, locale, avatarSource, actions, onDirtyChange})`.
It returns `{update, dispose, hasUnsavedChanges}`. `update` accepts the next options
object. `actions.update(changes)` and `actions.generateAvatar(prompt)` return
`{value, avatarSource}`; `actions.refresh()` returns the same. Adapters own version,
operation IDs, transport, errors and uncertain-operation recovery. Rejected actions
retain input and the last confirmed image. Errors have `code` and optional `current`.

The view owns presentation, edits, dirty/busy/error states and accessible controls.
It knows no fetch/MCP routes, credentials, provider calls or Lab draft schema.
Click avatar opens the prompt, click name edits it. Multiple mounted instances and
SPA teardown must work. English and German use the native product language.

The product adapter and MCP adapter import that same source. Product assets use
content-hashed URLs because the existing static mount caches immutably. The built
self-contained HTML and a deterministic build manifest are shipped as package
data under `sonaloop/mcp_server/ui/`. The manifest binds source-file SHA-256s,
component ID, DTO version, resource URI, MIME, HTML bytes hash, fields, actions,
states and text fallback. Customer CI publishes both assets in the same wheel.
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
