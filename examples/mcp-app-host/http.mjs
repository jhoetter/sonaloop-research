import { randomBytes, timingSafeEqual } from 'node:crypto';
import { ContractError } from './policy.mjs';

export function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}
export function fail(res, error) {
  json(res, error instanceof ContractError ? error.status : 503, { error: {
    code: error instanceof ContractError ? error.code : 'service_unavailable',
    message: error instanceof ContractError ? error.message : 'Der Testdienst konnte die Anfrage nicht bestätigen. Prüfe bei einer Schreibaktion zuerst den gespeicherten Stand.',
  } });
}
export async function body(req, maximumBytes = 16384) {
  if (req.headers['content-type']?.split(';')[0] !== 'application/json') throw new ContractError('json_required', 'JSON erforderlich.', 415);
  const chunks = []; let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maximumBytes) throw new ContractError('request_too_large', 'Die Anfrage ist zu groß.', 413);
    chunks.push(chunk);
  }
  try {
    const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    return value;
  } catch { throw new ContractError('invalid_json', 'Ungültige Anfrage.', 400); }
}
export function originGuard(req, origin, requireOrigin = false) {
  const expected = new URL(origin);
  if (req.headers.host !== expected.host || (req.headers.origin && req.headers.origin !== origin) ||
      (requireOrigin && req.headers.origin !== origin) || req.headers['sec-fetch-site'] === 'cross-site') {
    throw new ContractError('origin_denied', 'Diese Herkunft darf den Testdienst nicht aufrufen.', 403);
  }
}
export function createSessions() {
  const sessions = new Map();
  const name = 'mcp_app_host_session';
  function session(req, res, create = false) {
    const cookie = (req.headers.cookie || '').split(';').map(p => p.trim()).find(p => p.startsWith(`${name}=`))?.slice(name.length + 1);
    const stored = cookie ? sessions.get(cookie) : undefined;
    if (stored && stored.expires > Date.now()) return { id: cookie, ...stored };
    if (!create) throw new ContractError('session_required', 'Bitte die Testseite erneut öffnen.', 401);
    for (const [id, value] of sessions) if (value.expires < Date.now()) sessions.delete(id);
    if (sessions.size >= 100) throw new ContractError('session_limit', 'Zu viele lokale Sessions.', 429);
    const id = randomBytes(32).toString('hex');
    const value = { csrf: randomBytes(32).toString('hex'), expires: Date.now() + 4 * 60 * 60 * 1000 };
    sessions.set(id, value);
    res.setHeader('Set-Cookie', `${name}=${id}; HttpOnly; SameSite=Strict; Path=/; Max-Age=14400`);
    return { id, ...value };
  }
  function csrf(req, current) {
    const actual = req.headers['x-host-csrf'];
    if (typeof actual !== 'string' || Buffer.byteLength(actual) !== Buffer.byteLength(current.csrf) || !timingSafeEqual(Buffer.from(actual), Buffer.from(current.csrf))) {
      throw new ContractError('csrf_denied', 'Bitte die Testseite neu laden.', 403);
    }
  }
  return { session, csrf };
}
