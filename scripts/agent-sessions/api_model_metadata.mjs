/** Bounded public model facts; no inference and no capability guesses from IDs. */
export function modelFacts(entry, binding, key) {
  function safeString(value, maximum) {
    if (typeof value !== 'string' || !value.length || value.length > maximum || /[\ud800-\udfff]/u.test(value)) return null;
    for (const char of value) if (char.codePointAt(0) < 32 || char.codePointAt(0) === 127) return null;
    if (typeof key === 'string' && value.includes(key)) return null;
    return value;
  }
  const tokens = value => Number.isSafeInteger(value) && value > 0 && value <= 2147483647 ? value : null;
  function model(entry) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
    const id = safeString(entry.id, 200); if (!id || [...id].some(char => /\s/u.test(char))) return null;
    const capabilities = Object.fromEntries(['text', 'functionTools', 'streaming', 'imageInput', 'reasoning', 'webSearch', 'imageGeneration', 'goals'].map(field => [field, 'unknown']));
    let contextWindow = null, maxOutputTokens = null, name = id;
    let reasoning, efforts = [], defaultEffort = null;
    // OpenRouter's published model schema supplies these facts. Generic Models
    // IDs alone establish no context/tool/reasoning or modality capabilities.
    if (binding.kind === 'openrouter') {
      name = safeString(entry.name, 200) ?? id;
      contextWindow = tokens(entry.context_length); maxOutputTokens = tokens(entry.top_provider?.max_completion_tokens);
      const modalities = entry.architecture?.input_modalities, outputs = entry.architecture?.output_modalities;
      if (Array.isArray(modalities) && modalities.every(value => typeof value === 'string')) {
        if (Array.isArray(outputs) && outputs.every(value => typeof value === 'string')) capabilities.text = modalities.includes('text') && outputs.includes('text') ? 'supported' : 'unsupported';
        capabilities.imageInput = modalities.includes('image') ? 'supported' : 'unsupported';
      }
      const parameters = entry.supported_parameters;
      if (Array.isArray(parameters) && parameters.length <= 128 && parameters.every(value => typeof value === 'string')) {
        capabilities.functionTools = parameters.includes('tools') && parameters.includes('tool_choice') ? 'supported' : 'unsupported';
        capabilities.reasoning = parameters.some(value => ['reasoning', 'reasoning_effort', 'include_reasoning'].includes(value)) ? 'supported' : 'unsupported';
      }
      if (entry.reasoning != null) {
        if (typeof entry.reasoning !== 'object' || Array.isArray(entry.reasoning)) return null;
        reasoning = {};
        const levels = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];
        for (const field of ['mandatory', 'default_enabled']) if (field in entry.reasoning) {
          if (typeof entry.reasoning[field] !== 'boolean') return null;
          reasoning[field] = entry.reasoning[field];
        }
        if ('supported_efforts' in entry.reasoning) {
          const values = entry.reasoning.supported_efforts;
          if (values !== null && (!Array.isArray(values) || values.length > levels.length
            || values.some(value => !levels.includes(value)) || new Set(values).size !== values.length)) return null;
          reasoning.supported_efforts = values;
          efforts = values === null ? [...levels] : [...values];
        }
        if ('default_effort' in entry.reasoning) {
          const value = entry.reasoning.default_effort;
          if (value !== null && !levels.includes(value)) return null;
          reasoning.default_effort = value;
        }
        if (reasoning.mandatory === true) {
          if (reasoning.default_effort === 'none' || reasoning.default_enabled === false) return null;
          efforts = efforts.filter(value => value !== 'none');
        }
        defaultEffort = reasoning.default_enabled !== false && efforts.includes(reasoning.default_effort) ? reasoning.default_effort : '';
        if (!defaultEffort) efforts.unshift(''); // Provider default: no wire effort, never implicit none.
        capabilities.reasoning = 'supported';
      }
      capabilities.streaming = 'supported'; // Published endpoint-level streaming contract.
    }
    return { id, name, contextWindow, maxOutputTokens, capabilities, efforts, defaultEffort, ...(reasoning ? { reasoning } : {}) };
  }
  return model(entry);
}
