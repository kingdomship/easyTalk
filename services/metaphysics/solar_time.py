"""真太阳时校正: 夏令时 → 经度 → 均时差 → 晚子时"""
import json
import os
import logging
from datetime import datetime, timedelta
import math

logger = logging.getLogger("metaphysics")

_dir = os.path.dirname(__file__)
with open(os.path.join(_dir, "cities.json"), "r") as f:
    _CITIES: dict = json.load(f)

_DEFAULT_CITY = {"name": "北京", "longitude": 116.4, "timezone": "Asia/Shanghai"}


def lookup_city(name: str) -> dict:
    """查询城市经纬度+时区, 不存在返回北京默认值"""
    city = _CITIES.get(name)
    if not city:
        return dict(_DEFAULT_CITY)
    return city


def normalize_gender(gender: str) -> int:
    """'女' → 0, '男' → 1 (lunar-python getYun(sex) 约定: 0=女 1=男)"""
    return 0 if gender in ("女", "female", "f") else 1


def correct_solar_time(birth_info: dict) -> dict:
    """校正出生时间为真太阳时, 返回校正后的 birth_info 副本"""
    result = dict(birth_info)
    clock_str = birth_info.get("clock_time", "12:00")
    hour, minute = map(int, clock_str.split(":"))
    city_name = birth_info.get("city", "北京")
    city = lookup_city(city_name)

    # ① 夏令时校正 (1986-1991)
    if birth_info.get("is_dst_affected") or (
        birth_info.get("calendar") == "solar"
        and _is_dst(birth_info.get("solar_date", ""), city.get("dst_years", []))
    ):
        hour = max(0, hour - 1)

    # ② 经度校正: 每偏离 120°E 一度 ±4 分钟
    offset_minutes = (city["longitude"] - 120.0) * 4
    total_minutes = hour * 60 + minute - int(offset_minutes)

    # ③ 均时差 (Equation of Time)
    solar_date = birth_info.get("solar_date", "")
    if solar_date:
        eot = _equation_of_time(solar_date)
        total_minutes -= int(eot)

    # ④ 跨日处理 + 晚子时判定
    total_minutes = total_minutes % (24 * 60)
    final_hour = total_minutes // 60
    final_minute = total_minutes % 60

    result["clock_time"] = f"{final_hour:02d}:{final_minute:02d}"
    result["city_longitude"] = city["longitude"]
    result["corrected"] = True

    return result


def _is_dst(solar_date: str, dst_years: list[int]) -> bool:
    """检查日期是否在夏令时范围内 (1986-1991 每年4月中旬-9月中旬)"""
    if not solar_date or not dst_years:
        return False
    try:
        dt = datetime.strptime(solar_date, "%Y-%m-%d")
        if dt.year not in dst_years:
            return False
        # 简化: 4月15日-9月15日为夏令时区间
        start = datetime(dt.year, 4, 15)
        end = datetime(dt.year, 9, 15)
        return start <= dt <= end
    except ValueError:
        return False


def _equation_of_time(solar_date: str) -> float:
    """计算均时差 (分钟), 使用简化天文公式 (±15分钟范围)"""
    try:
        dt = datetime.strptime(solar_date, "%Y-%m-%d")
        day_of_year = dt.timetuple().tm_yday
        # Spencer公式近似
        b = (2 * math.pi / 365) * (day_of_year - 81)
        eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
        return eot
    except ValueError:
        return 0.0
