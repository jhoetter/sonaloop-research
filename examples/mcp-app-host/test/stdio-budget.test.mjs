import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { MAX_MCP_STDIO_BUFFER_BYTES } from '../host-limits.mjs';

// A synthetic JSON-RPC peer: no MCP data, provider, environment lookup or filesystem.
const childScript = `
const bytes = Number(process.argv[1]);
process.stdin.once('data', () => {
  process.stdout.write(JSON.stringify({jsonrpc:'2.0', id:1,
    result:{content:[], _meta:{syntheticPayload:'x'.repeat(bytes)}}}) + '\\n');
});
process.stdin.resume();
`;
const sha = text => createHash('sha256').update(text).digest('hex');
async function within(promise, milliseconds) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Synthetic stdio fixture timed out')), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}

async function withTransport(payloadBytes, verify) {
  const received = Promise.withResolvers(), closed = Promise.withResolvers();
  // Transport setup can fail before the response is awaited.
  void received.promise.catch(() => {});
  let didClose = false, childPid, stderrBytes = 0;
  const transport = new StdioClientTransport({
    command: process.execPath, args: ['-e', childScript, String(payloadBytes)],
    stderr: 'pipe', env: {}, maxBufferSize: MAX_MCP_STDIO_BUFFER_BYTES,
  });
  transport.onmessage = message => received.resolve(message);
  transport.onerror = error => received.reject(error);
  transport.onclose = () => { didClose = true; closed.resolve(); };
  transport.stderr.on('data', chunk => { stderrBytes += chunk.byteLength; });
  try {
    await transport.start();
    childPid = transport.pid;
    assert.ok(Number.isInteger(childPid));
    await transport.send({ jsonrpc: '2.0', id: 1, method: 'synthetic_fixture' });
    await verify(within(received.promise, 10000));
  } finally {
    try {
      await transport.close();
      if (childPid && !didClose) await within(closed.promise, 2000);
    } finally {
      if (childPid && !didClose) {
        try { process.kill(childPid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
        await within(closed.promise, 2000);
      }
    }
    if (childPid) assert.equal(didClose, true, 'Synthetic child must be reaped');
    assert.equal(stderrBytes, 0, 'Synthetic child must produce no diagnostics');
  }
}

test('16 MiB stdio transport preserves an 8 MiB PNG-sized base64 response above the old 10 MiB limit', { timeout: 20000 }, async () => {
  const payloadBytes = Math.ceil(8 * 1024 * 1024 / 3) * 4;
  assert.ok(payloadBytes > 10 * 1024 * 1024);
  await withTransport(payloadBytes, async pending => {
    const message = await pending;
    assert.equal(message.jsonrpc, '2.0');
    assert.equal(message.id, 1);
    assert.deepEqual(message.result.content, []);
    assert.equal(Buffer.byteLength(message.result._meta.syntheticPayload), payloadBytes);
    assert.equal(sha(message.result._meta.syntheticPayload), sha('x'.repeat(payloadBytes)));
  });
});

test('stdio transport rejects a JSON-RPC response above its 16 MiB budget and closes the child', { timeout: 20000 }, async () => {
  await withTransport(MAX_MCP_STDIO_BUFFER_BYTES + 1024, async pending => {
    await assert.rejects(pending, error => {
      assert.equal(error.message, `ReadBuffer exceeded maximum size of ${MAX_MCP_STDIO_BUFFER_BYTES} bytes`);
      return true;
    });
  });
});
