import test from 'node:test';
import assert from 'node:assert/strict';
import { readProviderStream } from '../provider-stream.mjs';
import { ContractError } from '../policy.mjs';

const encode = text => new TextEncoder().encode(text);
const complete = (output = [], extra = {}) => ({ type: 'response.completed', response: {
  id: 'resp_test', status: 'completed', output, usage: { input_tokens: 1, output_tokens: 2, total_tokens: 3 }, ...extra,
} });
const packet = event => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
const delta = (text, extra = {}) => ({ type: 'response.output_text.delta', item_id: 'msg_one', content_index: 0, delta: text, ...extra });
const message = text => ({ type: 'message', id: 'msg_one', content: [{ type: 'output_text', text }] });
function fixture(text, { chunkSize = 65536, contentType = 'text/event-stream; charset=utf-8', close = true } = {}) {
  const bytes = typeof text === 'string' ? encode(text) : text;
  let offset = 0, cancelled = false;
  const body = new ReadableStream({
    pull(controller) {
      if (offset < bytes.length) {
        controller.enqueue(bytes.subarray(offset, offset + chunkSize)); offset += chunkSize;
      } else if (close) controller.close();
    },
    cancel() { cancelled = true; },
  });
  return { response: new Response(body, { headers: { 'content-type': contentType } }), cancelled: () => cancelled };
}
const rejects = (operation, code) => assert.rejects(operation, error => {
  assert.ok(error instanceof ContractError);
  assert.equal(error.code, code);
  assert.equal(error.status, 502);
  assert.equal(JSON.stringify({ message: error.message, ...error }).includes('PRIVATE'), false);
  return true;
});

test('tiny UTF-8 chunks, CRLF, comments and multiline data produce only safe early projections', async () => {
  const output = [message('Final authoritative text')];
  const text = '\uFEFF: heartbeat\r\n\r\n' +
    'id: ignored\r\nretry: 1000\r\nevent: response.output_text.delta\r\n' +
    'data: {"type":"response.output_text.delta",\r\n' +
    'data: "item_id":"msg_one","content_index":0,"delta":"Grüße 👋"}\r\n\r\n' +
    packet(delta('Bitte', { type: 'response.refusal.delta', private: 'PRIVATE' })).replaceAll('\n', '\r\n') +
    packet({ type: 'response.output_item.added', item: { type: 'function_call', id: 'fc_one', name: 'get_persona_surface', arguments: 'PRIVATE' } }) +
    packet({ type: 'response.function_call_arguments.delta', delta: 'PRIVATE' }) +
    packet({ type: 'response.reasoning_text.delta', delta: 'PRIVATE' }) +
    packet(complete(output, { instructions: 'PRIVATE', error: 'PRIVATE' })) + 'data: [DONE]\n\n';
  const f = fixture(text, { chunkSize: 1, close: false });
  const events = [];
  const result = await readProviderStream(f.response, { onEvent: event => events.push(event) });
  assert.deepEqual(events, [
    { type: 'text', itemId: 'msg_one', contentIndex: 0, delta: 'Grüße 👋' },
    { type: 'text', itemId: 'msg_one', contentIndex: 0, delta: 'Bitte' },
    { type: 'tool', itemId: 'fc_one', name: 'get_persona_surface' },
  ]);
  assert.deepEqual(result, { id: 'resp_test', status: 'completed', output, usage: { input_tokens: 1, output_tokens: 2, total_tokens: 3 } });
  assert.equal(JSON.stringify(events).includes('PRIVATE'), false);
  assert.equal(f.cancelled(), true);
  assert.equal(f.response.body.locked, false);
});

test('a delta is delivered while completion is still pending; arguments come only from final output', async () => {
  let controller, notify;
  const first = new Promise(resolve => { notify = resolve; });
  const body = new ReadableStream({ start(value) { controller = value; } });
  const pending = readProviderStream(new Response(body, { headers: { 'content-type': 'text/event-stream' } }), { onEvent: notify });
  controller.enqueue(encode(packet(delta('Live'))));
  assert.equal((await first).delta, 'Live');
  const output = [{ type: 'function_call', id: 'fc_one', name: 'read', call_id: 'call_one', arguments: '{"final":true}' }];
  controller.enqueue(encode(packet(complete(output))));
  assert.deepEqual((await pending).output, output);
});

test('bare CR line endings and unnamed SSE events are accepted', async () => {
  const text = `data:${JSON.stringify(complete())}\r\r`;
  assert.equal((await readProviderStream(fixture(text, { chunkSize: 1 }).response)).status, 'completed');
});

test('usage exposes only nonnegative integer token totals', async () => {
  const usage = { input_tokens: 4, output_tokens: 7, total_tokens: 11, private: 'PRIVATE',
    input_tokens_details: { cached_tokens: 3 }, output_tokens_details: { reasoning_tokens: 2 } };
  const result = await readProviderStream(fixture(packet(complete([], { usage }))).response);
  assert.deepEqual(result.usage, { input_tokens: 4, output_tokens: 7, total_tokens: 11 });
  assert.equal(JSON.stringify(result).includes('PRIVATE'), false);
  const invalidTotals = { input_tokens: -1, output_tokens: 1.5, total_tokens: 'PRIVATE' };
  assert.deepEqual((await readProviderStream(fixture(packet(complete([], { usage: invalidTotals }))).response)).usage, {});
});

