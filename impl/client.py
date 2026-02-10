import asyncio
import contextlib
from pathlib import Path
from ssl import SSLZeroReturnError
from typing import Callable, Dict, Generic, List, Optional, Protocol, Type, TypeVar, overload

from aiofiles import open as async_open
from httpx import AsyncClient, HTTPError, Response

from .assets_utils.path import ASSETS_ROOT
from .core.file_manager import FileManager
from .models.base import BaseWikiModel, IconAsset
from .models.enums import Game, DataType
from utils.const import PROJECT_ROOT
from utils.log import logger
from utils.typedefs import StrOrURL, StrOrInt

T = TypeVar("T")
ASSETS_PATH = PROJECT_ROOT.joinpath("resources/assets")
ASSETS_PATH.mkdir(exist_ok=True, parents=True)


class IconGetter(Protocol):
    @overload
    def __call__(self, target: StrOrInt, second_target: StrOrInt) -> Path | None: ...
    @overload
    def __call__(self, target: StrOrInt) -> Path | None: ...


def _icon_getter(mode: str) -> IconGetter:
    def wrapper(self: "_AssetsService[T]", target: StrOrInt, second_target: StrOrInt | None = None) -> Path | None:
        return self._get_icon(self.get_target(target, second_target), mode)

    return wrapper


class _AssetsServiceError(Exception):
    pass


class _AssetsCouldNotFound(_AssetsServiceError):
    def __init__(self, message: str, target: str):
        self.message = message
        self.target = target
        super().__init__(f"{message}: target={target}")


class _AssetsService(Generic[T]):
    client: "AsyncClient" = AsyncClient(timeout=60.0)
    BASE_URL = "https://ys-res.paimon.vip/"
    game: "Game"
    data_type: "DataType"
    data_model: Type[T]
    DEFAULT_ID: int = None
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.all_items: List[T] = []
        self.all_items_map: Dict[str, T] = {}
        self.all_items_name: Dict[str, T] = {}
        self.sync_read_metadata()

    async def _remote_get(self, url: StrOrURL, retry: int = 5) -> Optional["Response"]:
        for time in range(retry):
            try:
                response = await self.client.get(url, follow_redirects=False)
            except Exception as error:  # pylint: disable=W0703
                if not isinstance(error, (HTTPError, SSLZeroReturnError)):
                    logger.error(error)  # 打印未知错误
                if time != retry - 1:  # 未达到重试次数
                    await asyncio.sleep(1)
                else:
                    raise error
                continue
            if response.status_code != 200:  # 判定页面是否正常
                return None
            return response
        return None

    async def _download(self, url: StrOrURL, path: Path, retry: int = 5) -> Optional[Path]:
        """从 url 下载图标至 path"""
        if not url:
            return None
        logger.debug("正在从 %s 下载图标至 %s", url, path)
        response = await self._remote_get(url, retry)
        if not response:
            return None
        async with async_open(path, "wb") as file:
            await file.write(response.content)  # 保存图标
        return path.resolve()

    @property
    def data_url(self) -> str:
        """数据的远程地址"""
        return self.BASE_URL + str(
            FileManager.get_raw_file_path(self.game, self.data_type).relative_to(ASSETS_ROOT)
        ).replace("\\", "/")

    @property
    def base_path(self) -> Path:
        """数据的基础地址"""
        p = ASSETS_PATH / self.game.value / self.data_type.value
        p.mkdir(exist_ok=True, parents=True)
        return p

    @property
    def data_path(self) -> Path:
        """数据的本地地址"""
        return self.base_path.parent / f"{self.data_type.value}.json"

    def clear_class_data(self) -> None:
        self.all_items.clear()
        self.all_items_map.clear()
        self.all_items_name.clear()

    def _get_icon_path(self, model: "IconAsset") -> Optional[Path]:
        try:
            file_name = Path(model.path.replace("\\", "/")).parts[-2:]
            return self.base_path / Path(*file_name)
        except ValueError:
            logger.debug("图标路径错误: %s", model)
            return None

    async def _download_icon(self, model: "IconAsset"):
        """下载图标"""
        try:
            url = self.BASE_URL + model.path.replace("\\", "/")
            path = self._get_icon_path(model)
        except ValueError:
            logger.debug("图标路径错误: %s", model)
            return None
        if path.exists():
            return path
        path.parent.mkdir(exist_ok=True, parents=True)
        await self._download(url, path)
        return path

    def _sync_read_metadata(self, datas):
        self.clear_class_data()
        for data in datas:
            item = self.data_model.model_validate(data)
            self.all_items.append(item)
            self.all_items_map[item.id] = item
            self.all_items_name[item.name] = item

    def sync_read_metadata(self):
        if not self.data_path.exists():
            return
        datas = FileManager.sync_load_json(self.data_path)
        self._sync_read_metadata(datas)

    async def read_metadata(self, force: bool):
        if force or not self.data_path.exists():
            datas = await self._remote_get(self.data_url)
            await FileManager.save_file(self.data_path, datas.content)
        datas = await FileManager.load_json(self.data_path)
        self._sync_read_metadata(datas)

    async def download_icons(self):
        need_download_fields = []
        for k, v in self.data_model.model_fields.items():
            anno = v.annotation
            if anno == IconAsset or (hasattr(anno, "__args__") and IconAsset in anno.__args__):
                need_download_fields.append(k)
        tasks = []
        for item in self.all_items:
            item: "BaseWikiModel"
            for field in need_download_fields:
                icon: "IconAsset" = getattr(item, field)
                if not icon:
                    continue
                tasks.append(self._download_icon(icon))
                if len(tasks) > 10:
                    await asyncio.gather(*tasks)
                    tasks.clear()
        if tasks:
            await asyncio.gather(*tasks)
            tasks.clear()

    async def initialize(self, force):
        """初始化数据"""
        logger.info("正在初始化 %s 素材", self.data_type.value)
        await self.read_metadata(force)
        await self.download_icons()

    def get_by_id(self, cid: StrOrInt) -> Optional[T]:
        cid = str(cid)
        return self.all_items_map.get(cid)

    def get_by_name(self, name: str) -> Optional[T]:
        return self.all_items_name.get(name)

    def search_by_name(self, name: str) -> Optional[T]:
        return next(filter(lambda item: name in item.name, self.all_items), None)

    def get_name_list(self) -> List[str]:
        return list(self.all_items_name.keys())

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> Optional[T]:
        data = None
        if target == 0 and self.DEFAULT_ID is not None:
            target = self.DEFAULT_ID
        with contextlib.suppress(ValueError, TypeError):
            target = int(target)
        if isinstance(target, int):
            data = self.get_by_id(target)
        elif isinstance(target, str):
            data = self.get_by_name(target)
        if data is None:
            if second_target:
                return self.get_target(second_target)
            raise _AssetsCouldNotFound("角色素材图标不存在", target)
        return data

    def _get_icon(self, model: T, property_name: str) -> Optional[Path]:
        icon: "IconAsset" = getattr(model, property_name)
        if not icon:
            return None
        return self._get_icon_path(icon)
