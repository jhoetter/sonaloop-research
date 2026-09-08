import { App } from '@modelcontextprotocol/ext-apps';
import { acceptPresentation } from './research-view.js';

const component = document.querySelector('meta[name="sonaloop-component"]').content;
const root = document.querySelector('[data-research-app]');
const app = new App({ name: component, version: '1.0.0' }, {}, { autoResize: true });
let sequence = 0;
let waiting = true;
let disposed = false;
function context(value = {}) {
  if (disposed) return;
  if (typeof value.locale === 'string') document.documentElement.lang = value.locale;
  if (['light', 'dark'].includes(value.theme)) document.documentElement.dataset.theme = value.theme;
  if (waiting) root.textContent = document.documentElement.lang.startsWith('de') ? 'Ansicht wird geladen…' : 'Loading view…';
}
context();
app.onhostcontextchanged = context;
app.ontoolresult = async result => {
  if (disposed) return;
  const current = ++sequence;
  try {
    const fragment = await acceptPresentation(result, component);
    if (current !== sequence) return;
    waiting = false;
    root.replaceChildren(fragment);
  } catch {
    if (current !== sequence) return;
    waiting = false;
    root.textContent = document.documentElement.lang.startsWith('de')
      ? 'Diese Ansicht ist nicht verfügbar. Das ursprüngliche Tool-Ergebnis bleibt im Chat erhalten.'
      : 'This view is unavailable. The original tool result remains available in the chat.';
    return;
  }
  // Optional host telemetry cannot invalidate a successfully rendered result.
  Promise.resolve().then(() => app.sendLog({ level: 'info', logger: component, data: { event: 'view-rendered', component_id: component } })).catch(() => {});
};
app.onteardown = async () => { disposed = true; waiting = false; sequence++; root.replaceChildren(); return {}; };
app.connect().then(() => context(app.getHostContext())).catch(() => {
  if (disposed || !waiting) return;
  waiting = false;
  root.textContent = 'MCP App connection unavailable.';
});
