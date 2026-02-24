import asyncio
import itertools
import re
import traceback
from asyncio import Queue
from multiprocessing import Value
from typing import List, Dict, Any, Optional, Union, AsyncIterator, Tuple

import ujson
from bs4 import BeautifulSoup
from httpx import Response, URL

from impl.assets_utils.logger import logs
from impl.core._abstract_spider import BaseSpider
from impl.core.file_manager import FileManager
from impl.models.base import BaseWikiModel, IconAsset, IconAssetUrl
from impl.models.enums import Game, DataType
from impl.models.genshin.enums import WeaponType, AttributeType
from impl.models.genshin.namecard import NameCard
from impl.models.genshin.weapon import WeaponAttribute, WeaponAffix, WeaponState, Weapon

HONEY_HOST = URL("https://gensh.honeyhunterworld.com/")


class HoneyWeaponSpider(BaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.WEAPON
    data_source: str = "honey"
    file_type: str = "json"
    priority = 110

    @staticmethod
    def scrape_urls() -> List[URL]:
        """爬取的目标网页集合

        例如有关武器的页面有:
        [单手剑](https://genshin.honeyhunterworld.com/fam_sword/?lang=CHS)
        [双手剑](https://genshin.honeyhunterworld.com/fam_claymore/?lang=CHS)
        [长柄武器](https://genshin.honeyhunterworld.com/fam_polearm/?lang=CHS)
        。。。
        这个函数就是返回这些页面的网址所组成的 List

        """
        return [HONEY_HOST.join(f"fam_{i.lower()}/?lang=CHS") for i in WeaponType.__members__]

    @classmethod
    async def _parse_soup(cls, soup: BeautifulSoup) -> "BaseWikiModel":
        """解析 soup 生成对应 WikiModel

        Args:
            soup: 需要解析的 soup
        Returns:
            返回对应的 WikiModel
        """
        """解析武器页"""
        soup = soup.select(".wp-block-post-content")[0]
        tables = soup.find_all("table")
        table_rows = tables[0].find_all("tr")

        def get_table_text(row_num: int) -> str:
            """一个快捷函数，用于返回表格对应行的最后一个单元格中的文本"""
            return table_rows[row_num].find_all("td")[-1].text.replace("\xa0", "")

        def find_table(select: str):
            """一个快捷函数，用于寻找对应表格头的表格"""
            return list(filter(lambda x: select in " ".join(x.attrs["class"]), tables))

        id_ = re.findall(r"/img/(.*?)_gacha", str(table_rows[0]))[0]
        weapon_type = WeaponType.convert(get_table_text(1).split(",")[-1].strip())
        name = get_table_text(0)
        rarity = len(table_rows[2].find_all("img"))
        ascension = [tag.get("alt").strip() for tag in table_rows[-1].find_all("img") if tag.get("alt")]
        if rarity > 2:  # 如果是 3 星及其以上的武器
            attribute = WeaponAttribute(
                type=AttributeType.convert(tables[2].find("thead").find("tr").find_all("td")[2].text.split(" ")[1]),
                value=get_table_text(6),
            )
            affix = WeaponAffix(
                name=get_table_text(7),
                description=[i.find_all("td")[1].text for i in tables[3].find_all("tr")[1:]],
            )
            description = get_table_text(9)
            if story_table := find_table("quotes"):
                story = story_table[0].text.strip()
            else:
                story = None
        else:  # 如果是 2 星及其以下的武器
            attribute = affix = None
            description = get_table_text(5)
            story = tables[-1].text.strip()
        stats = []
        for row in tables[2].find_all("tr")[1:]:
            cells = row.find_all("td")
            if rarity > 2:
                stats.append(WeaponState(level=cells[0].text, ATK=cells[1].text, bonus=cells[2].text))
            else:
                stats.append(WeaponState(level=cells[0].text, ATK=cells[1].text))
        return Weapon(
            id=id_,
            name=name,
            en_name="",
            rank=rarity,
            attribute=attribute,
            affix=affix,
            weapon_type=weapon_type,
            story=story,
            stats=stats,
            description=description,
            ascension=ascension,
        )

    async def _scrape(self, url: Union[URL, str]) -> "BaseWikiModel":
        """从 url 中爬取数据，并返回对应的 Model

        Args:
            url: 目标 url. 可以为字符串 str , 也可以为 httpx.URL
        Returns:
            返回对应的 WikiModel
        """
        response, _ = await self._request("GET", url, save=False)
        return await self._parse_soup(BeautifulSoup(response.text, "lxml"))

    async def _name_list_generator(self, *, with_url: bool = False) -> AsyncIterator[Union[str, Tuple[str, URL]]]:
        """一个 Model 的名称 和 其对应 url 的异步生成器

        Args:
            with_url: 是否返回相应的 url
        Returns:
            返回对应的名称列表 或者 名称与url 的列表
        """
        urls = self.scrape_urls()
        queue: Queue[Union[str, Tuple[str, URL]]] = Queue()  # 存放 Model 的队列
        signal = Value("i", len(urls))  # 一个用于异步任务同步的信号，初始值为存放所需要爬取的页面数

        async def task(page: URL):
            """包装的爬虫任务"""
            response, _ = await self._request("GET", page, save=False)
            # 从页面中获取对应的 chaos data (未处理的json格式字符串)
            chaos_data = re.findall(r"sortable_data\.push\((.*?)\);\s*sortable_cur_page", response.text)[0]
            json_data = ujson.loads(chaos_data)  # 转为 json
            for data in json_data:  # 遍历 json
                data_name = re.findall(r">(.*)<", data[1])[0].strip()  # 获取 Model 的名称
                if with_url:  # 如果需要返回对应的 url
                    data_url = HONEY_HOST.join(re.findall(r"\"(.*?)\"", data[0])[0])
                    await queue.put((data_name, data_url))
                else:
                    await queue.put(data_name)
            signal.value = signal.value - 1  # 信号量减少 1 ，说明该爬虫任务已经完成

        for url in urls:  # 遍历需要爬出的页面
            asyncio.create_task(task(url))  # 添加爬虫任务
        while signal.value > 0 or not queue.empty():  # 当还有未完成的爬虫任务或存放数据的队列不为空时
            yield await queue.get()  # 取出并返回一个存放的 Model

    async def get_name_list(self, *, with_url: bool = False) -> List[Union[str, Tuple[str, URL]]]:
        # 重写此函数的目的是名字去重，例如单手剑页面中有三个 “「一心传」名刀”
        name_list = [i async for i in self._name_list_generator(with_url=with_url)]
        if with_url:
            return [(i[0], list(i[1])[0][1]) for i in itertools.groupby(name_list, lambda x: x[0])]
        return [i[0] for i in itertools.groupby(name_list, lambda x: x)]

    async def full_data_generator(self) -> AsyncIterator["BaseWikiModel"]:
        """Model 生成器

        这是一个异步生成器，该函数在使用时会爬取所有数据，并将其转为对应的 Model，然后存至一个队列中
        当有需要时，再一个一个地迭代取出

        Returns:
            返回能爬到的所有的 WikiModel 所组成的 List
        """
        queue: Queue["BaseWikiModel"] = Queue()  # 存放 Model 的队列
        signal = Value("i", 0)  # 一个用于异步任务同步的信号

        async def task(u):
            # 包装的爬虫任务
            try:
                await queue.put(await self._scrape(u))  # 爬取一条数据，并将其放入队列中
            except NotImplementedError as exc:
                logs.info("爬取数据出现测试服数据 url[%s] %s", u, str(exc))
            except Exception as exc:  # pylint: disable=W0703
                logs.info("爬取数据出现异常 url[%s] %s", u, str(exc))
            finally:
                signal.value -= 1  # 信号量减少 1 ，说明该爬虫任务已经完成

        for _, url in await self.get_name_list(with_url=True):  # 遍历爬取所有需要爬取的页面
            signal.value += 1  # 信号量增加 1 ，说明有一个爬虫任务被添加
            asyncio.create_task(task(url))  # 创建一个爬虫任务

        while signal.value > 0 or not queue.empty():  # 当还有未完成的爬虫任务或存放数据的队列不为空时
            yield await queue.get()  # 取出并返回一个存放的 Model

    async def get_full_data(self) -> List["BaseWikiModel"]:
        """获取全部数据的 Model

        Returns:
            返回能爬到的所有的 Model 所组成的 List
        """
        return [i async for i in self.full_data_generator()]

    async def start_crawl(self) -> List[BaseWikiModel]:
        """启动爬虫

        Returns:
            返回能爬到的所有的 Model 所组成的 List
        """
        data = await self.get_full_data()
        await FileManager.save_raw_file(
            self.game,
            self.data_type,
            self.data_source,
            "json",
            ujson.dumps([i.model_dump() for i in data if i]).encode("utf-8"),
        )
        return data


class HoneyNameCardSpider(BaseSpider):
    game: "Game" = Game.GENSHIN
    data_type: "DataType" = DataType.NAMECARD
    data_source: str = "honey"
    file_type: str = "json"

    url = "https://gensh.honeyhunterworld.com/fam_nameplate/?lang=CHS"

    @staticmethod
    async def process_request_func(response: "Response") -> bytes:
        chaos_data = re.findall(r"sortable_data\.push\((.*?)\);\s*sortable_cur_page", response.text)[0]
        json_data = ujson.loads(chaos_data)
        return ujson.dumps(json_data, ensure_ascii=False, indent=4).encode("utf-8")

    async def start_crawl(self) -> List[BaseWikiModel]:
        _, content = await self._request("GET", self.url, process_func=self.process_request_func)
        json_data = ujson.loads(content)
        d = []
        tasks = []
        for i in json_data:
            tasks.append(self._parse_content(i))
            if len(tasks) > 10:
                t = await self.gather_tasks(tasks)
                d.extend([j for j in t if j])
        if tasks:
            t = await self.gather_tasks(tasks)
            d.extend([j for j in t if j])
        return d

    @staticmethod
    def game_name_map(nid: str) -> dict[str, tuple[str, str]]:
        return {
            "icon": (f"{nid}", "webp"),
            "navbar": (f"{nid}_back", "webp"),
            "profile": (f"{nid}_profile", "webp"),
        }

    @staticmethod
    async def get_character_data(data: Dict) -> Dict[str, Any]:
        return {
            "id": re.findall(r"/(.*?)/", data[1])[0],
            "name": re.findall(r"alt=\"(.*?)\"", data[0])[0],
            "en_name": "",
            "rank": int(re.findall(r">(\d)<", data[2])[0]),
        }

    @staticmethod
    def get_icon_url(filename: str, ext: str) -> str:
        return f"https://gensh.honeyhunterworld.com/img/{filename}.{ext}"

    async def _parse_content(self, data: Dict[str, Any]) -> Optional[BaseWikiModel]:
        try:
            return await self.parse_content(data)
        except Exception as e:
            traceback.print_exc()
            logs.info(f"解析数据失败: {e}")
            return None

    async def parse_content(self, data: Dict) -> BaseWikiModel:
        c_data = await self.get_character_data(data)
        c = NameCard.model_validate(c_data)
        # 图片
        game_name_map = self.game_name_map(c.id)
        for k, v in game_name_map.items():
            u = self.get_icon_url(v[0], v[1])
            try:
                p = await self._download_file(u)
            except Exception as e:
                logs.info(f"下载图片失败：{c} {e}")
                continue
            i = IconAsset()
            j = IconAssetUrl(url=u, path=str(p))
            setattr(i, v[1], j)
            setattr(c, k, i)
        return c
