import { surfaceError, validateSurface } from './persona-contract.js';

// Shared adapter mechanics: native authority stays in the service. The only
// local operation state is a pending ID for explicit read-only recovery.
export function createPersonaActions({ read, invoke, inspect, unpack }) {
  let current, pending, active = false;
  async function accept(response) {
    const result = await unpack(response);
    validateSurface(result.value, current);
    current = result.value;
    return result;
  }
  async function write(action, fields) {
    if (active || pending) throw surfaceError({ code: 'in_progress', message: 'Check the previous operation before starting another.' });
    if (!current) throw surfaceError({ code: 'invalid_response' });
    const operation = crypto.randomUUID();
    pending = operation; active = true;
    try {
      const response = await invoke(action, { ...fields, operation_id: operation, expected_version: current.version });
      const result = await accept(response); pending = undefined; return result;
    } catch (error) {
      if (['validation','not_found','forbidden','conflict','operation_mismatch','provider_unavailable','provider_error','action_cancelled'].includes(error.code)) pending = undefined;
      if (pending && !['in_progress','outcome_unknown'].includes(error.code)) throw surfaceError({ code: 'outcome_unknown', message: error.message, operation_id: pending });
      throw error;
    } finally { active = false; }
  }
  return {
    accept,
    update: changes => write('update', { changes }),
    generateAvatar: prompt => write('generate_avatar', { prompt }),
    async refresh() {
      if (active) throw surfaceError({ code: 'in_progress' });
      if (pending) {
        const operation = await inspect(pending);
        if (['in_progress','outcome_unknown'].includes(operation.status)) throw surfaceError({ code: operation.status, message: operation.error?.message || 'The operation has not been confirmed.', operation_id: pending });
        if (!['succeeded','failed','conflict'].includes(operation.status)) throw surfaceError({ code: 'outcome_unknown', operation_id: pending });
        pending = undefined;
      }
      return accept(await read(current.persona_id));
    },
    get value() { return current; },
  };
}
