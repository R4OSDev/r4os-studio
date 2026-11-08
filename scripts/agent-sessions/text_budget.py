"""JSON string budgets with incremental prefix accounting and tail eviction."""
from collections import deque
from session_store import encode


def content_bytes(value):
    return len(encode(value).encode()) - 2


def bounded_text(value, budget, tail=False):
    """Bound the actual JSON representation, including escaped control bytes."""
    if content_bytes(value) + 2 <= budget: return value, False
    low, high = 0, len(value)
    while low < high:
        middle = (low+high+1)//2
        candidate = value[-middle:] if tail else value[:middle]
        if content_bytes(candidate) + 2 <= budget: low = middle
        else: high = middle-1
    return (value[-low:] if tail and low else value[:low]), True


class TextBuffer:
    def __init__(self, budget, tail=False):
        self.budget = budget; self.tail = tail; self.used = 0
        self.text = ''; self.parts = deque()

    @property
    def value(self):
        return ''.join(part for part, _ in self.parts) if self.tail else self.text

    def append(self, value):
        if not value: return '', False
        size = content_bytes(value); capacity = max(0, self.budget - 2)
        if not self.tail:
            remaining = capacity - self.used
            clipped = size > remaining
            if clipped: value, _ = bounded_text(value, remaining + 2); size = content_bytes(value)
            self.text += value; self.used += size
            return value, clipped
        clipped = self.used + size > capacity
        if size > capacity:
            value, _ = bounded_text(value, self.budget, True); size = content_bytes(value)
            self.parts.clear(); self.used = 0
        self.parts.append((value, size)); self.used += size
        while self.used > capacity:
            first, cost = self.parts.popleft(); self.used -= cost
            if self.used < capacity:
                first, _ = bounded_text(first, capacity - self.used + 2, True)
                cost = content_bytes(first); self.parts.appendleft((first, cost)); self.used += cost
        return value, clipped
