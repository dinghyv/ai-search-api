from engines.base import SearchEngine

_ENGINES: dict[str, SearchEngine] = {}


def register_engine(engine: SearchEngine):
    _ENGINES[engine.name] = engine


def get_engine(name: str) -> SearchEngine:
    key = (name or "").strip().lower()
    if key not in _ENGINES:
        available = ", ".join(_ENGINES.keys())
        raise ValueError(f"Unknown search engine '{name}'. Available: {available}")
    return _ENGINES[key]


def list_engines() -> list[dict]:
    return [
        {
            "name": e.name,
            "label": e.label,
            "description": e.description,
            "config_key": e.config_key or None,
        }
        for e in _ENGINES.values()
    ]
