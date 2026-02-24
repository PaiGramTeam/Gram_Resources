import aiofiles
import ujson
from typing import TYPE_CHECKING
from pathlib import Path
from httpx import URL

from ..assets_utils.path import ASSETS_ROOT, ASSETS_DATA_RAW_ROOT

if TYPE_CHECKING:
    from ..models.enums import Game, DataType


class FileManager:
    @staticmethod
    async def save_file(file_path: "Path", file_content: bytes):
        """保存文件"""
        async with aiofiles.open(file_path, "wb") as file:
            await file.write(file_content)

    @staticmethod
    async def load_file(file_path: "Path") -> bytes:
        """加载文件"""
        async with aiofiles.open(file_path, "rb") as file:
            content = await file.read()
        return content

    @staticmethod
    async def save_json(file_path: "Path", data: dict):
        """保存JSON文件"""
        async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
            await file.write(ujson.dumps(data, ensure_ascii=False, indent=4))

    @staticmethod
    async def load_json(file_path: "Path") -> dict:
        """加载JSON文件"""
        async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
            content = await file.read()
        return ujson.loads(content)

    @staticmethod
    def sync_load_json(file_path: "Path") -> dict:
        """同步加载JSON文件"""
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        return ujson.loads(content)

    @staticmethod
    def get_raw_file_path(
        game: "Game",
        data_type: "DataType",
        data_source: str = "",
        file_type: str = "json",
    ):
        if data_source:
            data_source = data_source.lower()
            p = ASSETS_DATA_RAW_ROOT / game.value / data_type.value / f"{data_source}.{file_type}"
        else:
            p = ASSETS_DATA_RAW_ROOT / game.value / f"{data_type.value}.{file_type}"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    async def save_raw_file(
        game: "Game",
        data_type: "DataType",
        data_source: str,
        file_type: str,
        data: bytes,
    ):
        """保存原始数据文件"""
        file_path = FileManager.get_raw_file_path(game, data_type, data_source, file_type)
        await FileManager.save_file(file_path, data)
        return file_path

    @staticmethod
    async def save_data_file(game: "Game", data_type: "DataType", data, data_source: str = ""):
        """保存数据文件"""
        file_path = FileManager.get_raw_file_path(game, data_type, data_source)
        await FileManager.save_json(file_path, data)

    @staticmethod
    async def load_data_file(game: "Game", data_type: "DataType", data_source: str = ""):
        """加载数据文件"""
        file_path = FileManager.get_raw_file_path(game, data_type, data_source)
        if not file_path.exists():
            return None
        return await FileManager.load_json(file_path)

    @staticmethod
    def get_raw_icon_path(url: str, game: "Game", data_type: "DataType", data_source: str):
        data_source = data_source.lower()
        p = ASSETS_DATA_RAW_ROOT / game.value / data_type.value / data_source
        p.mkdir(parents=True, exist_ok=True)
        u = URL(url)
        return p / u.path.split("/")[-1]

    @staticmethod
    def has_raw_icon(url: str, game: "Game", data_type: "DataType", data_source: str):
        """检查原始数据文件是否存在"""
        file_path = FileManager.get_raw_icon_path(url, game, data_type, data_source)
        return file_path.exists(), file_path.relative_to(ASSETS_ROOT)

    @staticmethod
    async def save_raw_icon(url: str, game: "Game", data_type: "DataType", data_source: str, data):
        """保存原始数据文件"""
        file_path = FileManager.get_raw_icon_path(url, game, data_type, data_source)
        await FileManager.save_file(file_path, data)
        return file_path.relative_to(ASSETS_ROOT)

    @staticmethod
    def get_file_ext(file_path: str) -> str:
        """获取文件扩展名"""
        file = Path(file_path)
        return file.suffix
