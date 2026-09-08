import { ContractError } from './policy.mjs';

const EVENT_BYTES = 2 * 1024 * 1024;
const STREAM_BYTES = 8 * 1024 * 1024;
const TEXT_BYTES = 256 * 1024;
const OUTPUT_BYTES = 1024 * 1024;
const identifier = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,256}$/.test(value);
const toolName = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const invalid = () => new ContractError('provider_stream_invalid', 'Ungültige Modellantwort im Datenstrom.', 502);
const limit = () => new ContractError('provider_stream_limit', 'Der Modell-Datenstrom überschreitet die erlaubte Größe.', 502);
const incomplete = () => new ContractError('provider_incomplete', 'Modellantwort unvollständig.', 502);

function completedBody(body) {
  if (!object(body) || body.status !== 'completed') throw incomplete();
  if (!identifier(body.id) || !Array.isArray(body.output)) throw invalid();
  if (body.output.length > 128 || Buffer.byteLength(JSON.stringify(body.output)) > OUTPUT_BYTES) throw limit();
  let textBytes = 0;
  for (const item of body.output) {
    if (!object(item) || typeof item.type !== 'string' || item.type.length > 128) throw invalid();
    if (item.type === 'function_call') {
      if (!identifier(item.id) || !toolName(item.name) || !identifier(item.call_id) || typeof item.arguments !== 'string') throw invalid();
      if (Buffer.byteLength(item.arguments) > 64 * 1024) throw limit();
    }
    if (item.type !== 'message') continue;
    if (!identifier(item.id)) throw invalid();
    if (!Array.isArray(item.content)) throw invalid();
    if (item.content.length > 128) throw limit();
    for (const part of item.content) {
      if (!object(part) || typeof part.type !== 'string') throw invalid();
      const text = part.type === 'output_text' ? part.text : part.type === 'refusal' ? part.refusal : undefined;
      if (part.type === 'output_text' || part.type === 'refusal') {
        if (typeof text !== 'string') throw invalid();
        textBytes += Buffer.byteLength(text);
        if (textBytes > TEXT_BYTES) throw limit();
      }
    }
  }
  if (body.usage != null && !object(body.usage)) throw invalid();
  if (body.usage && Buffer.byteLength(JSON.stringify(body.usage)) > 8192) throw limit();
  // Keep final output authoritative (including continuation items), never build it from deltas.
  let usage;
  if(body.usage){
    usage={};
    for(const name of ['input_tokens','output_tokens','total_tokens']) if(Number.isSafeInteger(body.usage[name]) && body.usage[name]>=0) usage[name]=body.usage[name];
  }
  const model=typeof body.model==='string'&&/^[A-Za-z0-9_.:-]{1,128}$/.test(body.model) ? body.model : undefined;
  return { id: body.id, status: 'completed', output: body.output, usage, ...(model ? {model} : {}) };
}

/** Read Responses SSE; only text and function names cross the progress callback boundary.
 * Event shapes: https://developers.openai.com/api/docs/guides/streaming-responses
 */
