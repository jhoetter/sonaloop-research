// Authored surface values only: no profile copy, native call, private metadata or media.
import { stableJSON } from '../../../sonaloop/web/assets/persona-view/persona-contract.js';
import { validatePersonaProps } from '../../../sonaloop/web/assets/persona-view/persona-public-props.js';

export const PERSONA_COMPONENT_SCENARIO = 'persona-component-readonly-placeholder';

export function personaPublicProps() {
  return validatePersonaProps({ locale: 'en', value: {
    schema_version: 'sonaloop.persona-surface.v1', persona_id: 'persona_component_fixture',
    slug: 'mira-component-fixture', version: 'fixture-version-1',
    fields: { display_name: 'Mira Chen', age: '35–44', location: 'Berlin', role_title: 'Operations coordinator',
      goals: ['Make shift handovers clear'], pain_points: ['Ownership gets lost between shifts'],
      portrait_description: 'A fictional adult persona. No portrait image is supplied.' },
    avatar: { state: 'missing', sha256: null, generated_at: null, profile_version: null },
    capabilities: { edit: [], generate_avatar: false, reasons: ['Read-only synthetic component example.'] },
    warnings: ['Synthetic example, not research evidence.'],
  } });
}

export function personaComponentScenario() {
  const props = personaPublicProps();
  return { scenario: PERSONA_COMPONENT_SCENARIO, state: 'ready', tool: 'get_persona_surface', props,
    input: { persona_id: props.value.persona_id }, result: {
      content: [{ type: 'text', text: stableJSON(props.value) }], structuredContent: structuredClone(props.value),
    } };
}
