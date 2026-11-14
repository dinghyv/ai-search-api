from abc import ABC, abstractmethod


class SearchEngine(ABC):
    name: str = ""
    label: str = ""
    description: str = ""
    config_key: str = ""  # 若需要外部 API Key（如 brave_api_key），填写对应 settings key

    @abstractmethod
    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        include_ai: bool = True,
        include_media: bool = True,
        raw: bool = False,
    ) -> dict:
        """执行搜索并返回统一格式的 JSON 字典。"""
        raise NotImplementedError
