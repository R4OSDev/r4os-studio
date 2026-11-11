"""Resolution-aware image estimates for direct provider input."""
from input_budget import raster_dimensions, raster_reserve


PATCH_MODELS = {'gpt-4.1-mini-2025-04-14': 162, 'gpt-5.2': 120}
DETAILS = ('low', 'high', 'auto')
DEFAULT_IMAGE_TOKENS = 5000


def patches(width, height):
    return ((width+31)//32)*((height+31)//32)


class ImageCost:
    def __init__(self, binding, *, history=None, use_history=False):
        self.multiplier = PATCH_MODELS.get(binding.get('model')) if (
            binding.get('kind') == 'openai-compatible' and binding.get('baseUrl') == 'https://api.openai.com/v1'
            and binding.get('protocol') in ('responses', 'chat-completions')
            and binding.get('imageInput') == 'supported' and not binding.get('imageAction')) else None
        self.qualified = 0
        self.conservative = 0
        self.historical = 0
        self.use_history = use_history
        self.samples = []
        if use_history and history:
            from image_usage import scope
            if scope(binding)==history.get('bindingSha256'):
                self.samples = [sample for sample in history.get('samples',[]) if
                    isinstance(sample,list) and len(sample)==4 and isinstance(sample[2],str)
                    and all(type(sample[i]) is int and sample[i]>0 for i in (0,1,3))]

    def __call__(self, data, mime, detail):
        width, height = raster_dimensions(data, mime)
        same_detail = [s for s in self.samples if s[2]==detail]
        area = patches(width,height)
        if same_detail:
            w,h,_,tokens=min(same_detail,key=lambda s: (
                abs(s[0]-width)/max(s[0],width)+abs(s[1]-height)/max(s[1],height),-s[3]/patches(s[0],s[1])))
            self.historical += 1
            original = patches(w,h)
            return (tokens*area+original-1)//original
        if self.multiplier is not None and detail in DETAILS and max(width, height) <= 2048:
            # No provider resize is required within these documented bounds.
            if area <= 6144:
                self.qualified += 1
                return (area * self.multiplier + 99) // 100
        self.conservative += 1
        return DEFAULT_IMAGE_TOKENS if self.use_history else raster_reserve(width, height)

    def provenance(self):
        return {'version': 2 if self.use_history else 1,
                'qualifiedImages': self.qualified, 'conservativeImages': self.conservative,
                'profile': 'openai-patches-32-v1' if self.qualified else None,
                **({'historicalImages':self.historical} if self.use_history else {})}