test('EOF, DONE and non-completed terminal bodies never grant completed output', async () => {
  for (const text of ['', packet(delta('partial')), 'data: [DONE]\n\n', packet(complete()).trimEnd(),
    packet(complete([], { status: 'in_progress' }))]) {
    await rejects(() => readProviderStream(fixture(text).response), 'provider_incomplete');
  }
});

test('provider failures and read errors are sanitized without emitting raw diagnostics', async () => {
  for (const type of ['response.failed', 'response.incomplete', 'response.error', 'error']) {
    const events = [];
    const f = fixture(packet({ type, message: 'PRIVATE', response: { error: { message: 'PRIVATE' } } }), { close: false });
    await rejects(() => readProviderStream(f.response, { onEvent: value => events.push(value) }), type === 'response.incomplete' ? 'provider_incomplete' : 'provider_error');
    assert.deepEqual(events, []);
    assert.equal(f.cancelled(), true);
  }
  const body = new ReadableStream({ pull(controller) { controller.error(new Error('PRIVATE')); } });
  await rejects(() => readProviderStream(new Response(body, { headers: { 'content-type': 'text/event-stream' } })), 'provider_stream_invalid');
});

test('invalid content type, JSON, UTF-8 and typed projections are rejected safely', async () => {
  const wrongType = fixture(packet(complete()), { contentType: 'application/json', close: false });
  await rejects(() => readProviderStream(wrongType.response), 'provider_stream_invalid');
  assert.equal(wrongType.cancelled(), true);
  for (const text of ['data: PRIVATE\n\n', 'data: null\n\n',
    'event: response.completed\ndata: {"type":"response.created"}\n\n',
    packet(delta('PRIVATE', { content_index: -1 })),
    packet({ type: 'response.output_item.added', item: { type: 'function_call', id: 'fc_one', name: 'PRIVATE\nname' } }),
    packet(complete(null)), packet(complete([], { id: '' })),
    packet(complete([{ type: 'message', content: [{ type: 'output_text', text: 'PRIVATE' }] }])),
    packet(complete([{ type: 'function_call', name: 'read', call_id: 'call_one', arguments: '{}' }]))]) {
    await rejects(() => readProviderStream(fixture(text).response), 'provider_stream_invalid');
  }
  await rejects(() => readProviderStream(fixture(new Uint8Array([100, 97, 116, 97, 58, 32, 255, 10, 10])).response), 'provider_stream_invalid');
});

test('abort interrupts an unresolved read and cancels without waiting for underlying cancellation', async () => {
  const abort = new AbortController();
  const reason = new Error('caller cancellation');
  let cancelled, cancelReason;
  const body = new ReadableStream({ cancel(value) { cancelled = true; cancelReason = value; return new Promise(() => {}); } });
  const response = new Response(body, { headers: { 'content-type': 'text/event-stream' } });
  const pending = readProviderStream(response, { signal: abort.signal });
  abort.abort(reason);
  await assert.rejects(pending, error => error === reason);
  assert.equal(cancelled, true);
  assert.equal(cancelReason, reason);
  assert.equal(response.body.locked, false);
});

test('already aborted input still cancels its reader and preserves the exact reason', async () => {
  const abort = new AbortController(); abort.abort('cancelled before reading');
  const f = fixture('', { close: false });
  await assert.rejects(readProviderStream(f.response, { signal: abort.signal }), error => error === abort.signal.reason);
  assert.equal(f.cancelled(), true);
});

test('abort also interrupts a pending asynchronous progress callback', async () => {
  const abort = new AbortController();
  const f = fixture(packet(delta('pending')), { close: false });
  let notify;
  const entered = new Promise(resolve => { notify = resolve; });
  const pending = readProviderStream(f.response, { signal: abort.signal, onEvent: () => {
    notify(); return new Promise(() => {});
  } });
  await entered;
  abort.abort('cancelled during progress');
  await assert.rejects(pending, error => error === abort.signal.reason);
  assert.equal(f.cancelled(), true);
});

test('event size and cumulative stream size include ignored provider data', async () => {
  const giant = fixture('data: ' + 'x'.repeat(2 * 1024 * 1024), { close: false });
  await rejects(() => readProviderStream(giant.response), 'provider_stream_limit');
  assert.equal(giant.cancelled(), true);
  const ignored = packet({ type: 'response.reasoning_text.delta', delta: 'PRIVATE' + 'x'.repeat(512 * 1024) });
  const total = fixture(ignored.repeat(17), { close: false });
  await rejects(() => readProviderStream(total.response), 'provider_stream_limit');
  assert.equal(total.cancelled(), true);
});

test('cumulative delta text and authoritative final output have independent bounds', async () => {
  const seen = [];
  const f = fixture(packet(delta('ä'.repeat(64 * 1024))) + packet(delta('b'.repeat(128 * 1024))) + packet(delta('c')));
  await rejects(() => readProviderStream(f.response, { onEvent: event => seen.push(event) }), 'provider_stream_limit');
  assert.equal(seen.length, 2);
  for (const output of [[message('x'.repeat(256 * 1024 + 1))], Array.from({ length: 129 }, () => message('')),
    [{ type: 'function_call', id: 'fc_one', name: 'read', call_id: 'call_one', arguments: 'x'.repeat(64 * 1024 + 1) }],
    [{ type: 'reasoning', encrypted_content: 'PRIVATE' + 'x'.repeat(1024 * 1024) }]]) {
    await rejects(() => readProviderStream(fixture(packet(complete(output))).response), 'provider_stream_limit');
  }
});
