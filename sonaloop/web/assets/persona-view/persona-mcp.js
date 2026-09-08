import { App } from '@modelcontextprotocol/ext-apps';
import { createPersonaView } from './persona-view.js';
import { createPersonaActions } from './persona-actions.js';
import { COMPONENT, SCHEMA, surfaceError, validateSurface, validatedAvatar } from './persona-contract.js';

const app = new App({ name: COMPONENT, version: '1.0.0' }, {}, { autoResize: true });
const root = document.querySelector('[data-persona-app]');
let view, locale = 'en', actions, sequence = 0;
const log = (event, extra = {}) => app.sendLog({ level: event === 'view-error' ? 'error' : 'info', logger: COMPONENT,
  data: { event, component_id: COMPONENT, schema_version: SCHEMA, persona_id: actions?.value?.persona_id, version: actions?.value?.version, ...extra } }).catch(() => {});
function toolError(result) { if (result.isError || result.structuredContent?.error) throw surfaceError(result.structuredContent?.error || { code: 'invalid_response' }); return result; }
const unpack = async result => {
  toolError(result); const value = validateSurface(result.structuredContent);
  return { value, avatarSource: await validatedAvatar(result._meta?.['sonaloop/avatarDataUri'], value.avatar.sha256) };
};
function createActions() {
  const call = async (name, args, timeout = 40000) => {
    try { return toolError(await app.callServerTool({ name, arguments: args }, { timeout })); }
    catch (error) { if (typeof error.code === 'string') throw error; throw surfaceError({ code: 'request_failed', message: 'The host did not confirm the tool result.' }); }
  };
  return createPersonaActions({
    read: persona_id => call('get_persona_surface', { persona_id }),
    invoke: (action, args) => call(action === 'update' ? 'update_persona_surface' : 'generate_persona_surface_avatar', { persona_id: actions.value.persona_id, ...args }, action === 'generate_avatar' ? 300000 : 40000),
    inspect: async operation_id => (await call('get_persona_surface_operation', { operation_id })).structuredContent,
    unpack,
  });
}
function hostContext(context = {}) {
  if (typeof context.locale === 'string') locale = context.locale;
  document.documentElement.lang = locale;
  if (['light','dark'].includes(context.theme)) { document.documentElement.dataset.theme = context.theme; document.documentElement.style.colorScheme = context.theme; }
  for (const [key, value] of Object.entries(context.styles?.variables || {})) if (/^--[a-zA-Z0-9_-]+$/.test(key) && typeof value === 'string' && !/[;{}<>]/.test(value)) document.documentElement.style.setProperty(key, value);
  view?.update({ locale });
}
app.onhostcontextchanged = hostContext;
app.ontoolresult = async result => {
  const turn = ++sequence;
  try {
    if (!actions) actions = createActions();
    await actions.accept(result);
    const accepted = await actions.refresh(); if (turn !== sequence) return;
    if (view) view.update(accepted);
    else view = createPersonaView(root, { ...accepted, locale, actions, onDirtyChange: dirty => log('view-dirty', { dirty }) });
    await log('view-rendered');
  } catch (error) {
    if (turn !== sequence) return;
    if (!view) root.textContent = error.message;
    await log('view-error', { code: error.code || 'invalid_response' });
  }
};
app.onteardown = async () => { sequence++; view?.dispose(); return {}; };
app.connect().then(() => hostContext(app.getHostContext())).catch(error => { root.textContent = error.message; });
