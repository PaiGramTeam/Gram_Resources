from typing import Dict, Any

from impl.assets_utils.logger import logs
from impl.models.base import BaseWikiModel, IconAsset, IconAssetUrl
from impl.models.enums import Game, DataType
from impl.models.genshin.enums import Association, Element
from impl.models.genshin.artifact import Artifact
from impl.models.genshin.character import Character
from impl.models.genshin.material import Material
from impl.models.genshin.namecard import NameCard
from impl.models.genshin.weapon import Weapon
from impl._spiders.ambr import AmbrBaseSpider


class AmbrCharacterSpider(AmbrBaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.CHARACTER

    url = "https://gi.yatta.moe/api/v2/chs/avatar"

    @staticmethod
    def get_game_name(icon: str) -> str:
        return icon.replace("UI_AvatarIcon_", "")

    @staticmethod
    def game_name_map(game_name: str) -> dict[str, tuple[str, str]]:
        return {
            "icon": (f"UI_AvatarIcon_{game_name}", "png"),
            "side": (f"UI_AvatarIcon_Side_{game_name}", "png"),
            "gacha": (f"UI_Gacha_AvatarImg_{game_name}", "png"),
            "gacha_card": (f"UI_AvatarIcon_{game_name}_Card", "png"),
        }

    @staticmethod
    async def get_character_data(data: Dict[str, Any]) -> Dict[str, Any]:
        region = data["region"]
        special_region = {"NODKRAI_ZIBAI": "Nodkrai"}.get(region, region)
        return {
            "id": data["id"],
            "name": data["name"],
            "en_name": data["route"],
            "rank": data["rank"],
            "element": data["element"],
            "weapon_type": data["weaponType"],
            "body_type": data["bodyType"],
            "birthday": {"month": data["birthday"][0], "day": data["birthday"][1]},
            "association": Association.convert(special_region),
        }

    async def parse_content(self, data: Dict[str, Any]) -> list[BaseWikiModel]:
        c_data = await self.get_character_data(data)
        game_name = self.get_game_name(data["icon"])
        if c_data["id"] in {10000117, 10000118}:
            c_list = []
            for ele in list(Element):
                c_data_copy = c_data.copy()
                ele_lower = ele.name.lower()
                c_data_copy["id"] = f"{c_data['id']}-{ele_lower}"
                c_data_copy["element"] = ele.value
                c_list.append(await self.parse_content_single(c_data_copy, game_name))
            return c_list
        elif "element" not in c_data or c_data["element"] is None:
            logs.info(f"ambr 跳过异常角色：{c_data}")
            return []
        c = await self.parse_content_single(c_data, game_name)
        return [c]

    async def parse_content_single(self, c_data: dict[str, Any], game_name: str) -> Character:
        c = Character.model_validate(c_data)
        # 图片
        game_name_map = self.game_name_map(game_name)
        for k, v in game_name_map.items():
            u_list = self.get_icon_url(v[0], v[1])
            for u in u_list:
                try:
                    p = await self._download_file(u)
                except Exception as e:
                    logs.info(f"下载图片失败：{c} {e}")
                    continue
                i = IconAsset()
                j = IconAssetUrl(url=u, path=str(p))
                setattr(i, v[1], j)
                setattr(c, k, i)
                break
        return c


class AmbrWeaponSpider(AmbrBaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.WEAPON

    url = "https://gi.yatta.moe/api/v2/chs/weapon"

    @staticmethod
    def get_game_name(icon: str) -> str:
        return icon.replace("UI_EquipIcon_", "")

    @staticmethod
    def game_name_map(game_name: str) -> dict[str, tuple[str, str]]:
        return {
            "icon": (f"UI_EquipIcon_{game_name}", "png"),
            "awaken": (f"UI_EquipIcon_{game_name}_Awaken", "png"),
            "gacha": (f"UI_Gacha_EquipIcon_{game_name}", "png"),
        }

    @staticmethod
    async def get_character_data(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": data["id"],
            "name": data["name"],
            "en_name": data["route"],
            "rank": data["rank"],
            "weapon_type": data["type"],
            "description": "",
        }

    async def parse_content(self, data: Dict[str, Any]) -> list[BaseWikiModel]:
        c_data = await self.get_character_data(data)
        game_name = self.get_game_name(data["icon"])
        c = Weapon.model_validate(c_data)
        # 图片
        game_name_map = self.game_name_map(game_name)
        for k, v in game_name_map.items():
            u_list = self.get_icon_url(v[0], v[1])
            for u in u_list:
                try:
                    p = await self._download_file(u)
                except Exception as e:
                    logs.info(f"下载图片失败：{c} {e}")
                    continue
                i = IconAsset()
                j = IconAssetUrl(url=u, path=str(p))
                setattr(i, v[1], j)
                setattr(c, k, i)
                break
        return [c]


class AmbrMaterialSpider(AmbrBaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.MATERIAL

    url = "https://gi.yatta.moe/api/v2/chs/material"

    @staticmethod
    def game_name_map(game_name: str) -> dict[str, tuple[str, str]]:
        return {
            "icon": (game_name, "png"),
        }

    @staticmethod
    async def get_character_data(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": data["id"],
            "name": data["name"],
            "en_name": data["route"],
            "rank": data["rank"],
            "material_type": "",
        }

    async def parse_content(self, data: Dict[str, Any]) -> list[BaseWikiModel]:
        c_data = await self.get_character_data(data)
        c = Material.model_validate(c_data)
        # 图片
        game_name_map = self.game_name_map(data["icon"])
        for k, v in game_name_map.items():
            u_list = self.get_icon_url(v[0], v[1])
            for u in u_list:
                try:
                    p = await self._download_file(u)
                except Exception as e:
                    logs.info(f"下载图片失败：{c} {e}")
                    continue
                i = IconAsset()
                j = IconAssetUrl(url=u, path=str(p))
                setattr(i, v[1], j)
                setattr(c, k, i)
                break
        return [c]


class AmbrArtifactSpider(AmbrBaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.ARTIFACT

    url = "https://gi.yatta.moe/api/v2/chs/reliquary"

    @staticmethod
    def game_name_map(set_id: str) -> dict[str, tuple[str, str]]:
        return {
            "flower": (f"UI_RelicIcon_{set_id}_4", "png"),
            "plume": (f"UI_RelicIcon_{set_id}_2", "png"),
            "sands": (f"UI_RelicIcon_{set_id}_5", "png"),
            "goblet": (f"UI_RelicIcon_{set_id}_1", "png"),
            "circlet": (f"UI_RelicIcon_{set_id}_3", "png"),
        }

    @staticmethod
    async def get_character_data(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": data["id"],
            "name": data["name"],
            "en_name": data["route"],
            "level_list": data["levelList"],
            "affix_list": data["affixList"],
        }

    @staticmethod
    def get_icon_url(filename: str, ext: str) -> list[str]:
        return [
            f"https://enka.network/ui/{filename}.{ext}",
            f"https://gi.yatta.moe/assets/UI/reliquary/{filename}.{ext}",
        ]

    async def parse_content(self, data: Dict[str, Any]) -> list[BaseWikiModel]:
        c_data = await self.get_character_data(data)
        c = Artifact.model_validate(c_data)
        # 图片
        game_name_map = self.game_name_map(c.id)
        for k, v in game_name_map.items():
            u_list = self.get_icon_url(v[0], v[1])
            for u in u_list:
                try:
                    p = await self._download_file(u)
                except Exception as e:
                    if c.id not in [
                        "15004",  # 冰之川与雪之砂
                        "15009",  # 祭火之人
                        "15010",  # 祭水之人
                        "15011",  # 祭雷之人
                        "15012",  # 祭风之人
                        "15013",  # 祭冰之人
                    ]:
                        logs.info(f"下载图片失败：{c} {e}")
                    continue
                i = IconAsset()
                j = IconAssetUrl(url=u, path=str(p))
                setattr(i, v[1], j)
                setattr(c, k, i)
                break
        return [c]


class AmbrNameCardSpider(AmbrBaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.NAMECARD

    url = "https://gi.yatta.moe/api/v2/chs/namecard"
    priority = 90

    @staticmethod
    def game_name_map(game_name: str) -> dict[str, tuple[str, str]]:
        _game_name = "_".join(game_name.split("_")[2:])
        return {
            "icon": (game_name, "png"),
            # "navbar": (f"UI_NameCardPic_{game_name}_Alpha", "png"),
            "profile": (f"UI_NameCardPic_{_game_name}_P", "png"),
        }

    @staticmethod
    async def get_character_data(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": data["id"],
            "name": data["name"],
            "en_name": data["route"],
            "rank": data["rank"],
        }

    @staticmethod
    def get_icon_url(filename: str, ext: str) -> list[str]:
        return [
            f"https://enka.network/ui/{filename}.{ext}",
            f"https://gi.yatta.moe/assets/UI/namecard/{filename}.{ext}",
        ]

    async def parse_content(self, data: Dict[str, Any]) -> list[BaseWikiModel]:
        c_data = await self.get_character_data(data)
        c = NameCard.model_validate(c_data)
        # 图片
        game_name_map = self.game_name_map(data["icon"])
        for k, v in game_name_map.items():
            u_list = self.get_icon_url(v[0], v[1])
            for u in u_list:
                try:
                    p = await self._download_file(u)
                except Exception as e:
                    logs.info(f"下载图片失败：{c} {e}")
                    continue
                i = IconAsset()
                j = IconAssetUrl(url=u, path=str(p))
                setattr(i, v[1], j)
                setattr(c, k, i)
                break
        return [c]
