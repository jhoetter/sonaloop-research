import { App } from '@modelcontextprotocol/ext-apps';
import { acceptPresentation } from './research-view.js';

const component = document.querySelector('meta[name="sonaloop-component"]').content;
const root = document.querySelector('[data-research-app]');
const app = new App({ name: component, version: '1.0.0' }, {}, { autoResize: true });
let sequence = 0;
function context(value = {}) {
  if (typeof value.locale === 'string') document.documentElement.lang = value.locale;
  if (['light', 'dark'].includes(value.theme)) document.documentElement.dataset.theme = value.theme;
}
app.onhostcontextchanged = context;
app.ontoolresult = async result => {
  const current = ++sequence;
  try {
    const fragment = await acceptPresentation(result, component);
    if (current !== sequence) return;
    root.replaceChildren(fragment);
    await app.sendLog({ level: 'info', logger: component, data: { event: 'view-rendered', component_id: component } });
  } catch {
    if (current !== sequence) return;
    root.textContent = document.documentElement.lang.startsWith('de')
      ? 'Diese Ansicht ist nicht verfügbar. Das ursprüngliche Tool-Ergebnis bleibt im Chat erhalten.'
      : 'This view is unavailable. The original tool result remains available in the chat.';
  }
};
app.onteardown = async () => { sequence++; root.replaceChildren(); return {}; };
app.connect().then(() => context(app.getHostContext())).catch(() => { root.textContent = 'MCP App connection unavailable.'; });
