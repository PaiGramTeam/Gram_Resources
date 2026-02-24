import traceback
from functools import partial
from typing import List, Dict, Optional

from impl._spiders.genshin.other_json_data import ZH_LANG_MAP
from impl.assets_utils.logger import logs
from impl.config import config
from impl.core._abstract_spider import BaseSpider, RequestClient
from impl.core.file_manager import FileManager
from impl.models.base import BaseWikiModel
from impl.models.enums import Game, DataType
from impl.models.genshin.daily_material import MaterialsData, AreaDailyMaterialsData, CITY_NAMES

FILE_PATH = "https://gitlab.com/Dimbreath/AnimeGameData/-/raw/master/{PATH}"
DATA_FILES = """
ExcelBinOutput/AvatarExcelConfigData.json
ExcelBinOutput/AvatarPromoteExcelConfigData.json
ExcelBinOutput/AvatarSkillDepotExcelConfigData.json
ExcelBinOutput/AvatarSkillExcelConfigData.json
ExcelBinOutput/BydMaterialExcelConfigData.json
ExcelBinOutput/DungeonEntryExcelConfigData.json
ExcelBinOutput/MaterialExcelConfigData.json
ExcelBinOutput/ProudSkillExcelConfigData.json
ExcelBinOutput/WeaponExcelConfigData.json
ExcelBinOutput/WeaponPromoteExcelConfigData.json
TextMap/TextMapCHS.json
TextMap/TextMapCHT.json
TextMap/TextMapDE.json
TextMap/TextMapEN.json
TextMap/TextMapES.json
TextMap/TextMapFR.json
TextMap/TextMapIT.json
TextMap/TextMapJP.json
TextMap/TextMapKR.json
TextMap/TextMapPT.json
TextMap/TextMapRU_0.json
TextMap/TextMapRU_1.json
TextMap/TextMapTH_0.json
TextMap/TextMapTH_1.json
TextMap/TextMapTR.json
TextMap/TextMapVI.json
""".strip()
KEYS_MAP = {
    "id": "ELKKIAIGOBK",
    "nameTextMapHash": "DNINKKHEILA",
    "descTextMapHash": "PGEPICIANFN",
    # AvatarSkillExcelConfigData
    "skillIcon": "BGIHPNEDFOL",
    "forceCanDoSkill": "CFAICKLGPDP",
    "costElemType": "PNIDLNBBJIC",
    "proudSkillGroupId": "DGIJCGLPDPI",
    # AvatarTalentExcelConfigData
    "talentId": "JFALAEEKFMI",
    "icon": "CNPCNIGHGJJ",
    # ReliquaryExcelConfigData
    "itemType": "CEBMMGCMIJM",
    "equipType": "HNCDIADOINL",
    "rankLevel": "IMNCLIODOBL",
    "mainPropDepotId": "AIPPMEGLAKJ",
    "appendPropDepotId": "GIFPAPLPMGO",
    # EquipAffixExcelConfigData
    "affixId": "NEMBIFHOIKM",
    "openConfig": "JIPJEMFCKAI",
    # ReliquaryMainPropExcelConfigData
    # ReliquaryAffixExcelConfigData
    "propType": "JJNPGPFNJHP",
    "propValue": "AGDCHCBAGFO",
    # WeaponExcelConfigData
    "awakenIcon": "KMOCENBGOEM",
    # MaterialExcelConfigData
    "materialType": "HBBILKOGMIP",
    "picPath": "PPCKMKGIIMP",
    # ManualTextMapConfigData
    "textMapId": "EHLGDOCBKBO",
    "textMapContentTextMapHash": "ECIGIIKPLGD",
    # ProfilePictureExcelConfigData
    "iconPath": "FPPENJGNALC",
    # AvatarSkillDepotExcelConfigData
    "skills": "CBJGLADMBHG",
    "energySkill": "GIEFGHHKGDD",
    "talents": "IAGMADCJGIA",
    # AvatarExcelConfigData
    "iconName": "OCNPJGGMLLO",
    "sideIconName": "IPNPPIGGOPB",
    "qualityType": "ADLDGBEKECJ",
    "skillDepotId": "HCBILEOPKHD",
    "candSkillDepotIds": "FOCOLMLMEFN",
    "featureTagGroupID": "EOCNJBDLDMK",
    "avatarPromoteId": "ECMKJJIDKAE",
    # AvatarPromoteExcelConfigData
    "costItems": "FPIJIIENLBP",
    "promoteLevel": "AKPHFJACMIB",
    # ProudSkillExcelConfigData
    "level": "BHFAPOEDIDB",
}


