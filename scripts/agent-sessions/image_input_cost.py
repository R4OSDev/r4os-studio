"""Versioned image estimates for qualified direct OpenAI vision input."""
from input_budget import raster_dimensions, raster_reserve


PATCH_MODELS = {'gpt-4.1-mini-2025-04-14': 162, 'gpt-5.2': 120}
DETAILS = ('low', 'high', 'auto')


class ImageCost:
    def __init__(self, binding):
        self.multiplier = PATCH_MODELS.get(binding.get('model')) if (
            binding.get('kind') == 'openai-compatible' and binding.get('baseUrl') == 'https://api.openai.com/v1'
            and binding.get('protocol') in ('responses', 'chat-completions')
            and binding.get('imageInput') == 'supported' and not binding.get('imageAction')) else None
        self.qualified = 0
        self.conservative = 0

    def __call__(self, data, mime, detail):
        width, height = raster_dimensions(data, mime)
        if self.multiplier is not None and detail in DETAILS and max(width, height) <= 2048:
            patches = ((width + 31) // 32) * ((height + 31) // 32)
            # No provider resize is required within these documented bounds.
            if patches <= 6144:
                self.qualified += 1
                return (patches * self.multiplier + 99) // 100
        self.conservative += 1
        return raster_reserve(width, height)

    def provenance(self):
        return {'version': 1, 'qualifiedImages': self.qualified, 'conservativeImages': self.conservative,
                'profile': 'openai-patches-32-v1' if self.qualified else None}
