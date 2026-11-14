from engines.bing import BingEngine
from engines.brave import BraveEngine
from engines.duckduckgo import DuckDuckGoEngine
from engines.registry import get_engine, list_engines, register_engine
from engines.so360 import So360Engine
from engines.so_qq import SoQQEngine

register_engine(SoQQEngine())
register_engine(BingEngine())
register_engine(So360Engine())
register_engine(BraveEngine())
register_engine(DuckDuckGoEngine())

__all__ = ["get_engine", "list_engines", "register_engine"]
