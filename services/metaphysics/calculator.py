"""Calculator orchestrator — assemble full chart, parallel bazi+ziwei"""
import asyncio
import logging

logger = logging.getLogger("metaphysics")


def _safe_compute(fn, *args):
    """排盘安全包装器: 捕获所有异常, 返回带 error 字段的结构"""
    try:
        return fn(*args)
    except Exception as e:
        logger.error(
            "排盘失败: %s args=%s", fn.__name__, str(args)[:200], exc_info=True
        )
        return {
            "error": True,
            "error_code": "COMPUTE_FAILED",
            "error_message": "命盘计算失败，请检查出生信息是否正确",
            "detail": str(e)[:200],
        }


def _normalize_birth_info(birth_info):
    """标准化出生信息: 农历→公历转换（若需要）"""
    if birth_info.get("calendar") == "lunar" and birth_info.get("lunar_date"):
        from services.metaphysics.solar_time import convert_lunar_to_solar
        solar = convert_lunar_to_solar(
            birth_info["lunar_date"],
            birth_info.get("clock_time", "12:00"),
        )
        info = dict(birth_info)
        info["calendar"] = "solar"
        info["solar_date"] = solar["solar_date"]
        info["clock_time"] = solar["clock_time"]
        return info
    return birth_info


def validate_birth_info(birth_info):
    """校验 birth_info 字段合法性"""
    if not birth_info:
        return {"error": True, "error_code": "INVALID_BIRTH_INFO",
                "error_message": "缺少出生信息"}

    # 农历→公历转换
    birth_info = _normalize_birth_info(birth_info)

    solar_date = birth_info.get("solar_date", "")
    clock_time = birth_info.get("clock_time", "")

    from datetime import datetime
    try:
        dt = datetime.strptime(solar_date, "%Y-%m-%d")
        if dt.year < 1900 or dt.year > 2100:
            return {"error": True, "error_code": "DATE_OUT_OF_RANGE",
                    "error_message": "出生日期超出支持范围 (1900-2100)"}
    except (ValueError, TypeError):
        return {"error": True, "error_code": "INVALID_BIRTH_INFO",
                "error_message": "出生日期格式无效，需要 YYYY-MM-DD"}

    try:
        if clock_time:
            h, m = map(int, clock_time.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
    except (ValueError, TypeError):
        return {"error": True, "error_code": "INVALID_BIRTH_INFO",
                "error_message": "时间格式无效，需要 HH:MM"}

    return None


def compute_bazi_from_birth(birth_info):
    """从临时出生信息计算八字 (不走缓存, 不求动态层)"""
    birth_info = _normalize_birth_info(birth_info)
    err = validate_birth_info(birth_info)
    if err:
        return err

    from services.metaphysics.solar_time import correct_solar_time
    from services.metaphysics.bazi.paipan import compute_bazi_static as _bazi

    corrected = correct_solar_time(birth_info)
    return _safe_compute(_bazi, corrected)


def compute_ziwei_from_birth(birth_info):
    """从临时出生信息计算紫微 (不走缓存, 不求动态层)"""
    birth_info = _normalize_birth_info(birth_info)
    err = validate_birth_info(birth_info)
    if err:
        return err

    from services.metaphysics.solar_time import correct_solar_time
    from services.metaphysics.ziwei.paipan import compute_ziwei_static as _ziwei

    corrected = correct_solar_time(birth_info)
    return _safe_compute(_ziwei, corrected)


async def get_full_chart(birth_info):
    """并行排盘: 八字+紫微, asyncio.gather"""
    birth_info = _normalize_birth_info(birth_info)
    err = validate_birth_info(birth_info)
    if err:
        return err

    from services.metaphysics.solar_time import correct_solar_time

    corrected = correct_solar_time(birth_info)
    bazi_static, ziwei_static = await asyncio.gather(
        asyncio.to_thread(compute_bazi_from_birth, corrected),
        asyncio.to_thread(compute_ziwei_from_birth, corrected),
    )
    return {"bazi": bazi_static, "ziwei": ziwei_static}
