import asyncio
import traceback
from enum import StrEnum
from typing import Any, Dict, Optional

from impl._spiders.nanoka import NanokaBaseSpider, build_data_url, get_nanoka_version
from impl.assets_utils.logger import logs
from impl.models.base import BaseWikiModel, IconAsset, IconAssetUrl
from impl.models.enums import DataType, Game
from impl.models.genshin.artifact import Artifact
from impl.models.genshin.beyond_item import BeyondItem
from impl.models.genshin.character import Character
from impl.models.genshin.enums import Element
from impl.models.genshin.weapon import Weapon


class GIElement(StrEnum):
    """nanoka 数据中的元素字段映射。

    nanoka/hakush 等数据源对元素的命名与游戏内部 ``Element`` 枚举不同，
    这里建立映射表用于转换。
    """

    HYDRO = "Hydro"
    PYRO = "Pyro"
    CRYO = "Cryo"
    ELECTRO = "Electro"
    ANEMO = "Anemo"
    GEO = "Geo"
    DENDRO = "Dendro"


async def _download_icons(
    spider: NanokaBaseSpider,
    target: BaseWikiModel,
    name_map: Dict[str, tuple],
    ignore_ids: Optional[set] = None,
) -> None:
    """统一处理图标的下载与赋值。

    Args:
        spider: 当前爬虫实例，用于调用 ``_download_file``。
        target: 数据模型实例，下载好的图标会被设置回对应属性。
        name_map: ``{属性名: (文件名, 扩展名)}`` 的映射。
        ignore_ids: 忽略下载失败日志的 ID 集合，避免无意义的告警刷屏。
    """
    ignore_ids = ignore_ids or set()
    for attr, value in name_map.items():
        filename, ext = value
        if not filename:
            continue
        url = spider.get_icon_url(filename, ext)
        try:
            path = await spider._download_file(url)
        except Exception as exc:
            if str(getattr(target, "id", "")) not in ignore_ids:
                logs.info(f"nanoka 下载图片失败：{target} {exc}")
            continue
        icon_asset = IconAsset()
        icon_url = IconAssetUrl(url=url, path=str(path))
        setattr(icon_asset, ext, icon_url)
        setattr(target, attr, icon_asset)


