"""Milvus 向量数据库客户端"""
from typing import List, Dict, Any, Optional
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)
from app.config.settings import settings
from app.config.model_config import model_config
from app.utils.logger import logger


class MilvusClient:
    """Milvus 客户端封装（单例）"""

    _instance: Optional["MilvusClient"] = None
    _connected: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.host = settings.MILVUS_HOST
        self.port = settings.MILVUS_PORT
        self.user = settings.MILVUS_USER
        self.password = settings.MILVUS_PASSWORD
        self.db_name = settings.MILVUS_DB_NAME
        self._collections: Dict[str, Collection] = {}

    def connect(self):
        """连接 Milvus"""
        if self._connected:
            return

        try:
            conn_params = {
                "host": self.host,
                "port": str(self.port),
                "db_name": self.db_name,
            }
            if self.user:
                conn_params["user"] = self.user
            if self.password:
                conn_params["password"] = self.password

            connections.connect("default", **conn_params)
            self._connected = True
            logger.info(f"Milvus 连接成功: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Milvus 连接失败: {e}")
            # 在没有 Milvus 时不抛错，使用 mock 模式
            self._connected = False
            self._mock_mode = True
            logger.warning("Milvus 进入 mock 模式（用于本地开发测试）")
            return
        self._mock_mode = False

    def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            self.connect()

    def has_collection(self, collection_name: str) -> bool:
        """检查集合是否存在"""
        self._ensure_connected()
        if getattr(self, "_mock_mode", False):
            return collection_name in self._collections
        try:
            return utility.has_collection(collection_name)
        except Exception as e:
            logger.error(f"检查集合失败: {e}")
            return False

    def create_collection(self, collection_name: str) -> Collection:
        """创建集合（根据预定义配置）"""
        self._ensure_connected()

        if getattr(self, "_mock_mode", False):
            # mock 模式
            if collection_name not in self._collections:
                self._collections[collection_name] = _MockCollection(collection_name)
            return self._collections[collection_name]

        if self.has_collection(collection_name):
            collection = Collection(collection_name)
            self._collections[collection_name] = collection
            return collection

        # 根据名称匹配配置
        config = None
        if collection_name == model_config.user_chat_styles_collection.name:
            config = model_config.user_chat_styles_collection
        elif collection_name == model_config.post_contents_collection.name:
            config = model_config.post_contents_collection
        else:
            raise ValueError(f"未知的集合名称: {collection_name}")

        # 创建字段
        fields = []
        for f in config.fields:
            if f["dtype"] == "INT64":
                if f.get("is_primary"):
                    fields.append(
                        FieldSchema(
                            name=f["name"],
                            dtype=DataType.INT64,
                            is_primary=True,
                            auto_id=f.get("auto_id", False),
                        )
                    )
                else:
                    fields.append(
                        FieldSchema(name=f["name"], dtype=DataType.INT64)
                    )
            elif f["dtype"] == "VARCHAR":
                fields.append(
                    FieldSchema(
                        name=f["name"],
                        dtype=DataType.VARCHAR,
                        max_length=f.get("max_length", 256),
                    )
                )
            elif f["dtype"] == "FLOAT_VECTOR":
                fields.append(
                    FieldSchema(
                        name=f["name"],
                        dtype=DataType.FLOAT_VECTOR,
                        dim=f["dim"],
                    )
                )

        schema = CollectionSchema(
            fields=fields,
            description=config.description,
        )
        collection = Collection(name=collection_name, schema=schema)

        # 创建索引
        vector_field = next(
            (f["name"] for f in config.fields if f["dtype"] == "FLOAT_VECTOR"),
            None,
        )
        if vector_field:
            collection.create_index(
                field_name=vector_field,
                index_params=config.index_params,
            )

        self._collections[collection_name] = collection
        logger.info(f"Milvus 集合创建成功: {collection_name}")
        return collection

    def get_collection(self, collection_name: str) -> Collection:
        """获取集合"""
        self._ensure_connected()

        if getattr(self, "_mock_mode", False):
            if collection_name not in self._collections:
                self._collections[collection_name] = _MockCollection(collection_name)
            return self._collections[collection_name]

        if collection_name not in self._collections:
            if not self.has_collection(collection_name):
                self.create_collection(collection_name)
            else:
                self._collections[collection_name] = Collection(collection_name)
                self._collections[collection_name].load()

        return self._collections[collection_name]

    async def insert(
        self,
        collection_name: str,
        data: List[Dict[str, Any]],
    ) -> List[int]:
        """插入数据

        Args:
            collection_name: 集合名
            data: 数据列表，每项为一个字段字典

        Returns:
            插入的 ID 列表
        """
        try:
            collection = self.get_collection(collection_name)
            if isinstance(collection, _MockCollection):
                return collection.insert(data)
            ids = collection.insert(data)
            collection.flush()
            return ids.primary_keys
        except Exception as e:
            logger.error(f"Milvus 插入失败: {e}")
            return []

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        filter_expr: Optional[str] = None,
        limit: int = 10,
        output_fields: Optional[List[str]] = None,
        search_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """向量检索

        Args:
            collection_name: 集合名
            query_vector: 查询向量
            filter_expr: 过滤表达式，如 "user_id == 'xxx'"
            limit: 返回数量
            output_fields: 输出字段
            search_params: 搜索参数

        Returns:
            命中结果列表
        """
        try:
            collection = self.get_collection(collection_name)
            if isinstance(collection, _MockCollection):
                return collection.search(query_vector, filter_expr, limit, output_fields)

            # 找到向量字段名
            config = None
            if collection_name == model_config.user_chat_styles_collection.name:
                config = model_config.user_chat_styles_collection
            elif collection_name == model_config.post_contents_collection.name:
                config = model_config.post_contents_collection

            if config is None:
                return []

            vector_field = next(
                (f["name"] for f in config.fields if f["dtype"] == "FLOAT_VECTOR"),
                "embedding",
            )

            if output_fields is None:
                output_fields = []

            search_params = search_params or config.search_params

            results = collection.search(
                data=[query_vector],
                anns_field=vector_field,
                param=search_params,
                limit=limit,
                expr=filter_expr,
                output_fields=output_fields,
            )

            hits = []
            for hits_batch in results:
                for hit in hits_batch:
                    item = {
                        "id": hit.id,
                        "score": hit.score,
                        "distance": hit.distance,
                    }
                    if output_fields:
                        for field_name in output_fields:
                            item[field_name] = hit.entity.get(field_name)
                    hits.append(item)
            return hits
        except Exception as e:
            logger.error(f"Milvus 检索失败: {e}")
            return []

    async def delete(
        self,
        collection_name: str,
        filter_expr: str,
    ) -> int:
        """根据条件删除"""
        try:
            collection = self.get_collection(collection_name)
            if isinstance(collection, _MockCollection):
                return collection.delete(filter_expr)
            result = collection.delete(filter_expr)
            collection.flush()
            return result.delete_count
        except Exception as e:
            logger.error(f"Milvus 删除失败: {e}")
            return 0

    async def drop_collection(self, collection_name: str):
        """删除集合"""
        self._ensure_connected()
        if getattr(self, "_mock_mode", False):
            self._collections.pop(collection_name, None)
            return
        try:
            if self.has_collection(collection_name):
                utility.drop_collection(collection_name)
                self._collections.pop(collection_name, None)
                logger.info(f"Milvus 集合删除成功: {collection_name}")
        except Exception as e:
            logger.error(f"Milvus 集合删除失败: {e}")


class _MockCollection:
    """Milvus Mock 集合（用于无 Milvus 服务时的本地开发）"""

    def __init__(self, name: str):
        self.name = name
        self._data: List[Dict[str, Any]] = []
        self._next_id = 1

    def insert(self, data: List[Dict[str, Any]]):
        ids = []
        for item in data:
            if "id" not in item:
                item["id"] = self._next_id
                self._next_id += 1
            self._data.append(item)
            ids.append(item["id"])
        return type("InsertResult", (), {"primary_keys": ids})()

    def search(self, query_vector, filter_expr, limit, output_fields):
        # 简化：返回空
        return [[]]

    def delete(self, filter_expr):
        before = len(self._data)
        # 简化的过滤逻辑，仅支持 user_id == 'xxx' 模式
        if "user_id ==" in filter_expr:
            value = filter_expr.split("==")[1].strip().strip("'\"")
            self._data = [d for d in self._data if d.get("user_id") != value]
        return type("DeleteResult", (), {"delete_count": before - len(self._data)})()


# 全局实例
milvus_client = MilvusClient()
