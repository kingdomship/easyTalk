"""ChartCache: 内存单例 + 文件持久化 — 出生信息MD5不变不重算"""
import hashlib
import json
import logging
import os
import threading
import time

from app.config import BIRTH_INFO_PATH, BAZI_CACHE_PATH, ZIWEI_CACHE_PATH

logger = logging.getLogger("metaphysics")


class ChartCache:
    """命盘缓存 — 两层: 静态层(永久, 出生MD5不变不重算) + 动态层(5min TTL)"""
    _instance = None
    _lock = threading.Lock()
    _bazi_static: dict | None = None
    _ziwei_static: dict | None = None
    _birth_hash: str | None = None
    _dynamic_cache: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_bazi(self, include_dynamic=True):
        with self._lock:
            current_hash = self._read_birth_hash()
            if self._birth_hash != current_hash:
                self._bazi_static = self._compute_bazi_static()
                self._save_json(BAZI_CACHE_PATH, self._bazi_static)
                self._birth_hash = current_hash

        static = self._bazi_static
        if not include_dynamic or not static:
            return static or {}

        dynamic = self._get_dynamic_with_ttl("bazi_dynamic", 300, self._compute_bazi_dynamic)
        return {**static, **(dynamic or {})}

    def get_ziwei(self, include_dynamic=True):
        with self._lock:
            current_hash = self._read_birth_hash()
            if self._birth_hash != current_hash or self._ziwei_static is None:
                self._ziwei_static = self._compute_ziwei_static()
                self._save_json(ZIWEI_CACHE_PATH, self._ziwei_static)
                self._birth_hash = current_hash

        static = self._ziwei_static
        if not include_dynamic or not static:
            return static or {}

        dynamic = self._get_dynamic_with_ttl("ziwei_dynamic", 300, self._compute_ziwei_dynamic)
        return {**static, **(dynamic or {})}

    async def get_bazi_async(self, include_dynamic=True):
        import asyncio
        return await asyncio.to_thread(self.get_bazi, include_dynamic)

    async def get_ziwei_async(self, include_dynamic=True):
        import asyncio
        return await asyncio.to_thread(self.get_ziwei, include_dynamic)

    def get_birth_hash(self):
        return self._read_birth_hash()

    def invalidate(self):
        with self._lock:
            self._bazi_static = None
            self._ziwei_static = None
            self._birth_hash = None
            self._dynamic_cache.clear()

    def _compute_bazi_static(self):
        birth_info = self._read_birth_info()
        if not birth_info:
            return {}
        from services.metaphysics.solar_time import correct_solar_time
        from services.metaphysics.bazi.paipan import compute_bazi_static
        corrected = correct_solar_time(birth_info)
        return compute_bazi_static(corrected)

    def _compute_ziwei_static(self):
        birth_info = self._read_birth_info()
        if not birth_info:
            return {}
        try:
            from services.metaphysics.solar_time import correct_solar_time
            from services.metaphysics.ziwei.paipan import compute_ziwei_static
            corrected = correct_solar_time(birth_info)
            return compute_ziwei_static(corrected)
        except ImportError:
            return {}

    def _compute_bazi_dynamic(self):
        if not self._bazi_static:
            return {}
        from services.metaphysics.bazi.paipan import compute_bazi_dynamic
        return compute_bazi_dynamic(self._bazi_static)

    def _compute_ziwei_dynamic(self):
        if not self._ziwei_static:
            return {}
        try:
            from services.metaphysics.ziwei.paipan import compute_ziwei_dynamic
            return compute_ziwei_dynamic(self._ziwei_static)
        except ImportError:
            return {}

    def _get_dynamic_with_ttl(self, key, ttl_seconds, compute_fn):
        with self._lock:
            entry = self._dynamic_cache.get(key)
            if entry:
                ts, data = entry
                if time.time() - ts < ttl_seconds:
                    return data
            data = compute_fn()
            self._dynamic_cache[key] = (time.time(), data)
            return data

    def _read_birth_hash(self):
        if not os.path.exists(BIRTH_INFO_PATH):
            return None
        with open(BIRTH_INFO_PATH, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _read_birth_info(self):
        if not os.path.exists(BIRTH_INFO_PATH):
            return None
        with open(BIRTH_INFO_PATH, "r") as f:
            return json.load(f)

    @staticmethod
    def _save_json(path, data):
        if data is None:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


cache = ChartCache()
