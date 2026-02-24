import asyncio
from functools import partial
from typing import Any, List

from impl._spiders.genshin.other_json_data import ZH_LANG_MAP
from impl.assets_utils.logger import logs
from impl.core._abstract_spider import BaseSpider
from impl.core.file_manager import FileManager
from impl.models.base import BaseWikiModel, IconAsset, IconAssetUrl
from impl.models.enums import Game, DataType
from impl.models.genshin.beyond_item import BeyondItem


class HutaoBeyondSpider(BaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.BEYOND_ITEM
    data_source: str = "hutao"
    file_type: str = "json"

    url = "https://api.snaphutaorp.org/static/raw/BeyondItemIcon"

    def __init__(self):
        super().__init__()
        self.save_path = partial(
            FileManager.get_raw_icon_path, game=self.game, data_type=DataType.OTHER, data_source="data"
        )
        self.excel_config_path = self.save_path("BydMaterialExcelConfigData.json")
        self.excel_config_data = None
        self.items = []
        self.key = ""

    async def load_excel_config(self):
        self.excel_config_data = await FileManager.load_json(self.excel_config_path)

    def get_icon_url(self, name: str) -> List[str]:
        return [f"{self.url}/{name}.png"]

    async def get_icon_by_name(self, name: str) -> IconAsset | None:
        u_list = self.get_icon_url(name)
        for u in u_list:
            try:
                p = await self._download_file(u)
            except Exception as e:
                logs.info(f"下载图片失败：{name} {e}")
                continue
            ext = FileManager.get_file_ext(p)[1:].lower()
            i = IconAsset()
            j = IconAssetUrl(url=u, path=str(p))
            setattr(i, ext, j)
            return i
        return None

    def get_item_type_key(self, data: dict[str, Any]) -> str:
        if self.key:
            return self.key
        for k, v in data.items():
            if isinstance(v, str) and v.startswith("BEYOND_"):
                self.key = k
        return self.key

    async def parse_excel_config_single(self, data: dict[str, Any]) -> BeyondItem:
        name = ZH_LANG_MAP.get(str(data["nameTextMapHash"]), "")
        desc = ZH_LANG_MAP.get(str(data["descTextMapHash"]), "")
        item_type = data[self.get_item_type_key(data)]
        item = BeyondItem(
            id=data["id"],
            name=name,
            en_name="",
            rank=data["rankLevel"],
            desc=desc,
            item_type=item_type,
            icon=None,
        )
        if icon := data["icon"]:
            if item_type != "BEYOND_MATERIAL_HALL_UNLOCK":
                try:
                    item.icon = await self.get_icon_by_name(icon)
                except Exception as e:
                    logs.info(f"获取图标失败：{icon} {e}")
        self.items.append(item)
        return item

    async def parse_excel_config_single_try(self, data: dict[str, Any]) -> BeyondItem | None:
        try:
            return await self.parse_excel_config_single(data)
        except Exception as e:
            logs.info(f"解析数据失败：{data['id']} {e}")

    async def parse_excel_config(self) -> list[BeyondItem]:
        tasks = []
        for data in self.excel_config_data:
            tasks.append(self.parse_excel_config_single_try(data))
            if len(tasks) >= 10:
                await asyncio.gather(*tasks)
                tasks.clear()
        if tasks:
            await asyncio.gather(*tasks)
            tasks.clear()
        return self.items

    async def start_crawl(self) -> List[BaseWikiModel]:
        await self.load_excel_config()
        return await self.parse_excel_config()
