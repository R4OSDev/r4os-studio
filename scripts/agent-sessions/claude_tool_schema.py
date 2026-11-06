"""Claude wire hints; canonical tool schemas remain the admission authority."""
from copy import deepcopy
import base64
import re

from model_transport import ModelFault, dumps, loads


def input_schema(schema):
    result = deepcopy(schema)
    combinators = [key for key in ('oneOf', 'allOf', 'anyOf') if key in result]
    if not combinators:
        return result
    variants = result.get('oneOf')
    properties = result.get('properties')
    if (combinators != ['oneOf'] or result.get('type') != 'object'
            or not isinstance(properties, dict) or not isinstance(variants, list) or not variants
            or any(not isinstance(part, dict) or part.get('type') != 'object'
                   or part.get('additionalProperties') is not False
                   or not isinstance(part.get('properties', {}), dict)
                   or not set(part.get('properties', {})).issubset(properties) for part in variants)):
        raise ModelFault('model_tool_schema_unavailable', not_dispatched=True)
    # The provider rejects composition at the root. Keep the already exposed
    # field envelope and describe every original variant without changing the
    # argument shape, call identity or canonical whole-batch validation.
    del result['oneOf']
    result['additionalProperties'] = False
    result['description'] = (result.get('description', '') + '\nOriginal input variants: exactly one must match. '
        'Studio validates these original constraints before executing any tool:\n' + dumps(variants)).lstrip()
    return result


def rejected(status, details):
    if (status != 400 or not isinstance(details, dict) or details.get('httpResponseComplete') is not True
            or details.get('bodyTruncated') or not isinstance(details.get('providerBodyBase64'), str)
            or len(details['providerBodyBase64']) > 87384):
        return False
    try:
        raw = base64.b64decode(details['providerBodyBase64'], validate=True)
        if len(raw) > 65536: return False
        value = loads(raw.decode()); error = value.get('error', {})
        return bool(value.get('type') == 'error' and error.get('type') == 'invalid_request_error'
            and isinstance(error.get('message'), str) and re.fullmatch(
                r'tools\.\d{1,4}(?:\.custom)?\.input_schema: input_schema does not support oneOf, allOf, or anyOf at the top level',
                error['message']))
    except (ValueError, UnicodeError, ModelFault, AttributeError):
        return False
