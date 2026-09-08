import { createHash } from 'node:crypto';
import Ajv from 'ajv';

export class ContractError extends Error {
  constructor(code, message, status = 400) { super(message); Object.assign(this, { code, status }); }
}
export const sha = value => createHash('sha256').update(typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value)).digest('hex');
export const visible = (tool, audience) => !tool._meta?.ui?.visibility || tool._meta.ui.visibility.includes(audience);
export const modelResult = result => ({content: result.content, structuredContent: result.structuredContent, isError: !!result.isError});

export function createPolicy(tools, configuration) {
  const ajv = new Ajv({ strict: false, allErrors: false, validateFormats: false });
  const admitted = new Map();
  for (const name of configuration.allowedTools) {
    const definition = tools.find(tool => tool.name === name);
    if (!definition) throw new ContractError('missing_tool', `Configured MCP tool is unavailable: ${name}`);
    admitted.set(name, { definition, validate: ajv.compile(definition.inputSchema) });
  }
  const approved = new Set(configuration.autoApproveTools || []);
  if ([...approved].some(name => !admitted.has(name))) throw new ContractError('invalid_policy', 'Approval policy exceeds allowed tools.');
  return {
    tools: [...admitted.values()].map(entry => entry.definition),
    authorize(name, args, audience, resourceUri) {
      const entry = admitted.get(name);
      if (!entry || !visible(entry.definition, audience)) throw new ContractError('tool_denied', 'Tool is not enabled for this caller.', 403);
      if (audience === 'app' && entry.definition._meta?.ui?.resourceUri !== resourceUri) throw new ContractError('resource_scope', 'Tool belongs to a different UI resource.', 403);
      if (!entry.validate(args)) throw new ContractError('invalid_arguments', 'Arguments do not match the discovered MCP schema.');
      return { tool: entry.definition, confirmation: entry.definition.annotations?.readOnlyHint !== true && !approved.has(name) };
    },
  };
}

export function checkedResource(result, uri) {
  const items = result.contents?.filter(item => item.uri === uri && item.mimeType === 'text/html;profile=mcp-app');
  if (items?.length !== 1 || typeof items[0].text !== 'string' || Buffer.byteLength(items[0].text) > 3_000_000
      || !/<head(?:\s[^>]*)?>/i.test(items[0].text)) throw new ContractError('resource_invalid', 'The MCP App resource is unavailable or exceeds this host’s limits.', 422);
  return { html: items[0].text, sha256: sha(items[0].text), uri };
}