class NanokaCharacterSpider(NanokaBaseSpider):
    """nanoka 角色爬虫，数据源 ``<base>/gi/<ver>/character.json``。"""

    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.CHARACTER
    data_path: str = "character.json"

    @staticmethod
    def get_game_name(icon: str) -> str:
        """从 ``icon`` 字段提取出游戏内部使用的角色名片段。"""
        return icon.replace("UI_AvatarIcon_", "")

    @staticmethod
    def game_name_map(game_name: str) -> Dict[str, tuple]:
        """生成角色相关的图标资源名映射。"""
        return {
            "icon": (f"UI_AvatarIcon_{game_name}", "webp"),
            "side": (f"UI_AvatarIcon_Side_{game_name}", "webp"),
            "gacha": (f"UI_Gacha_AvatarImg_{game_name}", "webp"),
            "gacha_card": (f"UI_AvatarIcon_{game_name}_Card", "webp"),
        }

    @staticmethod
    def get_character_data(key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """将 nanoka 原始数据转换为 ``Character`` 模型字段。"""
        if "-" in key:
            # 旅行者按元素拆分为多个独立 ID
            real_id, _ = key.split("-")
            ele = str(data.get("element", "")).lower()
            key = f"{real_id}-{ele}"
        rank = {"QUALITY_ORANGE": 5, "QUALITY_PURPLE": 4}.get(data.get("rank"))
        try:
            element = getattr(Element, GIElement(data["element"]).name)
        except (KeyError, ValueError):
            element = None
        return {
            "id": key,
            "name": data.get("zh") or data.get("en") or "",
            "en_name": data.get("en", ""),
            "rank": rank,
            "element": element,
            "weapon_type": data.get("weapon", ""),
            "body_type": "",
            "birthday": {
                "month": data.get("birth", [0, 0])[0],
                "day": data.get("birth", [0, 0])[1],
            },
            "association": "其它",
        }

    async def parse_content(self, key: str, data: Dict[str, Any]) -> Optional[BaseWikiModel]:
        c_data = self.get_character_data(key, data)
        game_name = self.get_game_name(data.get("icon", ""))
        # 第三人称射击旅行者特殊处理：跳过
        if str(c_data["id"]) in {"10000134", "10000135"}:
            logs.info(f"nanoka 跳过第三人称射击旅行者角色：{c_data}")
            return None
        # 旅行者特殊处理：固定 5 星
        if (
            str(c_data["id"]).startswith("10000117-")
            or str(c_data["id"]).startswith("10000118-")
            or c_data["id"] == "10000062"
        ):
            c_data["rank"] = 5
            c_data["birthday"] = {"month": 0, "day": 0}
        if c_data.get("rank") is None:
            logs.info(f"nanoka 跳过异常角色：{c_data}")
            return None
        character = Character.model_validate(c_data)
        await _download_icons(self, character, self.game_name_map(game_name))
        return character


class NanokaWeaponSpider(NanokaBaseSpider):
    """nanoka 武器爬虫，数据源 ``<base>/gi/<ver>/weapon.json``。"""

    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.WEAPON
    data_path: str = "weapon.json"

    @staticmethod
    def get_game_name(icon: str) -> str:
        return icon.replace("UI_EquipIcon_", "")

    @staticmethod
    def game_name_map(game_name: str) -> Dict[str, tuple]:
        return {
            "icon": (f"UI_EquipIcon_{game_name}", "webp"),
            "awaken": (f"UI_EquipIcon_{game_name}_Awaken", "webp"),
            "gacha": (f"UI_Gacha_EquipIcon_{game_name}", "webp"),
        }

    @staticmethod
    def get_weapon_data(key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": key,
            "name": data.get("zh") or data.get("en") or "",
            "en_name": data.get("en", ""),
            "rank": data.get("rank", 3),
            "weapon_type": data.get("type", ""),
            "description": data.get("desc", "") or "",
        }

    async def parse_content(self, key: str, data: Dict[str, Any]) -> Optional[BaseWikiModel]:
        w_data = self.get_weapon_data(key, data)
        game_name = self.get_game_name(data.get("icon", ""))
        if w_data.get("weapon_type") == "ITEM_TPS_WEAPON":
            # skip: ITEM_TPS_WEAPON
            return None
        weapon = Weapon.model_validate(w_data)
        await _download_icons(self, weapon, self.game_name_map(game_name))
        return weapon


class NanokaArtifactSpider(NanokaBaseSpider):
    """nanoka 圣遗物爬虫，数据源 ``<base>/gi/<ver>/artifact.json``。"""

    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.ARTIFACT
    data_path: str = "artifact.json"

    #: 部分圣遗物套装缺少完整图标，忽略其下载失败日志
    IGNORE_FAIL_IDS = {
        "15004",  # 冰之川与雪之砂
        "15009",  # 祭火之人
        "15010",  # 祭水之人
        "15011",  # 祭雷之人
        "15012",  # 祭风之人
        "15013",  # 祭冰之人
    }

    @staticmethod
    def game_name_map(set_id: str) -> Dict[str, tuple]:
        return {
            "flower": (f"UI_RelicIcon_{set_id}_4", "webp"),
            "plume": (f"UI_RelicIcon_{set_id}_2", "webp"),
            "sands": (f"UI_RelicIcon_{set_id}_5", "webp"),
            "goblet": (f"UI_RelicIcon_{set_id}_1", "webp"),
            "circlet": (f"UI_RelicIcon_{set_id}_3", "webp"),
        }

    @staticmethod
    def get_artifact_data(key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        affix_list: Dict[str, str] = {}
        name = ""
        for affix_id, affix_data in (data.get("set") or {}).items():
            desc_map = affix_data.get("desc") or {}
            name_map = affix_data.get("name") or {}
            affix_list[affix_id] = desc_map.get("zh") or desc_map.get("CHS") or ""
            if not name:
                name = name_map.get("zh") or name_map.get("CHS") or ""
        return {
            "id": key,
            "name": name,
            "en_name": "",
            "level_list": data.get("rank", []),
            "affix_list": affix_list,
        }

    async def parse_content(self, key: str, data: Dict[str, Any]) -> Optional[BaseWikiModel]:
        a_data = self.get_artifact_data(key, data)
        artifact = Artifact.model_validate(a_data)
        await _download_icons(
            self,
            artifact,
            self.game_name_map(key),
            ignore_ids=self.IGNORE_FAIL_IDS,
        )
        return artifact


class NanokaBeyondItemSpider(NanokaBaseSpider):
    """nanoka 美装（beyond）爬虫。

    会同时拉取下面三个数据源并合并成一个 ``BeyondItem`` 集合：

    - ``<base>/gi/<ver>/zh/beyond/costume.json``        角色装扮
    - ``<base>/gi/<ver>/zh/beyond/costume_suit.json``   装扮套装
    - ``<base>/gi/<ver>/zh/beyond/item.json``           装饰物 / 其它道具

    为避免不同来源的主键冲突，``costume_suit`` 与 ``item`` 在合并后的 key
    及最终模型 ``id`` 上加上来源前缀（``suit:`` / ``item:``）；``costume``
    保持原始 key 以保证向后兼容。
    """

    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.BEYOND_ITEM
    #: 不再使用单一 data_path，统一由 ``data_paths`` 描述
    data_path: str = ""
    #: ``{来源标签: 相对路径}``，来源标签会作为分发解析逻辑的依据
    data_paths: Dict[str, str] = {
        "costume": "zh/beyond/costume.json",
        "suit": "zh/beyond/costume_suit.json",
        "item": "zh/beyond/item.json",
    }

    #: nanoka 数据中 rank 字段为颜色字符串，转换为对应星级
    _RANK_MAP = {
        "Orange": 5,
        "Purple": 4,
        "Blue": 3,
        "Green": 2,
        "Gray": 1,
    }

    @staticmethod
    def game_name_map(icon_name: str) -> Dict[str, tuple]:
        return {"icon": (icon_name, "webp")}

    async def _resolve_data_url(self) -> str:  # pragma: no cover - 不再使用单源解析
        raise RuntimeError(f"{self.__class__.__name__} 使用多数据源，请通过 data_paths 拉取数据")

    async def _load_source(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """并行拉取三个数据源，合并为一个 dict。

        合并后的 value 在原数据基础上额外注入 ``__source__`` 字段，
        以便 :meth:`parse_content` 据此分发到不同的解析逻辑。
        """
        version = await get_nanoka_version(self.game_key)
        if not version:
            logs.info(f"{self.__class__.__name__} 无法获取 nanoka 数据版本号，停止爬取")
            return None

        async def _fetch(source: str, path: str) -> Dict[str, Any]:
            url = build_data_url(self.game_key, version, path)
            try:
                response, _ = await self._request("GET", url)
                payload = response.json()
            except Exception as exc:
                traceback.print_exc()
                logs.info(f"{self.__class__.__name__} 请求 nanoka 数据失败 source={source} url={url}: {exc}")
                return {}
            if not isinstance(payload, dict):
                logs.info(
                    f"{self.__class__.__name__} 数据格式异常 source={source}，期望 dict，实际 {type(payload).__name__}"
                )
                return {}
            return payload

        sources = list(self.data_paths.items())
        results = await asyncio.gather(*(_fetch(s, p) for s, p in sources))

        merged: Dict[str, Dict[str, Any]] = {}
        for (source, _path), payload in zip(sources, results):
            for raw_key, raw_value in payload.items():
                if not isinstance(raw_value, dict):
                    continue
                value = dict(raw_value)
                value["__source__"] = source
                merged_key = str(raw_key)
                merged[merged_key] = value
        return merged

    @classmethod
    def get_beyond_data(cls, key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """将不同来源的原始数据统一映射为 ``BeyondItem`` 字段。"""
        source = data.get("__source__", "costume")
        rank_value = data.get("rank")
        if isinstance(rank_value, str):
            rank = cls._RANK_MAP.get(rank_value, 3)
        else:
            try:
                rank = int(rank_value) if rank_value is not None else 3
            except (TypeError, ValueError):
                rank = 3

        if source == "costume" or source == "suit":
            # nanoka costume.json 没有 desc/item_type，组合 body/color 作为描述，
            # 使用 slot 作为物品类型，最大限度保留信息
            body = "/".join(data.get("body") or [])
            color = "/".join(data.get("color") or [])
            desc_parts = [p for p in (body, color) if p]
            slot_list = data.get("slot") or []
            item_type = slot_list[0] if slot_list else "suit"
            desc = " / ".join(desc_parts)
        else:  # source == "item"
            # 通用装饰物：优先使用原 desc / item_type，缺失时回退到 type
            desc = data.get("desc") or data.get("description") or ""
            item_type = data.get("item_type") or data.get("type") or "item"

        return {
            "id": key,
            "name": data.get("name") or data.get("zh") or data.get("en") or "",
            "en_name": data.get("en", ""),
            "rank": rank,
            "desc": desc,
            "item_type": item_type,
        }

    async def parse_content(self, key: str, data: Dict[str, Any]) -> Optional[BaseWikiModel]:
        b_data = self.get_beyond_data(key, data)
        item = BeyondItem.model_validate(b_data)
        icon_name = data.get("icon", "")
        if not icon_name:
            return item
        await _download_icons(self, item, self.game_name_map(icon_name))
        return item
