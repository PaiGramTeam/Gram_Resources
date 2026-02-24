import abc
import traceback
from typing import List, Dict, Any

from impl.assets_utils.logger import logs
from impl.core._abstract_spider import BaseSpider
from impl.models.base import BaseWikiModel


class AmbrBaseSpider(BaseSpider):
    data_source: str = "ambr"
    file_type: str = "json"
    priority: int = 90
    url = "https://gi.yatta.moe/api/v2/chs/avatar"

    async def start_crawl(self) -> List[BaseWikiModel]:
        req, _ = await self._request("GET", self.url + "?vh=90F0")
        data = req.json()
        d = []
        tasks = []
        for i in data.get("data", {}).get("items", {}).values():
            tasks.append(self._parse_content(i))
            if len(tasks) > 10:
                t = await self.gather_tasks(tasks)
                d.extend([j for sublist in t for j in sublist if j])
        if tasks:
            t = await self.gather_tasks(tasks)
            d.extend([j for sublist in t for j in sublist if j])
        return d

    @staticmethod
    def get_icon_url(filename: str, ext: str) -> list[str]:
        return [f"https://enka.network/ui/{filename}.{ext}", f"https://gi.yatta.moe/assets/UI/{filename}.{ext}"]

    async def _parse_content(self, data: Dict[str, Any]) -> list[BaseWikiModel]:
        try:
            return await self.parse_content(data)
        except Exception as e:
            traceback.print_exc()
            logs.info(f"解析数据失败: {e}")
            return []

    @abc.abstractmethod
    async def parse_content(self, data: Dict[str, Any]) -> list[BaseWikiModel]:
        """
        解析数据
        :param data:
        :return:
        """
