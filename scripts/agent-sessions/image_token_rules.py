"""Image input rules bound to the provider routes that use them."""
from math import isqrt


CODEX_HIGH_EDGE = {
    'gpt-6.1-sol': 65535, 'gpt-6-astra': 65535, 'gpt-6.1-terra': 65535,
    'gpt-6-sol': 65535, 'gpt-6-luna': 65535,
    'gpt-5.6-sol': 2048, 'gpt-5.6-terra': 2048, 'gpt-5.6-luna': 2048,
    'gpt-daybreak-blue-latest': 2048,
}
CLAUDE_STANDARD = frozenset((
    'claude-sonnet-4-6', 'claude-opus-4-6', 'claude-opus-4-5-20251101',
    'claude-haiku-4-5-20251001', 'claude-sonnet-4-5-20250929',
))
CLAUDE_HIGH = frozenset((
    'claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-fable-5-1',
    'claude-opus-5', 'claude-sonnet-5', 'claude-fable-5', 'claude-opus-4-8', 'claude-opus-4-7',
))


def grid(width, height, patch):
    return ((width + patch - 1) // patch) * ((height + patch - 1) // patch)


def codex_tokens(model, width, height, detail):
    """Effective image input, including its separator, observed on Codex."""
    edge = CODEX_HIGH_EDGE.get(model)
    if edge is None:
        return None
    if detail == 'low':
        edge = 512
    elif detail in ('auto', 'original'):
        edge = 65535
    elif detail != 'high':
        return None
    longer = max(width, height)
    if longer > edge:
        width = max(1, (width * edge + longer // 2) // longer)
        height = max(1, (height * edge + longer // 2) // longer)
    patches = grid(width, height, 32)
    if detail == 'high' and patches > 2500:
        # Fit the documented proportional patch budget without a floating
        # point error at exact multiples of 32.
        wide = isqrt(2500 * width // height)
        tall = isqrt(2500 * height // width)
        if wide * height <= tall * width:
            width, height = wide * 32, wide * 32 * height // width
        else:
            width, height = tall * 32 * width // height, tall * 32
        patches = grid(width, height, 32)
    if patches > 30000:
        return None
    return patches * 6 // 5 + 1


def claude_tokens(model, width, height, detail):
    """Use the largest aspect-preserving size that fits the model's tier."""
    if detail != 'auto':
        return None
    if model in CLAUDE_HIGH:
        edge, maximum = 2576, 4784
    elif model in CLAUDE_STANDARD:
        edge, maximum = 1568, 1568
    else:
        return None
    long, short = max(width, height), min(width, height)
    tokens = grid(long, short, 28)
    if long <= edge and tokens <= maximum:
        return tokens
    ratio = long / short
    low, high = 1, min(long, edge)
    while low < high:
        middle = (low + high + 1) // 2
        if grid(middle, max(1, round(middle / ratio)), 28) <= maximum:
            low = middle
        else:
            high = middle - 1
    return grid(low, max(1, round(low / ratio)), 28)


def rule_for(binding):
    if (binding.get('kind') == 'codex-subscription' and binding.get('protocol') == 'responses'
            and binding.get('baseUrl') == 'https://chatgpt.com/backend-api/codex'
            and not binding.get('imageAction')):
        return 'codex-vision-32-v1', codex_tokens
    if (binding.get('kind') == 'claude-plan' and binding.get('protocol') == 'messages'
            and binding.get('baseUrl') == 'https://api.anthropic.com/v1'):
        return 'claude-vision-28-v1', claude_tokens
    return None