export async function readProviderStream(response, { signal, onEvent = () => {} } = {}) {
  let reader, cancelRequested = false;
  const cancel = reason => {
    if (!reader || cancelRequested) return;
    cancelRequested = true;
    // A custom underlying source may never settle cancel(); cleanup must not block abort.
    try { void reader.cancel(reason).catch(() => {}); } catch {}
  };
  let interrupt;
  const onAbort = () => { interrupt?.(signal.reason); cancel(signal.reason); };
  async function wait(task) {
    const operation = Promise.resolve(task);
    if (signal?.aborted) { void operation.catch(() => {}); throw signal.reason; }
    if (!signal) return await operation;
    // Keep only the current wait: racing every chunk against one unresolved abort
    // promise would retain a handler per chunk until the whole stream finishes.
    try {
      return await new Promise((resolve, reject) => {
        interrupt = reject;
        operation.then(resolve, reject);
      });
    } finally { interrupt = undefined; }
  }
  try {
    reader = response.body?.getReader();
    if (signal?.aborted) throw signal.reason;
    signal?.addEventListener('abort', onAbort, { once: true });
    if (!reader || response.headers?.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'text/event-stream') throw invalid();

    // One bounded line buffer avoids retaining arbitrarily many tiny network chunks.
    const line = new Uint8Array(EVENT_BYTES);
    const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
    let lineBytes = 0, eventBytes = 0, totalBytes = 0, deltaBytes = 0;
    let data = [], eventType = '', skipLF = false, firstLine = true;
    let completed;

    function append(bytes) {
      eventBytes += bytes.byteLength;
      if (eventBytes > EVENT_BYTES || lineBytes + bytes.byteLength > EVENT_BYTES) throw limit();
      line.set(bytes, lineBytes);
      lineBytes += bytes.byteLength;
    }

    async function dispatch() {
      if (!data.length) return;
      const encoded = data.join('\n');
      if (encoded.trim() === '[DONE]') throw incomplete();
      let event;
      try { event = JSON.parse(encoded); } catch { throw invalid(); }
      if (!object(event) || typeof event.type !== 'string' || (eventType && eventType !== event.type)) throw invalid();
      if (event.type === 'response.failed' || event.type === 'error' || event.type === 'response.error') {
        throw new ContractError('provider_error', 'Der Modellaufruf ist fehlgeschlagen.', 502);
      }
      if (event.type === 'response.incomplete') throw incomplete();
      if (event.type === 'response.completed') {
        completed = completedBody(event.response);
        return;
      }
      let projected;
      if (event.type === 'response.output_text.delta' || event.type === 'response.refusal.delta') {
        if (!identifier(event.item_id) || !Number.isSafeInteger(event.content_index) || event.content_index < 0 ||
            event.content_index > 1024 || typeof event.delta !== 'string') throw invalid();
        deltaBytes += Buffer.byteLength(event.delta);
        if (deltaBytes > TEXT_BYTES) throw limit();
        projected = { type: 'text', itemId: event.item_id, contentIndex: event.content_index, delta: event.delta };
      } else if (event.type === 'response.output_item.added' && event.item?.type === 'function_call') {
        if (!identifier(event.item.id) || !toolName(event.item.name)) throw invalid();
        projected = { type: 'tool', itemId: event.item.id, name: event.item.name };
      }
      // Argument deltas, reasoning, raw provider objects and diagnostics are never emitted.
      if (projected) await wait(onEvent(projected));
    }

    async function endLine() {
      let text = decoder.decode(line.subarray(0, lineBytes));
      lineBytes = 0;
      if (firstLine) { text = text.replace(/^\uFEFF/, ''); firstLine = false; }
      if (text === '') {
        await dispatch();
        data = []; eventType = ''; eventBytes = 0;
        return;
      }
      if (text.startsWith(':')) return;
      const colon = text.indexOf(':');
      const field = colon === -1 ? text : text.slice(0, colon);
      let value = colon === -1 ? '' : text.slice(colon + 1);
      if (value.startsWith(' ')) value = value.slice(1);
      if (field === 'event') eventType = value;
      if (field === 'data') {
        if (data.length >= 4096) throw limit();
        data.push(value);
      }
    }

    while (!completed) {
      const { done, value } = await wait(reader.read());
      if (signal?.aborted) throw signal.reason;
      if (done) throw incomplete(); // A partial last event is not an SSE dispatch.
      if (!(value instanceof Uint8Array)) throw invalid();
      totalBytes += value.byteLength;
      if (totalBytes > STREAM_BYTES) throw limit();
      let start = 0;
      for (let index = 0; index < value.length; index++) {
        const byte = value[index];
        if (skipLF) {
          skipLF = false;
          if (byte === 10) {
            if (eventBytes && ++eventBytes > EVENT_BYTES) throw limit();
            start = index + 1; continue;
          }
        }
        if (byte !== 10 && byte !== 13) continue;
        append(value.subarray(start, index));
        if (++eventBytes > EVENT_BYTES) throw limit();
        await endLine();
        if (signal?.aborted) throw signal.reason;
        if (completed) return completed;
        skipLF = byte === 13;
        start = index + 1;
      }
      append(value.subarray(start));
    }
    return completed;
  } catch (error) {
    if (signal?.aborted) throw signal.reason;
    if (error instanceof ContractError) throw error;
    // JSON, decoding and transport exceptions can contain private provider diagnostics.
    throw invalid();
  } finally {
    signal?.removeEventListener('abort', onAbort);
    cancel(signal?.aborted ? signal.reason : undefined);
    try { reader?.releaseLock(); } catch {}
  }
}
