"""Release-bound Exchange limits shared with the offline VM exporter."""
import json
from pathlib import Path

CONTRACT = json.loads((Path(__file__).resolve().parents[2] / 'shared/exchange-host.json').read_text())
EXCHANGE_LIMITS = CONTRACT['limits']
