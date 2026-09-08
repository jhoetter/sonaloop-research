// The native customer renderer emits semantic HTML. A passive App does not
// inherit product navigation, scripts, images, forms, styles or event handlers.
const tags = new Set('ARTICLE HEADER H1 H2 H3 H4 H5 H6 DIV SPAN P UL OL LI STRONG B EM I DEL CODE PRE BLOCKQUOTE TABLE THEAD TBODY TR TH TD HR BR METER'.split(' '));
const sha = async text => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map(x => x.toString(16).padStart(2, '0')).join('');
export async function acceptPresentation(result, component) {
  const value = result?._meta?.['sonaloop/presentation'];
  if (result?.isError || !value || value.schema_version !== 'sonaloop.research-presentation.v1'
    || value.component_id !== component || !['ready', 'empty'].includes(value.state)
    || typeof value.html !== 'string' || new TextEncoder().encode(value.html).length > 192 * 1024
    || !/^[a-f0-9]{64}$/.test(value.text_sha256)) throw new Error('Invalid presentation');
  const text = (result.content || []).filter(block => block.type === 'text').map(block => block.text).join('\n');
  if (await sha(text) !== value.text_sha256) throw new Error('Result digest mismatch');
  const parsed = new DOMParser().parseFromString(value.html, 'text/html');
  const output = document.createDocumentFragment();
  function copy(node, parent) {
    if (node.nodeType === Node.TEXT_NODE) { parent.append(document.createTextNode(node.textContent)); return; }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = node.tagName.toUpperCase();
    if (['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'SVG', 'MATH', 'TEMPLATE', 'IMG', 'VIDEO', 'AUDIO', 'FORM', 'INPUT', 'BUTTON'].includes(tag)) return;
    const element = document.createElement(tags.has(tag) ? tag.toLowerCase() : 'span');
    if (tag === 'METER') {
      const value = node.getAttribute('value');
      // Only a unit-interval quantity is admitted. Native counts remain readable
      // beside it; arbitrary styles, URLs and interactive controls stay forbidden.
      if (!value || !/^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(value)
        || node.getAttribute('min') !== '0' || node.getAttribute('max') !== '1') throw new Error('Invalid meter');
      element.setAttribute('min', '0'); element.setAttribute('max', '1'); element.setAttribute('value', value);
      const label = node.getAttribute('aria-label');
      if (label && label.length <= 500) element.setAttribute('aria-label', label);
    }
    const names = (node.getAttribute('class') || '').split(/\s+/).filter(name => /^(sl-research-[a-z-]+|sl-prose|sl-note-summary|sl-cmdk-title|sl-cmdk-desc|sl-cmdk-meta|lead|strow|muted|small|sub)$/.test(name));
    if (tag === 'A') names.push('sl-research-link');
    if (names.length) element.className = names.join(' ');
    for (const child of node.childNodes) copy(child, element);
    parent.append(element);
  }
  for (const node of parsed.body.childNodes) copy(node, output);
  if (!output.textContent.trim()) throw new Error('Empty presentation');
  return output;
}
