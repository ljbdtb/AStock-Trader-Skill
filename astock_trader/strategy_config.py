from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=1)
def strategy_config():
    path = Path(__file__).resolve().parent.parent / "config" / "strategy.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))
