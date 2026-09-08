export const SCHEMA = 'sonaloop.persona-surface.v1';
export const PREVIEW_SCHEMA = 'sonaloop.persona-preview.v1';
export const COMPONENT = 'sonaloop.research.persona-view';
export const FIELDS = ['display_name', 'age', 'location', 'role_title', 'goals', 'pain_points', 'portrait_description'];
export const stableJSON = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value, max = 4000) => typeof value === 'string' && value.length <= max;
const optional = value => value === null || text(value);
const list = value => Array.isArray(value) && value.length <= 100 && value.every(item => text(item));
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const exact = (value, keys) => object(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
export function validatePreview(value) {
  const fields = value?.fields;
  if (!exact(value, ['schema_version', 'fields']) || value.schema_version !== PREVIEW_SCHEMA || !exact(fields, FIELDS)
    || !text(fields.display_name, 120) || !fields.display_name.trim()
    || !['location', 'role_title'].every(key => fields[key] === null || text(fields[key], 200))
    || !(fields.portrait_description === null || text(fields.portrait_description, 500))
    || !(fields.age === null || text(fields.age, 120) || typeof fields.age === 'number' && Number.isFinite(fields.age))
    || !['goals', 'pain_points'].every(key => Array.isArray(fields[key]) && fields[key].length > 0 && fields[key].length <= 8
      && fields[key].every(item => text(item, 180) && item.trim()))) {
    throw surfaceError({ code: 'invalid_preview', message: 'The proposed Persona cannot be previewed safely.' });
  }
  return value;
}
// Presentation only: native creation still validates and normalizes the complete
// authored profile. This projection never returns an identity or permissions.
export function projectRecordPreview(args, toolName) {
  if (toolName !== undefined && toolName !== 'record_persona_surface') return null;
  if (toolName === undefined && (!object(args) || !Object.hasOwn(args, 'profile'))) return null;
  const keys = ['description', 'profile', 'operation_id', ...(Object.hasOwn(args || {}, 'segment_hint') ? ['segment_hint'] : [])];
  if (!exact(args, keys) || !text(args.description, 8000) || !args.description.trim()
    || !text(args.operation_id, 200) || !args.operation_id.trim() || !object(args.profile)
    || !(args.segment_hint === undefined || args.segment_hint === null || text(args.segment_hint, 300))
    || JSON.stringify(args).length > 65536) throw surfaceError({ code: 'invalid_preview', message: 'Invalid Persona preview arguments.' });
  const profile = args.profile;
  if (!object(profile.demographics) || !object(profile.role) || !object(profile.identity_traits)) {
    throw surfaceError({ code: 'invalid_preview', message: 'The proposed Persona fields are incomplete.' });
  }
  return structuredClone(validatePreview({ schema_version: PREVIEW_SCHEMA, fields: {
    display_name: profile.display_name, age: profile.demographics.age ?? null, location: profile.demographics.location ?? null,
    role_title: profile.role.title ?? null, goals: profile.goals, pain_points: profile.pain_points,
    portrait_description: profile.identity_traits.avatar_profile ?? null,
  } }));
}
export function validateSurface(value, previous) {
  if (!exact(value, ['schema_version', 'persona_id', 'slug', 'version', 'fields', 'avatar', 'capabilities', 'warnings'])
    || value.schema_version !== SCHEMA || !text(value.persona_id, 256) || !value.persona_id
    || !text(value.slug, 256) || !text(value.version, 256) || !value.version
    || !exact(value.fields, FIELDS) || !text(value.fields.display_name) || !value.fields.display_name
    || !['location', 'role_title', 'portrait_description'].every(key => optional(value.fields[key]))
    || !(value.fields.age === null || text(value.fields.age) || typeof value.fields.age === 'number' && Number.isFinite(value.fields.age))
    || !list(value.fields.goals) || !list(value.fields.pain_points)
    || !exact(value.avatar, ['state', 'sha256', 'generated_at', 'profile_version'])
    || !['missing', 'ready', 'stale', 'unavailable'].includes(value.avatar.state)
    || !(value.avatar.sha256 === null || hash(value.avatar.sha256))
    || !optional(value.avatar.generated_at) || !optional(value.avatar.profile_version)
    || !exact(value.capabilities, ['edit', 'generate_avatar', 'reasons'])
    || !Array.isArray(value.capabilities.edit) || value.capabilities.edit.some(key => !FIELDS.includes(key))
    || typeof value.capabilities.generate_avatar !== 'boolean' || !list(value.capabilities.reasons) || !list(value.warnings)
    || previous && (value.persona_id !== previous.persona_id || value.slug !== previous.slug)) {
    throw Object.assign(new Error('Invalid Persona surface response.'), { code: 'invalid_response' });
  }
  return value;
}
export function surfaceError(error) {
  const safe = error && typeof error === 'object' ? error : {};
  return Object.assign(new Error(typeof safe.message === 'string' ? safe.message.slice(0, 1000) : 'The operation could not be completed.'),
    { code: typeof safe.code === 'string' ? safe.code : 'invalid_response',
      ...(safe.current ? { current: safe.current } : {}), ...(safe.operation_id ? { operation_id: safe.operation_id } : {}) });
}
export async function validatedAvatar(dataUri, expectedHash) {
  if (dataUri == null) return null;
  if (typeof dataUri !== 'string' || dataUri.length > 11184834 || !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(dataUri) || !hash(expectedHash)) throw surfaceError({ code: 'invalid_media', message: 'Invalid portrait media.' });
  const bytes = Uint8Array.from(atob(dataUri.slice(22)), char => char.charCodeAt(0));
  if (bytes.length < 24 || bytes.length > 8388608 || [137,80,78,71,13,10,26,10].some((byte,index) => bytes[index] !== byte)
    || String.fromCharCode(...bytes.slice(12,16)) !== 'IHDR') throw surfaceError({ code: 'invalid_media', message: 'Invalid PNG portrait.' });
  const header = new DataView(bytes.buffer);
  if (![header.getUint32(16),header.getUint32(20)].every(size => size > 0 && size <= 2048)) throw surfaceError({ code: 'invalid_media', message: 'Portrait dimensions exceed the limit.' });
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  if ([...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2,'0')).join('') !== expectedHash) throw surfaceError({ code: 'invalid_media', message: 'Portrait checksum mismatch.' });
  const image = new Image(); image.src = dataUri; await image.decode(); return dataUri;
}
