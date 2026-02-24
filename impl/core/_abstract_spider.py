import abc
import asyncio
import traceback

from asyncio import sleep, PriorityQueue
from typing import Dict, List, Any, Tuple, Self

from httpx import AsyncClient, Response
from persica.factory.component import AsyncInitializingComponent

from .file_manager import FileManager
from ..config import config
from ..models.base import BaseWikiModel
from ..models.enums import DataType
from ..models.enums import Game


class RequestClient:
    client = AsyncClient()

    @staticmethod
    async def request(method: str, url: str, times: int = 3) -> "Response":
        try:
            response = await RequestClient.client.request(method, url, follow_redirects=True)
            if response.status_code == 200:
                return response
            else:
                times = 0
                raise Exception(f"Request {method} {url} failed with status code {response.status_code}")
        except Exception as e:
            if times > 0:
                await sleep(0.3)
                return await RequestClient.request(method, url, times - 1)
            else:
                raise e


class BaseSpider(AsyncInitializingComponent):
    game: "Game"
    data_type: "DataType"
    data_source: str
    file_type: str = "json"
    priority: int = 100

    @property
    def default_headers(self) -> Dict[str, str]:
        """默认请求头模板"""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.212 Safari/537.36",
            "Accept-Encoding": "gzip, deflate",
        }

    async def _request(
        self,
        method: str,
        url: str,
        response_type: str = "json",
        save: bool = True,
        process_func=None,
    ) -> Tuple["Response", Any]:
        response = await RequestClient.request(method, url)
        if process_func:
            data = await process_func(response)
        else:
            data = response.content
        if save:
            await FileManager.save_raw_file(self.game, self.data_type, self.data_source, response_type, data)
        return response, data

    async def _download_file(self, url: str) -> str:
        exists, p = FileManager.has_raw_icon(url, self.game, self.data_type, self.data_source)
        if exists:
            return p
        response = await RequestClient.request("GET", url)
        return await FileManager.save_raw_icon(url, self.game, self.data_type, self.data_source, response.content)

    async def initialize(self):
        if not hasattr(self, "game") or not self.game or not self.data_type:
            return
        await SpiderManager.add_to_spider(self.game, self.data_type, self)

    @staticmethod
    async def gather_tasks(tasks: list) -> List[BaseWikiModel]:
        """Gather tasks and return the results."""
        results = await asyncio.gather(*tasks)
        tasks.clear()
        return results

    def __lt__(self, other: "Self") -> bool:
        return self.priority < other.priority

    @abc.abstractmethod
    async def start_crawl(self) -> List[BaseWikiModel]:
        """
        抽象方法：爬虫入口
        子类需实现具体爬取流程控制
        """
        raise NotImplementedError


class SpiderManager:
    spiders: Dict["Game", Dict["DataType", PriorityQueue]] = {}
    SPIDER_INDEX_MAP: Dict["Game", Dict["DataType", str]] = {
        Game.GENSHIN: {DataType.WEAPON: "name", DataType.NAMECARD: "name"}
    }

    @staticmethod
    async def add_to_spider(game: "Game", data_type: "DataType", clz: "BaseSpider"):
        if game.value not in SpiderManager.spiders:
            SpiderManager.spiders[game] = {}
        if data_type.value not in SpiderManager.spiders[game]:
            SpiderManager.spiders[game][data_type] = PriorityQueue()
        await SpiderManager.spiders[game][data_type].put(clz)

    @staticmethod
    def merge_dict(dict_1: Dict[str, Any], dict_2: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并两个字典
        :param dict_1:
        :param dict_2:
        :return:
        """
        for key, value in dict_2.items():
            if not key or not value:
                continue
            if isinstance(value, dict):
                if key not in dict_1 or not dict_1[key]:
                    dict_1[key] = value
                else:
                    dict_1[key] = SpiderManager.merge_dict(dict_1[key], value)
            if key not in dict_1 or not dict_1[key]:
                dict_1[key] = value
        return dict_1

    @staticmethod
    def get_spider_model_index_key(game: "Game", data_type: "DataType") -> str:
        """
        获取爬虫模型索引键
        :param game:
        :param data_type:
        :return:
        """
        if game in SpiderManager.SPIDER_INDEX_MAP and data_type in SpiderManager.SPIDER_INDEX_MAP[game]:
            return SpiderManager.SPIDER_INDEX_MAP[game][data_type]
        return "id"

    @staticmethod
    async def start_crawl():
        """
        启动所有爬虫
        :return:
        """
        for game, data_types in SpiderManager.spiders.items():
            if game is Game.GENSHIN and not config.GENSHIN:
                continue
            if game is Game.STARRAIL and not config.STARRAIL:
                continue
            if game is Game.ZZZ and not config.ZZZ:
                continue
            if game is Game.WW and not config.WW:
                continue
            for data_type, spiders in data_types.items():
                data: List[List[Dict]] = []
                model_index_key = SpiderManager.get_spider_model_index_key(game, data_type)
                while not spiders.empty():
                    spider = await spiders.get()
                    try:
                        d = await spider.start_crawl()
                        data.append([i.model_dump() for i in d if i])
                        print(f"{game} {spider.__class__.__name__} 爬取完成，数据量: {len(d)}")
                    except Exception as e:
                        traceback.print_exc()
                        print(f"{game} {spider.__class__.__name__} 报错: {e}")
                # 合并
                final_data: List[Dict] = []
                final_data_ids: Dict[str, Dict] = {}
                for i in range(len(data)):
                    if i == 0:
                        final_data = data[i]
                        final_data_ids = {j[model_index_key]: j for j in data[i]}
                        continue
                    for j in data[i]:
                        if j[model_index_key] not in final_data_ids:
                            final_data.append(j)
                            final_data_ids[j[model_index_key]] = j
                        else:
                            old_data = final_data_ids[j[model_index_key]]
                            SpiderManager.merge_dict(old_data, j)
                # 保存
                if len(final_data) > 0:
                    await FileManager.save_data_file(game, data_type, final_data)
                    print(f"{game} {data_type} 爬取完成，数据量: {len(final_data)}")
                else:
                    print(f"{game} {data_type} 没有数据")