def fix_map(data: str) -> str:
    for k, v in KEYS_MAP.items():
        data = data.replace(f'"{v}":', f'"{k}":')
    return data


class GenshinRoleMaterialSpider(BaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.OTHER
    data_source: str = "data"

    def __init__(self):
        super().__init__()
        self.save_path = save_path = partial(
            FileManager.get_raw_icon_path, game=self.game, data_type=self.data_type, data_source=self.data_source
        )
        self.avatar_data_path = save_path("AvatarExcelConfigData.json")
        self.avatar_promote_data_path = save_path("AvatarPromoteExcelConfigData.json")
        self.avatar_skill_depot_data_path = save_path("AvatarSkillDepotExcelConfigData.json")
        self.avatar_skill_data_path = save_path("AvatarSkillExcelConfigData.json")
        self.proud_skill_data_path = save_path("ProudSkillExcelConfigData.json")
        self.material_data_path = save_path("MaterialExcelConfigData.json")
        self.weapon_data_path = save_path("WeaponExcelConfigData.json")
        self.weapon_promote_data_path = save_path("WeaponPromoteExcelConfigData.json")

        self.material_data: Dict[int, str] = {}
        self.zh_lang_path = save_path("TextMap/TextMapCHS.json")
        self.avatar_promote_data: Dict[str, str] = {}
        self.skill_depot_map: Dict[str, int] = {}
        self.weapon_promote_map: Dict[int, List[int]] = {}
        """
        开发备忘：

        avatar_promote_data_path 是角色升级数据，里面包含了角色升级所需的素材消耗信息
        avatar_promote_data 是角色名称 -> avatarPromoteId 的 map

        avatar_skill_depot_data_path 是一个角色 id -> 天赋 id 的 map，不包含天赋信息
        skill_depot_map 是角色 id -> 主天赋 id 的 map
        avatar_skill_data_path 是天赋基础信息，不包含天赋消耗信息，需要进一步通过 proudSkillGroupId 请求
        proud_skill_data_path 是天赋详细信息，包含了素材消耗信息
        
        weapon_data_path 是武器数据
        weapon_promote_data_path 是武器升级数据，里面包含了武器升级所需的素材消耗信息
        weapon_promote_map 是 promote_id -> 素材id 列表 的 map

        material_data_path 是 item 信息
        material_data 是 id -> name 的 map
        zh_lang_path 是中文文本信息
        """
        self.cost_item_keys = ""
        self.data = {"status": 0, "data": {}}
        self.data_weapon = {"status": 0, "data": {}}

    async def _download_file(self, url: str) -> str:
        try:
            response = await RequestClient.request("GET", url)
            c = fix_map(response.text.replace("\r\n", "\n")).encode("utf-8")
            return await FileManager.save_raw_icon(url, self.game, self.data_type, self.data_source, c)
        except Exception as e:
            traceback.print_exc()
            logs.info(f"下载文件失败: {e}")
            return ""

    async def download_data_file(self):
        tasks = [self._download_file(FILE_PATH.format(PATH=p.strip())) for p in DATA_FILES.split("\n")]
        await self.gather_tasks(tasks)

    async def get_name_list(self):
        ignore_name_list = ["旅行者", "奇偶·男性", "奇偶·女性"]
        name_list = []
        avatar_data = await FileManager.load_json(self.avatar_data_path)
        for avatar in avatar_data:
            if avatar["featureTagGroupID"] == 10000001:
                # 未上线角色
                continue
            cid = avatar["id"]
            if cid >= 10000900:
                # 未上线角色
                continue
            avatar_name = ZH_LANG_MAP[str(avatar["nameTextMapHash"])]
            if avatar_name not in ignore_name_list and avatar_name not in name_list:
                name_list.append(avatar_name)
                self.avatar_promote_data[avatar_name] = avatar["avatarPromoteId"]
                self.skill_depot_map[avatar_name] = avatar["skillDepotId"]
                self.data["data"][avatar_name] = {"id": cid, "name": avatar_name}
        return name_list

    async def load_material_data(self):
        _material_data = await FileManager.load_json(self.material_data_path)
        for material in _material_data:
            try:
                self.material_data[material["id"]] = ZH_LANG_MAP[str(material["nameTextMapHash"])]
            except KeyError:
                pass

    async def load_weapon_promote_data(self):
        _weapon_promote_data = await FileManager.load_json(self.weapon_promote_data_path)
        for weapon in _weapon_promote_data:
            pid = weapon["weaponPromoteId"]
            cos = weapon.get(self.cost_item_keys, [])
            if len(cos) != 3:
                continue
            for i in cos:
                if not i:
                    continue
                t_list = self.weapon_promote_map.get(pid, [])
                if i["id"] not in t_list:
                    t_list.append(i["id"])
                    self.weapon_promote_map[pid] = t_list
        return self.weapon_promote_map

    async def dump_weapon_promote_data(self):
        weapon_data = await FileManager.load_json(self.weapon_data_path)
        for weapon in weapon_data:
            wid = weapon["id"]
            name = ZH_LANG_MAP.get(str(weapon["nameTextMapHash"]), "")
            if "test" in name or "测试" in name:
                continue
            pid = weapon["weaponPromoteId"]
            if pid not in self.weapon_promote_map:
                continue
            _weapon_data = {
                "id": wid,
                "name": name,
                "materials": [self.material_data[i] for i in self.weapon_promote_map[pid] if i],
            }
            self.data_weapon["data"][str(wid)] = _weapon_data

    @staticmethod
    def guess_cost_items_key(avatar_promote_data: List[Dict]) -> Optional[str]:
        for data in avatar_promote_data:
            for k, v in data.items():
                if not isinstance(v, list):
                    continue
                for v1 in v:
                    if "count" in v1.keys():
                        return k
        return None

    async def get_up_data(self):
        _avatar_promote_data = await FileManager.load_json(self.avatar_promote_data_path)
        data_map: Dict[str, Dict] = {}
        data_material_map: Dict[str, List[str]] = {}
        self.cost_item_keys = self.guess_cost_items_key(_avatar_promote_data)
        if not self.cost_item_keys:
            logs.error("无法识别角色升级数据中的素材消耗字段")
            return
        for avatar in _avatar_promote_data:
            pid = avatar["avatarPromoteId"]
            cos = avatar.get(self.cost_item_keys, [])
            if len(cos) != 4:
                continue
            for i in cos[2:]:
                if not i:
                    continue
                t_list = data_material_map.get(pid, [])
                if i["id"] not in t_list:
                    t_list.append(i["id"])
                    data_material_map[pid] = t_list

            if avatar.get("promoteLevel") != 6:
                continue
            data_map[avatar["avatarPromoteId"]] = avatar
            data_material_map.get(pid, []).sort()
        for avatar, pid in self.avatar_promote_data.items():
            t = data_map[pid]
            if "奇偶" in avatar:
                continue
            self.data["data"][avatar]["ascension_materials"] = self.material_data[t[self.cost_item_keys][0]["id"]]
            self.data["data"][avatar]["level_up_materials"] = self.material_data[t[self.cost_item_keys][1]["id"]]
            self.data["data"][avatar]["materials"] = [self.material_data[i] for i in data_material_map[pid] if i]

    async def load_avatar_skill_depot_data(self) -> Dict[int, int]:
        _avatar_skill_depot_data = await FileManager.load_json(self.avatar_skill_depot_data_path)
        energy_skill_map: Dict[int, int] = {}
        for _avatar in _avatar_skill_depot_data:
            if "energySkill" not in _avatar:
                continue
            energy_skill_map[_avatar["id"]] = _avatar["energySkill"]
        return energy_skill_map

    async def load_avatar_skill_data(self) -> Dict[int, int]:
        _avatar_skill_data = await FileManager.load_json(self.avatar_skill_data_path)
        avatar_skill_map: Dict[int, int] = {}
        for _avatar in _avatar_skill_data:
            if "proudSkillGroupId" not in _avatar:
                continue
            avatar_skill_map[_avatar["id"]] = _avatar["proudSkillGroupId"]
        return avatar_skill_map

    async def load_proud_skill_data(self) -> Dict[int, List[str]]:
        _proud_skill_data = await FileManager.load_json(self.proud_skill_data_path)
        proud_skill_map: Dict[int, List[str]] = {}
        for _avatar in _proud_skill_data:
            if _avatar["level"] != 10:
                continue
            key = _avatar["proudSkillGroupId"]
            cos = _avatar[self.cost_item_keys]
            value = [self.material_data[cos[0]["id"]][1:3], self.material_data[cos[2]["id"]]]
            proud_skill_map[key] = value
        return proud_skill_map

    async def get_skill_data(self):
        energy_skill_map = await self.load_avatar_skill_depot_data()
        avatar_skill_map = await self.load_avatar_skill_data()
        proud_skill_map = await self.load_proud_skill_data()
        for avatar, depot_id in self.skill_depot_map.items():
            if "奇偶" in avatar:
                continue
            skill_id = energy_skill_map[depot_id]
            skill_group_id = avatar_skill_map[skill_id]
            self.data["data"][avatar]["talent"] = proud_skill_map[skill_group_id]

    async def get_material_data(self):
        await self.get_name_list()
        await self.load_material_data()
        await self.get_up_data()
        await self.get_skill_data()
        await FileManager.save_data_file(self.game, self.data_type, self.data, "roles_material")

    async def get_material_data_weapon(self):
        await self.load_weapon_promote_data()
        await self.dump_weapon_promote_data()
        await FileManager.save_data_file(self.game, self.data_type, self.data_weapon, "weapons_material")

    async def initialize(self):
        if not config.GENSHIN:
            return
        if config.GENSHIN_EXCEL_DATA:
            logs.info("Download raw file")
            await self.download_data_file()
            logs.info("Download raw file success")
        ZH_LANG_MAP.update(await FileManager.load_json(self.zh_lang_path))
        try:
            await self.get_material_data()
            await self.get_material_data_weapon()
        except Exception as e:
            traceback.print_exc()
            raise e

    async def start_crawl(self) -> List[BaseWikiModel]:
        pass


class GenshinDailyMaterialSpider(GenshinRoleMaterialSpider):
    __order__ = 10
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.OTHER
    data_source: str = "data"

    def __init__(self):
        super().__init__()
        self.city_names = CITY_NAMES
        self.dungeon_entry_data_path = self.save_path("DungeonEntryExcelConfigData.json")

        self.dungeon_entry_data_avatar = []
        self.dungeon_entry_data_weapon = []
        self.material_avatar_map: Dict[int, str] = {}
        self.material_weapon_map: Dict[int, str] = {}
        """
        开发备忘：

        dungeon_entry_data_path 是秘境数据
          type DUNGEN_ENTRY_TYPE_AVATAR_TALENT 为 角色天赋素材
          type DUNGEN_ENTRY_TYPE_WEAPON_PROMOTE 为 武器突破素材
        dungeon_entry_data_avatar 是角色天赋素材秘境数据列表
        dungeon_entry_data_weapon 是武器突破素材秘境数据列表

        material_avatar_map 是 角色id -> 素材名称 的 map
        material_weapon_map 是 武器id -> 素材名称 的 map
        """
        self.data: "MaterialsData"

    def init_base_data(self):
        def _get_base_data():
            return {
                "avatar_materials": [],
                "avatar": [],
                "weapon_materials": [],
                "weapon": [],
            }

        self.data = MaterialsData.model_validate(
            [{city: _get_base_data() for city in self.city_names} for _ in range(7)]
        )

    async def load_dungeon_entry_data(self):
        _dungeon_entry_data = await FileManager.load_json(self.dungeon_entry_data_path)
        for dungeon in _dungeon_entry_data:
            if dungeon["type"] == "DUNGEN_ENTRY_TYPE_AVATAR_TALENT":
                self.dungeon_entry_data_avatar.append(dungeon)
            elif dungeon["type"] == "DUNGEN_ENTRY_TYPE_WEAPON_PROMOTE":
                self.dungeon_entry_data_weapon.append(dungeon)
        if len(self.dungeon_entry_data_avatar) != len(self.city_names):
            logs.warning("角色天赋素材秘境数据异常，数量不匹配")
        if len(self.dungeon_entry_data_weapon) != len(self.city_names):
            logs.warning("武器突破素材秘境数据异常，数量不匹配")

    async def dump_dungeon_entry_data(self):
        for data, key in [
            (self.dungeon_entry_data_avatar, "avatar_materials"),
            (self.dungeon_entry_data_weapon, "weapon_materials"),
        ]:
            for idx, dungeon in enumerate(data):
                city = self.city_names[idx]
                materials_weeks = (
                    dungeon["descriptionCycleRewardList"][:-1] * 2 + dungeon["descriptionCycleRewardList"][-1:]
                )
                if len(materials_weeks) != 7:
                    logs.warning("秘境数据异常，数据长度不匹配 id=%s", dungeon["id"])
                    continue
                for week, materials in enumerate(materials_weeks):
                    materials_names = [self.material_data[i] for i in materials]
                    setattr(self.data[week][city], key, materials_names)

    async def load_material_map(self):
        roles_material = (await FileManager.load_data_file(self.game, self.data_type, "roles_material"))["data"]
        for v in roles_material.values():
            if not v["talent"]:
                continue
            self.material_avatar_map[v["id"]] = v["talent"][0]
        weapons_material = (await FileManager.load_data_file(self.game, self.data_type, "weapons_material"))["data"]
        for v in weapons_material.values():
            if not v["materials"]:
                continue
            self.material_weapon_map[v["id"]] = v["materials"][0]

    async def dump_material_map(self):
        for week in range(7):
            for city in self.city_names:
                area_data: "AreaDailyMaterialsData" = self.data[week][city]
                avatar_material_name = set([i[1:3] for i in area_data.avatar_materials])
                for material in avatar_material_name:
                    for mid, mname in self.material_avatar_map.items():
                        if mname == material:
                            if mid not in area_data.avatar:
                                area_data.avatar.append(str(mid))
                for material in area_data.weapon_materials:
                    for mid, mname in self.material_weapon_map.items():
                        if mname == material:
                            if mid not in area_data.weapon:
                                area_data.weapon.append(str(mid))
                area_data.avatar.sort()
                area_data.weapon.sort()

    async def get_material_data(self):
        self.init_base_data()
        await self.load_dungeon_entry_data()
        await self.load_material_data()
        await self.dump_dungeon_entry_data()
        await self.load_material_map()
        await self.dump_material_map()
        await FileManager.save_data_file(self.game, self.data_type, self.data.model_dump(), "daily_material")

    async def initialize(self):
        if not config.GENSHIN:
            return
        self.zh_lang = await FileManager.load_json(self.zh_lang_path)
        logs.info("parse_honey_impact_source")
        try:
            await self.get_material_data()
        except Exception as e:
            traceback.print_exc()
            raise e

    async def start_crawl(self) -> List[BaseWikiModel]:
        pass


class GenshinOtherSpider(BaseSpider):
    __order__ = 20
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.OTHER

    async def initialize(self):
        if not config.GENSHIN:
            return
        logs.info("merge genshin other data")
        data = {
            "daily_material": await FileManager.load_data_file(self.game, self.data_type, "daily_material"),
            "roles_material": await FileManager.load_data_file(self.game, self.data_type, "roles_material"),
            "weapons_material": await FileManager.load_data_file(self.game, self.data_type, "weapons_material"),
        }
        await FileManager.save_data_file(self.game, self.data_type, data)

    async def start_crawl(self) -> List[BaseWikiModel]:
        pass
