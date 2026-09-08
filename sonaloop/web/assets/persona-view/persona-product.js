import { createPersonaView } from './persona-view.js';
import { createPersonaActions } from './persona-actions.js';
import { surfaceError, validateSurface } from './persona-contract.js';
import { messages, language } from './persona-i18n.js';

const mounted = new Map();
async function request(url, body) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), body?.action === 'generate_avatar' ? 220000 : 40000);
  try {
    const response = await fetch(url, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      ...(body ? { headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    const result = await response.json();
    if (result.error) throw surfaceError(result.error);
    if (!response.ok) throw surfaceError({ code: response.status === 403 ? 'forbidden' : 'request_failed', message: `Research request failed (${response.status}).` });
    return result;
  } catch (error) { if (error.code && typeof error.code === 'string') throw error; throw surfaceError({ code: 'request_failed', message: 'The connection ended before Research confirmed the result.' }); }
  finally { clearTimeout(timer); }
}
async function mount(root) {
  const config = JSON.parse(root.querySelector('script[type="application/json"]').textContent);
  if (typeof config.persona_id !== 'string' || typeof config.csrf_token !== 'string') return;
  const local = { disposed: false, view: undefined, root }; mounted.set(root, local);
  const endpoint = `/api/personas/${encodeURIComponent(config.persona_id)}/surface`;
  const actions = createPersonaActions({
    read: () => request(endpoint),
    invoke: (action, args) => request(`${endpoint}/actions`, { action, ...args, csrf_token: config.csrf_token }),
    inspect: async operation => { const response = await request(`/api/personas/surface-operations/${encodeURIComponent(operation)}`); return response.structuredContent ?? response; },
    unpack: async result => {
      const value = validateSurface(result.structuredContent);
      if (value.persona_id !== config.persona_id) throw surfaceError({ code: 'invalid_response' });
      const avatarSource = ['ready','stale'].includes(value.avatar.state) && value.avatar.sha256
        ? `/personas/${encodeURIComponent(value.persona_id)}/avatar?v=${encodeURIComponent(value.avatar.sha256)}` : null;
      return { value, avatarSource };
    },
  });
  try {
    const result = await actions.accept(await request(endpoint)); if (local.disposed) return;
    local.view = createPersonaView(root, { ...result, locale: config.locale, actions }); root.dataset.enhanced = 'true';
    // Preserve research observations; hide only the duplicated profile fallback.
    root.closest('[data-persona-surface-section]')?.querySelectorAll('[data-persona-surface-fallback]').forEach(node => { node.hidden = true; });
  } catch (error) {
    if (local.disposed) return;
    const feedback = document.createElement('p'); feedback.className = 'sl-persona-view-mount__error'; feedback.textContent = `${messages[language(config.locale)].readonly} · ${error.message}`; root.append(feedback);
  }
}
function scan() {
  for (const [root, state] of mounted) if (!root.isConnected) { state.disposed = true; state.view?.dispose(); mounted.delete(root); }
  for (const root of document.querySelectorAll('[data-persona-view]')) if (!mounted.has(root)) void mount(root);
}
function dirty() { return [...mounted.values()].some(state => state.view?.hasUnsavedChanges()); }
window.addEventListener('beforeunload', event => { if (dirty()) { event.preventDefault(); event.returnValue = ''; } });
// The product navigation consumes this cancelable event before replacing page or drawer contents.
document.addEventListener('sonaloop:before-navigation', event => { if (dirty() && !window.confirm(messages[language(document.documentElement.lang)].discard)) event.preventDefault(); });
document.addEventListener('spa:load', scan);
document.addEventListener('sonaloop:drawer-closed', event => {
  for (const [root,state] of mounted) if (event.detail?.root?.contains(root)) { state.disposed = true; state.view?.dispose(); root.removeAttribute('data-persona-view'); mounted.delete(root); }
});
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scan, { once: true }); else scan();
new MutationObserver(() => { for (const root of mounted.keys()) if (!root.isConnected) { scan(); break; } }).observe(document.documentElement, { childList: true, subtree: true });
