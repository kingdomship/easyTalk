"""BaZi geju (格局) analysis — 月令取格 + 旺衰 + 调候 + 病药"""
import logging

logger = logging.getLogger("metaphysics")

_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

_MONTH_MAIN_QI = {
    "寅": "甲", "卯": "乙", "辰": "戊", "巳": "丙",
    "午": "丁", "未": "己", "申": "庚", "酉": "辛",
    "戌": "戊", "亥": "壬", "子": "癸", "丑": "己",
}

_TEN_GOD_TO_GEJU = {
    "正官": "正官格", "七杀": "七杀格", "正印": "正印格",
    "偏印": "偏印格", "正财": "正财格", "偏财": "偏财格",
    "食神": "食神格", "伤官": "伤官格", "比肩": "建禄格", "劫财": "月刃格",
}

_GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

_WUXING_RELATION = {
    "木": {"木": 1.0, "火": 0.7, "土": 0.3, "金": 0.1, "水": 0.8},
    "火": {"木": 0.8, "火": 1.0, "土": 0.7, "金": 0.3, "水": 0.1},
    "土": {"木": 0.3, "火": 0.8, "土": 1.0, "金": 0.7, "水": 0.3},
    "金": {"木": 0.1, "火": 0.3, "土": 0.8, "金": 1.0, "水": 0.7},
    "水": {"木": 0.7, "火": 0.1, "土": 0.3, "金": 0.8, "水": 1.0},
}

# 五行生克
_WUXING_SHENG = {"木": "水", "火": "木", "土": "火", "金": "土", "水": "金"}
_WUXING_KE = {"木": "金", "火": "水", "土": "木", "金": "火", "水": "土"}


def _get_ten_god_from_map(day_gan, other_gan):
    """从 paipan 的十神映射表获取关系"""
    from services.metaphysics.bazi.paipan import _get_ten_god
    return _get_ten_god(day_gan, other_gan)


def _get_season_strength(day_master, month_zhi):
    """月令旺相休囚死评分"""
    wuxing = _GAN_WUXING.get(day_master, "木")
    season_map = {
        "寅": "木", "卯": "木", "辰": "土",
        "巳": "火", "午": "火", "未": "土",
        "申": "金", "酉": "金", "戌": "土",
        "亥": "水", "子": "水", "丑": "土",
    }
    season = season_map.get(month_zhi, "木")
    return _WUXING_RELATION.get(wuxing, {}).get(season, 0.5)


def _get_earth_strength(day_master, hidden_stems):
    """地支藏干得地评分"""
    wuxing = _GAN_WUXING.get(day_master, "木")
    all_stems = []
    for stems in hidden_stems.values():
        all_stems.extend(stems)
    if not all_stems:
        return 0.3
    match_count = sum(1 for s in all_stems if _GAN_WUXING.get(s) == wuxing)
    return min(1.0, 0.3 + match_count / max(len(all_stems), 1))


def _get_heaven_strength(day_master, pillars):
    """天干比劫得势评分"""
    wuxing = _GAN_WUXING.get(day_master, "木")
    gans = [p.get("gan", "") for p in pillars.values() if p.get("gan")]
    same_count = sum(1 for g in gans if _GAN_WUXING.get(g) == wuxing)
    return min(1.0, same_count / 4)


def _get_tiao_hou(month_zhi):
    """调候需求: 夏用水, 冬用火"""
    if month_zhi in ("巳", "午", "未"):
        return "夏月出生，需水调候"
    elif month_zhi in ("亥", "子", "丑"):
        return "冬月出生，需火调候"
    return "无需特别调候"


def _get_bing_yao(day_master, wuxing_count, geju_type):
    """病药分析: 最强忌神 + 可制之药"""
    wx = _GAN_WUXING.get(day_master, "木")
    ke_day = _WUXING_KE.get(wx, "")  # 克日主的五行

    max_wx = max(wuxing_count, key=wuxing_count.get)
    if ke_day and wuxing_count.get(ke_day, 0) > 0.5:
        yao = _WUXING_KE.get(ke_day, "")
        return {
            "ji_shen": f"{ke_day}旺为忌",
            "yao": f"以{yao}制{ke_day}" if yao else "调和为宜",
        }
    return {"ji_shen": "无明显忌神", "yao": "中和为上"}


def analyze_geju(bazi_static):
    """子平法格局分析"""
    static = bazi_static.get("static", {})
    pillars = static.get("four_pillars", {})
    day_master = static.get("day_master", "甲")
    month_zhi = pillars.get("month", {}).get("zhi", "子")

    main_qi = _MONTH_MAIN_QI.get(month_zhi, "甲")
    main_ten_god = _get_ten_god_from_map(day_master, main_qi)
    geju_type = _TEN_GOD_TO_GEJU.get(main_ten_god, "正格")

    season_strength = _get_season_strength(day_master, month_zhi)
    earth_strength = _get_earth_strength(day_master, static.get("hidden_stems", {}))
    heaven_strength = _get_heaven_strength(day_master, pillars)

    total = season_strength * 0.4 + earth_strength * 0.35 + heaven_strength * 0.25
    if total > 0.55:
        strength = "身强"
    elif total < 0.35:
        strength = "身弱"
    else:
        strength = "中和"

    tiao_hou = _get_tiao_hou(month_zhi)
    wuxing_count = static.get("wuxing_count", {})
    bing_yao = _get_bing_yao(day_master, wuxing_count, geju_type)

    # 格局层次
    if geju_type in ("正官格", "正印格", "食神格") and strength in ("身强", "中和"):
        level = "中上"
    elif geju_type in ("七杀格", "伤官格", "月刃格") and strength == "身弱":
        level = "中下"
    else:
        level = "中"

    return {
        "type": geju_type,
        "strength": strength,
        "tiao_hou": tiao_hou,
        "bing_yao": bing_yao,
        "level": level,
        "score_breakdown": {
            "season": round(season_strength, 2),
            "earth": round(earth_strength, 2),
            "heaven": round(heaven_strength, 2),
            "total": round(total, 2),
        },
    }
