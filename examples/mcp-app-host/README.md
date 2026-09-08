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
round/context limits are set. `OPENAI_MODEL` overrides the configured model.

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
