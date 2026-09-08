import { validateSurface, validatePreview } from './persona-contract.js';
import { language, messages } from './persona-i18n.js';

let instances = 0;
const node = (tag, cls, text) => { const el = document.createElement(tag); if (cls) el.className = cls; if (text != null) el.textContent = String(text); return el; };
const button = (text, label, click, cls = '') => { const el = node('button', cls, text); el.type = 'button'; if (label) el.setAttribute('aria-label', label); el.addEventListener('click', click); return el; };
const unknown = error => ['in_progress', 'outcome_unknown', 'request_failed'].includes(error?.code);

/** One customer-owned, transport-free view. Adapters return canonical values only. */
export function createPersonaView(root, options) {
  const initialPreview = options.value === undefined ? validatePreview(options.preview) : null;
  if (!initialPreview) validateSurface(options.value);
  let opts = { ...options }, value = options.value, preview = initialPreview, copy = messages[language(options.locale)];
  let editor, dialog, busy = '', error, conflict = false, uncertain = false, disposed = false, imageSource = null, imageSequence = 0;
  const prefix = `sl-persona-${++instances}`;
  const card = node('article', 'sl-persona-view');
  const status = node('div', 'sl-persona-view__status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const body = node('div', 'sl-persona-view__body');
  root.replaceChildren(card); card.append(body, status);
  function dirty() { return !!editor || !!dialog || uncertain || ['update', 'generate'].includes(busy); }
  function notifyDirty() { opts.onDirtyChange?.(dirty()); }
  function writable(field) { return !preview && !busy && !uncertain && !conflict && !!opts.actions && (field ? value.capabilities.edit.includes(field) : value.capabilities.generate_avatar); }
  function report(cause) {
    error = cause; uncertain = uncertain || unknown(cause); conflict = cause?.code === 'conflict';
    notifyDirty(); renderStatus(); updateDisabled();
  }
  function updateDisabled() {
    for (const control of body.querySelectorAll('[data-field]')) control.disabled = !writable(control.dataset.field) || !!editor;
    const avatar = body.querySelector('[data-action="avatar"]'); if (avatar) avatar.disabled = !writable() || !!editor;
    if (editor) editor.save.disabled = !!busy || uncertain || conflict;
    if (dialog) dialog.generate.disabled = !!busy || uncertain || conflict;
  }
  function renderStatus() {
    status.replaceChildren(); card.setAttribute('aria-busy', busy ? 'true' : 'false');
    card.dataset.mode = preview ? 'preview' : 'persisted';
    if (preview) {
      const state = ['cancelled', 'failed'].includes(opts.previewStatus) ? opts.previewStatus : 'pending';
      card.dataset.previewStatus = state;
      status.append(node('p', 'sl-persona-view__preview-state', copy[`preview_${state}`]), node('p', '', copy.previewHint));
      return;
    }
    delete card.dataset.previewStatus;
    if (busy) status.append(node('p', '', busy === 'generate' ? copy.generating : copy.saving));
    else if (error) {
      const p = node('p', 'sl-persona-view__error', uncertain ? copy.pending : conflict ? copy.conflict : `${error.message || copy.unavailable} ${copy.retained}`);
      p.setAttribute('role', 'alert'); status.append(p);
    } else if (dirty()) status.append(node('p', '', copy.dirty));
    if (error || conflict || uncertain) status.append(button(uncertain ? copy.unknown : dirty() ? copy.refreshDirty : copy.refresh, null, refresh, 'sl-persona-view__secondary'));
  }
  function renderField(field, tag = 'div') {
    const wrap = node(tag, `sl-persona-view__field sl-persona-view__field--${field}`); wrap.dataset.personaField = field;
    const v = (preview || value).fields[field];
    if (field !== 'display_name') wrap.append(node('span', 'sl-persona-view__label', copy[field]));
    const content = node('span', 'sl-persona-view__field-value');
    if (Array.isArray(v) && v.length) { const list = node('ul'); for (const item of v) list.append(node('li', '', item)); content.append(list); }
    else content.textContent = v == null || v === '' || Array.isArray(v) ? copy.empty : String(v);
    if (!preview && value.capabilities.edit.includes(field) && opts.actions?.update) {
      const control = button('', `${copy.edit}: ${copy[field]}`, () => editField(field), 'sl-persona-view__edit');
      control.dataset.field = field; control.append(content, node('span', 'sl-persona-view__pencil', '✎')); wrap.append(control);
    } else wrap.append(content);
    return wrap;
  }
  function render() {
    if (disposed) return;
    body.replaceChildren();
    const top = node('div', 'sl-persona-view__top');
    const portrait = node('div', 'sl-persona-view__portrait');
    const avatar = preview ? node('div', 'sl-persona-view__avatar sl-persona-view__avatar--preview')
      : button('', imageSource ? copy.change : copy.create, openPrompt, 'sl-persona-view__avatar');
    if (!preview) avatar.dataset.action = 'avatar';
    if (imageSource) { const img = node('img'); img.src = imageSource; img.alt = `${copy.imageAlt}: ${value.fields.display_name}`; img.width = 320; img.height = 320; avatar.append(img); }
    else { avatar.append(node('span', 'sl-persona-view__silhouette', '◯'), node('span', '', preview ? copy.previewPortrait : copy.missing)); }
    if (!preview) avatar.append(node('span', 'sl-persona-view__avatar-action', imageSource ? copy.change : copy.create));
    portrait.append(avatar, node('p', 'sl-persona-view__caption', preview ? '' : value.avatar.state === 'unavailable' ? copy.unavailable : value.avatar.state === 'stale' ? copy.stale : imageSource ? copy.generated : ''));
    const identity = node('div', 'sl-persona-view__identity'); identity.append(node('span', 'sl-persona-view__eyebrow', preview ? copy.previewTitle : copy.persona), renderField('display_name', 'h2'), renderField('role_title'));
    const facts = node('div', 'sl-persona-view__facts'); facts.append(renderField('age'), renderField('location')); identity.append(facts); top.append(portrait, identity);
    const lists = node('div', 'sl-persona-view__lists'); lists.append(renderField('goals'), renderField('pain_points'));
    const details = node('details', 'sl-persona-view__details'); details.append(node('summary', '', copy.details), renderField('portrait_description'), node('p', '', preview ? copy.previewValidation : copy.native));
    if (!preview && (!opts.actions || !value.capabilities.edit.length)) details.append(node('p', '', copy.readonly));
    if (!preview) for (const warning of [...value.capabilities.reasons, ...value.warnings]) details.append(node('p', '', warning));
    body.append(top, lists, details); renderStatus(); updateDisabled();
  }
  function cancelEdit() {
    if (busy) return;
    const field = editor?.field; editor = undefined; if (!uncertain && !conflict) error = undefined; notifyDirty(); render();
    if (field) body.querySelector(`[data-field="${field}"]`)?.focus();
  }
  function editField(field) {
    if (editor || !writable(field)) return;
    error = undefined;
    const wrap = body.querySelector(`[data-persona-field="${field}"]`), original = value.fields[field], list = Array.isArray(original);
    const input = node(list || field === 'portrait_description' ? 'textarea' : 'input', 'sl-persona-view__input'); input.id = `${prefix}-${field}`;
    input.value = list ? original.join('\n') : original == null ? '' : String(original);
    input.setAttribute('aria-label', copy[field]); input.autocomplete = 'off';
    if (!list) input.maxLength = field === 'display_name' ? 120 : field === 'portrait_description' ? 500 : field === 'age' ? 120 : 200;
    if (field === 'age' && typeof original === 'number') input.inputMode = 'decimal';
    const form = node('form', 'sl-persona-view__editor'); const controls = node('div', 'sl-persona-view__editor-actions');
    const save = button('✓', `${copy.save}: ${copy[field]}`, saveEdit, 'sl-persona-view__save'); save.dataset.action = 'save-field';
    controls.append(save, button('×', copy.cancel, cancelEdit), node('span', '', list ? copy.listHint : copy.keyHint));
    form.append(input, controls); form.addEventListener('submit', e => { e.preventDefault(); saveEdit(); });
    input.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); } else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); saveEdit(); } });
    editor = { field, input, save, version: value.version, original }; wrap.replaceChildren(form); notifyDirty(); renderStatus(); updateDisabled(); input.focus(); input.select();
  }
  async function saveEdit() {
    if (!editor || busy || uncertain || conflict) return;
    if (editor.version !== value.version) { report({ code: 'conflict' }); return; }
    const { field, original, input } = editor;
    let change = input.value.trim();
    if (Array.isArray(original)) {
      change = change.split('\n').map(s => s.trim()).filter(Boolean);
      if (change.length < 1 || change.length > 8 || change.some(s => s.length > 180)) { report({ message: copy.invalidList }); return; }
    } else if (field === 'display_name' && !change) { report({ message: copy.required }); return; }
    else if (field === 'age') { if (!change) change = null; else if (typeof original === 'number') { change = Number(change); if (!Number.isFinite(change)) { report({ message: copy.required }); return; } } }
    else if (!change) change = null;
    if (JSON.stringify(change) === JSON.stringify(original)) { cancelEdit(); return; }
    busy = 'update'; error = undefined; notifyDirty(); renderStatus(); updateDisabled();
    try {
      const result = await opts.actions.update({ [field]: change }); if (disposed) return;
      validateSurface(result.value, value); editor = undefined; busy = ''; conflict = false; uncertain = false; notifyDirty(); await apply(result); body.querySelector(`[data-field="${field}"]`)?.focus();
    } catch (cause) { if (!disposed) { busy = ''; report(cause); } }
  }
  function closePrompt() {
    if (!dialog || busy) return;
    const old = dialog; dialog = undefined; old.element.close(); old.element.remove(); notifyDirty(); renderStatus(); body.querySelector('[data-action="avatar"]')?.focus();
  }
  function openPrompt() {
    if (dialog || editor || !writable()) return;
    error = undefined;
    const element = node('dialog', 'sl-persona-view__dialog'); element.setAttribute('aria-labelledby', `${prefix}-prompt-title`);
    const title = node('h3', '', copy.prompt); title.id = `${prefix}-prompt-title`;
    const hint = node('p', '', copy.promptHint); hint.id = `${prefix}-prompt-hint`;
    const input = node('textarea', 'sl-persona-view__input'); input.maxLength = 500; input.rows = 4; input.value = value.fields.portrait_description || ''; input.placeholder = copy.promptExample; input.setAttribute('aria-label', copy.prompt); input.setAttribute('aria-describedby', hint.id);
    const feedback = node('p', 'sl-persona-view__error'); feedback.setAttribute('role', 'alert');
    const controls = node('div', 'sl-persona-view__dialog-actions');
    const generate = button(copy.generate, null, generateAvatar, 'sl-persona-view__save'); generate.dataset.action = 'generate-avatar';
    controls.append(button(copy.cancel, null, closePrompt), generate); element.append(title, hint, input, feedback, controls); card.append(element);
    dialog = { element, input, feedback, generate, version: value.version }; element.addEventListener('cancel', e => { e.preventDefault(); closePrompt(); });
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); generateAvatar(); } });
    notifyDirty(); renderStatus(); element.showModal(); input.focus();
  }
  async function generateAvatar() {
    if (!dialog || busy || uncertain || conflict) return;
    if (dialog.version !== value.version) { report({ code: 'conflict' }); return; }
    const prompt = dialog.input.value.trim(); if (!prompt || prompt.length > 500) { dialog.feedback.textContent = copy.promptLimit; return; }
    busy = 'generate'; error = undefined; notifyDirty(); dialog.feedback.textContent = copy.generating; renderStatus(); updateDisabled();
    try {
      const result = await opts.actions.generateAvatar(prompt); if (disposed) return;
      validateSurface(result.value, value); busy = ''; uncertain = false; conflict = false; closePrompt(); await apply(result); body.querySelector('[data-action=avatar]')?.focus();
    } catch (cause) { if (!disposed) { busy = ''; report(cause); dialog.feedback.replaceChildren(node('span', '', uncertain ? copy.pending : cause.message || copy.unavailable), button(uncertain ? copy.unknown : copy.refreshDirty, null, refresh, 'sl-persona-view__secondary'));  } }
  }
  async function refresh() {
    if (preview || busy) return;
    busy = 'refresh'; renderStatus(); updateDisabled();
    try {
      const result = await opts.actions.refresh(); if (disposed) return;
      validateSurface(result.value, value); busy = ''; editor = undefined; if (dialog) closePrompt(); error = undefined; uncertain = false; conflict = false; notifyDirty(); await apply(result);
    } catch (cause) { if (!disposed) { busy = ''; report(cause); } }
  }
  async function apply(result) {
    value = result.value;
    if ((editor && editor.version !== value.version) || (dialog && dialog.version !== value.version)) { report({ code: 'conflict' }); return; }
    const sequence = ++imageSequence;
    const source = result.avatarSource ?? null;
    if (source && source !== imageSource) {
      try {
        const url = new URL(source, location.href);
        if (!(url.protocol === 'data:' && source.startsWith('data:image/png;base64,')) && !(url.origin === location.origin && url.protocol !== 'data:')) throw new Error('Invalid image source');
        const candidate = new Image(); candidate.src = source; await candidate.decode();
        if (disposed || sequence !== imageSequence) return;
        imageSource = source;
      } catch (cause) { if (disposed || sequence !== imageSequence) return; error = { message: copy.unavailable }; }
    } else if (!source && ['missing', 'unavailable'].includes(value.avatar.state)) imageSource = null;
    if (!disposed && !editor) render();
  }
  render(); if (!preview) void apply({ value, avatarSource: opts.avatarSource });
  return {
    update(next) {
      if (disposed) return;
      if (!preview && next.preview !== undefined) return;
      if (preview && next.value === undefined) {
        if (next.preview !== undefined) validatePreview(next.preview);
        opts = { ...opts, ...next }; copy = messages[language(opts.locale)];
        render(); return;
      }
      validateSurface(next.value ?? value, value);
      preview = null;
      opts = { ...opts, ...next }; copy = messages[language(opts.locale)];
      void apply({ value: next.value ?? value, avatarSource: next.avatarSource === undefined ? imageSource : next.avatarSource });
    },
    refresh,
    hasUnsavedChanges: dirty,
    dispose() { disposed = true; imageSequence++; if (dialog) { dialog.element.close(); dialog.element.remove(); } editor = undefined; dialog = undefined; opts.onDirtyChange?.(false); root.replaceChildren(); },
  };
}
