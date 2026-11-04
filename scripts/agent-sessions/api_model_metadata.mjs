/** Bounded public model facts; no inference and no capability guesses from IDs. */
import { readFileSync } from 'node:fs';
const zaiDocuments = JSON.parse(readFileSync(new URL('../../shared/zai-models.json', import.meta.url), 'utf8'));
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
    if (binding.kind === 'zai-coding-plan') {
      const documented = zaiDocuments.models.find(model => model.facts.id === id);
      if (documented) return structuredClone(documented.facts);
    }
    const capabilities = Object.fromEntries(['text', 'functionTools', 'streaming', 'imageInput', 'reasoning', 'webSearch', 'imageGeneration', 'goals'].map(field => [field, 'unknown']));
    let contextWindow = null, maxOutputTokens = null, name = id;
    let reasoning, efforts = [], defaultEffort = null;
    // OpenRouter's published model schema supplies these facts. Generic Models
    // IDs alone establish no context/tool/reasoning or modality capabilities.
    if (['chatgpt-plan','codex-subscription'].includes(binding.kind)) {
      if (entry.visibility !== 'list' || entry.supported_in_api !== true) return null;
      name = safeString(entry.display_name, 200) ?? id;
      contextWindow = tokens(entry.context_window); maxOutputTokens = tokens(entry.max_output_tokens);
      // The account Responses contract supports text, streamed output
      // and custom function tools. Display/account eligibility comes from this
      // account's own catalog; no ID or local binary selects a model.
      capabilities.text = capabilities.functionTools = capabilities.streaming = 'supported';
      if (Array.isArray(entry.input_modalities)) capabilities.imageInput = entry.input_modalities.includes('image') ? 'supported' : 'unsupported';
      const levels = entry.supported_reasoning_levels;
      if (Array.isArray(levels) && levels.length<=32 && levels.every(v => v && safeString(v.effort,30))) {
        // This account catalog also describes native orchestration modes (for
        // example automatic delegation). Keep its documented Responses effort
        // values without rejecting the model because it offers another mode.
        efforts = [...new Set(levels.map(v=>v.effort).filter(v=>['none','minimal','low','medium','high','xhigh','max'].includes(v)))];
        defaultEffort = efforts.includes(entry.default_reasoning_level) ? entry.default_reasoning_level : null;
        capabilities.reasoning = !efforts.length ? 'unknown' : efforts.some(v=>v!=='none') ? 'supported' : 'unsupported';
      }
    }
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

/** Retain explicitly configured IDs even when the public catalog is truncated. */
export function modelCatalog(entries, binding, key, modelIds = []) {
  if (!Array.isArray(entries) || !Array.isArray(modelIds) || modelIds.length > 320
    || modelIds.some(value => typeof value !== 'string' || value.length > 200)) throw Error('Invalid model catalog');
  if(['chatgpt-plan','codex-subscription'].includes(binding.kind))entries=entries.map(v=>({...v,id:v.slug}));
  const wanted = new Set(modelIds), preferred = [], remaining = [];
  for (const entry of entries) {
    if (wanted.has(entry?.id)) preferred.push(entry);
    else if (remaining.length < 256) remaining.push(entry);
    if (preferred.length > 320) throw Error('Duplicate configured model');
  }
  const seen = new Set(), models = [];
  for (const entry of [...preferred, ...remaining].slice(0,256)) {
    const current = modelFacts(entry,binding,key); if (!current) continue;
    if (seen.has(current.id)) throw Error('Duplicate model');
    seen.add(current.id); models.push(current);
  }
  return { models, truncated: entries.length > 256 };
}
