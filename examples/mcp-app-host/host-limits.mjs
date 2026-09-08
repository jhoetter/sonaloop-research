// Generic host budgets. A valid 8 MiB binary MCP attachment expands to about
// 10.67 MiB in base64; leave room for the enclosing result and JSON-RPC frame.
export const MAX_RETAINED_CALL_BYTES = 12 * 1024 * 1024;
export const MAX_RETAINED_CALL_TOTAL_BYTES = 48 * 1024 * 1024;
export const MAX_MCP_STDIO_BUFFER_BYTES = 16 * 1024 * 1024;
export const MAX_PROGRESS_EVENT_BYTES = 8 * 1024 * 1024;
export const MAX_STREAM_PENDING_EVENTS = 33024;
