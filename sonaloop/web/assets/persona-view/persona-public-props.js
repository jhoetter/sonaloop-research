import { validateSurface } from './persona-contract.js';
import { createPersonaView } from './persona-view.js';

const text = (maxLength = 4000, minLength = 0) => ({ type: 'string', maxLength, minLength });
const optionalText = () => ({ anyOf: [{ type: 'null' }, text()] });
const list = () => ({ type: 'array', maxItems: 100, items: text() });
const object = properties => ({ type: 'object', additionalProperties: false,
  properties, required: Object.keys(properties) });

/** Public JSON options for the existing view, restricted to read-only capabilities.
 * Native surface validation still owns the DTO. This schema grants no actions,
 * supplies no media, and is not the native profile/business schema.
 */
export const PERSONA_PROPS_SCHEMA = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  description: 'JSON options for createPersonaFromProps(root, {value, locale}), which calls the existing createPersonaView. Value is an authored Persona surface DTO with read-only capabilities, not a native profile or MCP envelope. The bounded public schema checks hash length; native surface validation also checks lowercase hexadecimal syntax. Props supply no actions, transport or image bytes.',
  ...object({
    locale: { type: 'string', enum: ['en', 'de'] },
    value: object({
      schema_version: { type: 'string', const: 'sonaloop.persona-surface.v1' },
      persona_id: text(256, 1), slug: text(256), version: text(256, 1),
      fields: object({ display_name: text(4000, 1), age: { anyOf: [{ type: 'null' }, text(), { type: 'number' }] },
        location: optionalText(), role_title: optionalText(), goals: list(), pain_points: list(),
        portrait_description: optionalText() }),
      avatar: object({ state: { type: 'string', enum: ['missing', 'ready', 'stale', 'unavailable'] },
        sha256: { anyOf: [{ type: 'null' }, text(64, 64)] },
        generated_at: optionalText(), profile_version: optionalText() }),
      capabilities: object({ edit: { type: 'array', maxItems: 0, items: false },
        generate_avatar: { type: 'boolean', const: false }, reasons: list() }),
      warnings: list(),
    }),
  }),
};

export function validatePersonaProps(props) {
  const pending = [{ value: props, depth: 0 }]; let nodes = 0;
  while (pending.length) {
    const { value, depth } = pending.pop();
    if (++nodes > 2048 || depth > 12) throw new Error('Persona public props exceed traversal limits');
    if (value === null || typeof value === 'boolean' || typeof value === 'string') continue;
    if (typeof value === 'number' && Number.isFinite(value)) continue;
    if (!value || typeof value !== 'object' || (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype))
      throw new Error('Persona public props must contain plain finite JSON values');
    for (const [key, child] of Object.entries(value)) {
      if (['_meta', '__proto__', 'constructor', 'prototype'].includes(key)) throw new Error('Private or reserved Persona prop');
      pending.push({ value: child, depth: depth + 1 });
    }
  }
  if (!props || Array.isArray(props) || Object.keys(props).length !== 2
      || !Object.hasOwn(props, 'value') || !Object.hasOwn(props, 'locale') || !['en', 'de'].includes(props.locale))
    throw new Error('Expected Persona public {value, locale} props');
  if (new TextEncoder().encode(JSON.stringify(props)).byteLength > 8192) throw new Error('Persona public props exceed the byte limit');
  validateSurface(props.value);
  if (props.value.capabilities.edit.length || props.value.capabilities.generate_avatar)
    throw new Error('Persona public props support read-only capabilities');
  return props;
}

/** No actions, transport, avatar loader or clock is installed by this entry. */
export function createPersonaFromProps(root, props) {
  const view = createPersonaView(root, validatePersonaProps(props));
  return { update: next => view.update(validatePersonaProps(next)), dispose: () => view.dispose() };
}
