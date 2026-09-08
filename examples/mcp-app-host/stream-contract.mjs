/** Customer-owned host transport. No product fields or execution authority live here.
 * POST /api/host/chat with Accept: text/event-stream:
 *   new: {message, sessionId?, clientTurnId}; resume: {sessionId, turnId, approved:{id,accepted}}
 * Every SSE data object contains {schemaVersion,seq,sessionId,turnId,type}.
 * - turn.started: {clientTurnId}
 * - text.delta: {partId,delta}
 * - tool.state: {partId,name,state,arguments?,approval?,call?,error?}
 * - turn.paused: {approval:{id,name,arguments,partId}}
 * - turn.finished: {status:'completed'|'stopped'|'failed',error?,responseId?,usage?}
 * A paused stream ends; approval continuation uses the same turn and part identities.
 * call is the existing owner-bound MCP call/resource grant, including app-only result
 * metadata. It is never provider input. SSE comments are transport heartbeats only.
 * GET /api/host/chat/turns/:turnId returns an owner-bound snapshot with
 * {schemaVersion,sessionId,turnId,clientTurnId,status,seq,parts,error?,toolInFlight}.
 * Parts are {kind:'text',id,text} or {kind:'tool',id,name,state,...toolStateFields}.
 * GET /api/host/chat/requests/:clientTurnId returns the same snapshot for this
 * cookie owner when turn.started was lost. It never starts/repeats a request.
 * Unknown and other-owner request IDs both return turn_missing (404). A 404
 * alone is not evidence that an earlier network request cannot still be admitted.
 * POST /api/host/chat/stop {sessionId,turnId} returns
 * {sessionId,turnId,status,toolInFlight}. Stop fences future dispatches; already
 * admitted native operations retain their actual result or unknown outcome.
 * Repeating a clientTurnId replays its events and never repeats its operations.
 * Existing callers without the SSE Accept header retain the legacy JSON shape.
 */
export const STREAM_SCHEMA_VERSION = 'customer_agent_stream.v1';
export const TURN_SCHEMA_VERSION = 'customer_agent_turn.v1';
export const TOOL_STATES = Object.freeze(['preparing', 'approval_required', 'running', 'completed', 'failed', 'denied', 'outcome_unknown']);
export const TURN_STATUSES = Object.freeze(['running', 'waiting_approval', 'stopping', 'completed', 'stopped', 'failed']);
