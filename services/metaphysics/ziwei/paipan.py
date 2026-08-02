"""Ziwei star placement (手写安星) — 10-step deterministic algorithm (~500 lines)"""
import logging
from datetime import datetime
from lunar_python import Solar

logger = logging.getLogger("metaphysics")

_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

_PALACE_NAMES = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "交友", "官禄", "田宅", "福德", "父母"]

# 命宫起法: (农历月index, 时辰index) → 命宫地支index
_MING_GONG_MAP = {}
for month_idx in range(12):
    for hour_idx in range(12):
        base = (month_idx - 2) % 12
        _MING_GONG_MAP[(month_idx, hour_idx)] = (base - hour_idx) % 12

_YIN_GAN_MAP = {
    "甲": "丙", "己": "丙", "乙": "戊", "庚": "戊",
    "丙": "庚", "辛": "庚", "丁": "壬", "壬": "壬",
    "戊": "甲", "癸": "甲",
}

_NAYIN_FULL = {
    "甲子": "金", "乙丑": "金", "丙寅": "火", "丁卯": "火", "戊辰": "木", "己巳": "木",
    "庚午": "土", "辛未": "土", "壬申": "金", "癸酉": "金",
    "甲戌": "火", "乙亥": "火", "丙子": "水", "丁丑": "水", "戊寅": "土", "己卯": "土",
    "庚辰": "金", "辛巳": "金", "壬午": "木", "癸未": "木",
    "甲申": "水", "乙酉": "水", "丙戌": "土", "丁亥": "土", "戊子": "火", "己丑": "火",
    "庚寅": "木", "辛卯": "木", "壬辰": "水", "癸巳": "水",
    "甲午": "金", "乙未": "金", "丙申": "火", "丁酉": "火", "戊戌": "木", "己亥": "木",
    "庚子": "土", "辛丑": "土", "壬寅": "金", "癸卯": "金",
    "甲辰": "火", "乙巳": "火", "丙午": "水", "丁未": "水", "戊申": "土", "己酉": "土",
    "庚戌": "金", "辛亥": "金", "壬子": "木", "癸丑": "木",
    "甲寅": "水", "乙卯": "水", "丙辰": "土", "丁巳": "土", "戊午": "火", "己未": "火",
    "庚申": "木", "辛酉": "木", "壬戌": "水", "癸亥": "水",
}

_WUXING_JU = {"金": 4, "木": 3, "水": 2, "火": 6, "土": 5}

_ZIWEI_TABLE = {
    2: {1: 0, 2: 11, 3: 10, 4: 9, 5: 8, 6: 7, 7: 6, 8: 5, 9: 4, 10: 3,
        11: 2, 12: 2, 13: 1, 14: 1, 15: 0, 16: 0, 17: 11, 18: 11, 19: 10,
        20: 10, 21: 9, 22: 9, 23: 8, 24: 8, 25: 7, 26: 7, 27: 6, 28: 6, 29: 5, 30: 5},
    3: {1: 0, 2: 10, 3: 8, 4: 7, 5: 5, 6: 4, 7: 2, 8: 2, 9: 1, 10: 0,
        11: 11, 12: 10, 13: 9, 14: 9, 15: 8, 16: 7, 17: 7, 18: 6, 19: 5,
        20: 5, 21: 4, 22: 3, 23: 3, 24: 2, 25: 1, 26: 1, 27: 0, 28: 11, 29: 11, 30: 10},
    4: {1: 0, 2: 9, 3: 6, 4: 4, 5: 1, 6: 0, 7: 10, 8: 9, 9: 8, 10: 7,
        11: 7, 12: 6, 13: 5, 14: 5, 15: 4, 16: 3, 17: 3, 18: 2, 19: 1,
        20: 1, 21: 0, 22: 11, 23: 11, 24: 10, 25: 9, 26: 9, 27: 8, 28: 7, 29: 7, 30: 6},
    5: {1: 0, 2: 8, 3: 4, 4: 1, 5: 9, 6: 6, 7: 3, 8: 1, 9: 11, 10: 9,
        11: 8, 12: 7, 13: 7, 14: 6, 15: 5, 16: 5, 17: 4, 18: 3, 19: 3,
        20: 2, 21: 1, 22: 1, 23: 0, 24: 11, 25: 11, 26: 10, 27: 9, 28: 9, 29: 8, 30: 7},
    6: {1: 0, 2: 7, 3: 2, 4: 10, 5: 5, 6: 0, 7: 7, 8: 2, 9: 11, 10: 7,
        11: 3, 12: 0, 13: 10, 14: 7, 15: 5, 16: 3, 17: 2, 18: 1, 19: 0,
        20: 11, 21: 10, 22: 10, 23: 9, 24: 8, 25: 8, 26: 7, 27: 6, 28: 6, 29: 5, 30: 4},
}

_ZIWEI_SERIES = [
    ("紫微", 0), ("天机", -1), ("", -2), ("太阳", -3),
    ("武曲", -4), ("天同", -5), ("", -6), ("廉贞", -7),
]

_TIANFU_SERIES = [
    ("天府", 0), ("太阴", 1), ("贪狼", 2), ("巨门", 3),
    ("天相", 4), ("天梁", 5), ("七杀", 6), ("破军", 7),
]

_TIANKUI_MAP = {"甲": "丑", "戊": "丑", "庚": "丑",
                "乙": "子", "己": "子",
                "丙": "亥", "丁": "酉",
                "辛": "午", "壬": "巳", "癸": "卯"}

_TIANYUE_MAP = {"甲": "未", "戊": "未", "庚": "未",
                "乙": "申", "己": "申",
                "丙": "酉", "丁": "亥",
                "辛": "寅", "壬": "巳", "癸": "巳"}

_LUCUN_MAP = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午",
              "戊": "巳", "己": "午", "庚": "申", "辛": "酉",
              "壬": "亥", "癸": "子"}

_TIANMA_MAP = {"寅": "申", "午": "申", "戌": "申",
               "申": "寅", "子": "寅", "辰": "寅",
               "巳": "亥", "酉": "亥", "丑": "亥",
               "亥": "巳", "卯": "巳", "未": "巳"}

_HUOXING_BASE = {"寅": "丑", "午": "丑", "戌": "丑",
                 "申": "卯", "子": "卯", "辰": "卯",
                 "巳": "酉", "酉": "酉", "丑": "酉",
                 "亥": "未", "卯": "未", "未": "未"}

_LINGXING_BASE = {"寅": "卯", "午": "卯", "戌": "卯",
                  "申": "戌", "子": "戌", "辰": "戌",
                  "巳": "戌", "酉": "戌", "丑": "戌",
                  "亥": "辰", "卯": "辰", "未": "辰"}

_SIHUA_TABLE = {
    "甲": {"禄": "廉贞", "权": "破军", "科": "武曲", "忌": "太阳"},
    "乙": {"禄": "天机", "权": "天梁", "科": "紫微", "忌": "太阴"},
    "丙": {"禄": "天同", "权": "天机", "科": "文昌", "忌": "廉贞"},
    "丁": {"禄": "太阴", "权": "天同", "科": "天机", "忌": "巨门"},
    "戊": {"禄": "贪狼", "权": "太阴", "科": "右弼", "忌": "天机"},
    "己": {"禄": "武曲", "权": "贪狼", "科": "天梁", "忌": "文曲"},
    "庚": {"禄": "太阳", "权": "武曲", "科": "太阴", "忌": "天同"},
    "辛": {"禄": "巨门", "权": "太阳", "科": "文曲", "忌": "文昌"},
    "壬": {"禄": "天梁", "权": "紫微", "科": "左辅", "忌": "武曲"},
    "癸": {"禄": "破军", "权": "巨门", "科": "太阴", "忌": "贪狼"},
}

_DAXIAN_BASE_AGE = {2: 2, 3: 3, 4: 4, 5: 5, 6: 6}


def _get_ming_gong(lunar_month, birth_hour_zhi):
    month_idx = (lunar_month - 1) % 12
    hour_idx = _ZHI.index(birth_hour_zhi)
    mg_idx = _MING_GONG_MAP.get((month_idx, hour_idx), 2)
    return _ZHI[mg_idx]


def _build_palaces(ming_gong_zhi):
    mg_idx = _ZHI.index(ming_gong_zhi)
    palaces = []
    for i, name in enumerate(_PALACE_NAMES):
        palaces.append({"name": name, "zhi": _ZHI[(mg_idx - i) % 12], "gan": "", "stars": []})
    return palaces


def _set_palace_gans(palaces, year_gan):
    yin_gan = _YIN_GAN_MAP.get(year_gan, "甲")
    yin_gan_idx = _GAN.index(yin_gan)
    for p in palaces:
        zhi_idx = _ZHI.index(p["zhi"])
        offset = (zhi_idx - 2) % 12
        p["gan"] = _GAN[(yin_gan_idx + offset) % 10]
    return palaces


def _get_nayin_wuxing(gan, zhi):
    return _NAYIN_FULL.get(gan + zhi, "土")


def _get_wuxing_ju(ming_palace):
    nayin = _get_nayin_wuxing(ming_palace["gan"], ming_palace["zhi"])
    return _WUXING_JU.get(nayin, 5)


def _place_ziwei(wuxing_ju, lunar_day):
    table = _ZIWEI_TABLE.get(wuxing_ju, {})
    return table.get(lunar_day, 2)


def _place_main_stars(palaces, ziwei_palace_idx):
    for star_name, offset in _ZIWEI_SERIES:
        if not star_name:
            continue
        idx = (ziwei_palace_idx + offset) % 12
        palaces[idx]["stars"].append(star_name)
    tianfu_idx = (4 - ziwei_palace_idx) % 12
    for star_name, offset in _TIANFU_SERIES:
        idx = (tianfu_idx + offset) % 12
        palaces[idx]["stars"].append(star_name)
    return palaces


def _place_fu_xing(palaces, lunar_month, birth_hour_zhi, year_gan, year_zhi):
    hour_idx = _ZHI.index(birth_hour_zhi)
    zuo_fu_idx = (4 + lunar_month - 1) % 12
    palaces[zuo_fu_idx]["stars"].append("左辅")
    you_bi_idx = (10 - (lunar_month - 1)) % 12
    palaces[you_bi_idx]["stars"].append("右弼")
    wc_idx = (10 - hour_idx) % 12
    palaces[wc_idx]["stars"].append("文昌")
    wq_idx = (4 + hour_idx) % 12
    palaces[wq_idx]["stars"].append("文曲")
    tk_zhi = _TIANKUI_MAP.get(year_gan, "丑")
    palaces[_ZHI.index(tk_zhi)]["stars"].append("天魁")
    ty_zhi = _TIANYUE_MAP.get(year_gan, "未")
    palaces[_ZHI.index(ty_zhi)]["stars"].append("天钺")
    lc_zhi = _LUCUN_MAP.get(year_gan, "寅")
    palaces[_ZHI.index(lc_zhi)]["stars"].append("禄存")
    tm_zhi = _TIANMA_MAP.get(year_zhi, "寅")
    palaces[_ZHI.index(tm_zhi)]["stars"].append("天马")
    return palaces


def _place_sha_xing(palaces, year_gan, year_zhi, birth_hour_zhi):
    hour_idx = _ZHI.index(birth_hour_zhi)
    lc_zhi = _LUCUN_MAP.get(year_gan, "寅")
    qingyang_idx = (_ZHI.index(lc_zhi) + 1) % 12
    palaces[qingyang_idx]["stars"].append("擎羊")
    tuoluo_idx = (_ZHI.index(lc_zhi) - 1) % 12
    palaces[tuoluo_idx]["stars"].append("陀罗")
    hx_base = _HUOXING_BASE.get(year_zhi, "丑")
    hx_idx = (_ZHI.index(hx_base) + hour_idx) % 12
    palaces[hx_idx]["stars"].append("火星")
    lx_base = _LINGXING_BASE.get(year_zhi, "卯")
    lx_idx = (_ZHI.index(lx_base) + hour_idx) % 12
    palaces[lx_idx]["stars"].append("铃星")
    dk_idx = (10 - hour_idx) % 12
    palaces[dk_idx]["stars"].append("地空")
    dj_idx = (10 + hour_idx) % 12
    palaces[dj_idx]["stars"].append("地劫")
    return palaces


def _si_hua_for_stars(year_gan, palaces):
    sihua_map = _SIHUA_TABLE.get(year_gan, {})
    result = {"禄": {}, "权": {}, "科": {}, "忌": {}}
    for hua_type, star_name in sihua_map.items():
        for i, p in enumerate(palaces):
            if star_name in p["stars"]:
                result[hua_type] = {"star": star_name, "palace": p["name"], "zhi": p["zhi"], "idx": i}
                star_list = p["stars"]
                idx = star_list.index(star_name)
                star_list[idx] = f"{star_name}[{hua_type}]"
                break
    return result


def _pai_da_xian(palaces, wuxing_ju, gender):
    base_age = _DAXIAN_BASE_AGE.get(wuxing_ju, 5)
    is_male = gender in ("男", "male", "m")
    da_xian = []
    for i in range(12):
        start_age = base_age + i * 10
        if is_male:
            p = palaces[i]
        else:
            p = palaces[(12 - i) % 12]
        da_xian.append({
            "palace": p["name"],
            "zhi": p["zhi"],
            "gan": p["gan"],
            "start_age": start_age,
            "end_age": start_age + 9,
            "stars": [s for s in p["stars"] if "[" not in s],
        })
    return da_xian


def _find_current_daxian(ziwei_static, current_age=None):
    if current_age is None:
        birth_date = datetime.strptime(
            ziwei_static.get("birth", {}).get("solar_date", "2000-01-01"), "%Y-%m-%d")
        today = datetime.now()
        current_age = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            current_age -= 1
    da_xian = ziwei_static.get("static", {}).get("da_xian", [])
    for dx in da_xian:
        if dx["start_age"] <= current_age <= dx["end_age"]:
            return dx
    return da_xian[0] if da_xian else None


def compute_ziwei_static(birth_info):
    """紫微斗数静态排盘 — 10步算法"""
    solar_date = birth_info.get("solar_date", "2000-01-01")
    clock_time = birth_info.get("clock_time", "12:00")
    gender = birth_info.get("gender", "女")

    dt = datetime.strptime(f"{solar_date} {clock_time}", "%Y-%m-%d %H:%M")
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()

    lunar_month = lunar.getMonth()
    lunar_day = lunar.getDay()
    birth_hour_zhi = _ZHI[((dt.hour + 1) // 2) % 12]

    year_gan = lunar.getYearGan()
    year_zhi = lunar.getYearZhi()

    ming_gong_zhi = _get_ming_gong(lunar_month, birth_hour_zhi)
    palaces = _build_palaces(ming_gong_zhi)
    palaces = _set_palace_gans(palaces, year_gan)
    wuxing_ju = _get_wuxing_ju(palaces[0])
    ziwei_palace_idx = _place_ziwei(wuxing_ju, lunar_day)
    palaces = _place_main_stars(palaces, ziwei_palace_idx)
    palaces = _place_fu_xing(palaces, lunar_month, birth_hour_zhi, year_gan, year_zhi)
    palaces = _place_sha_xing(palaces, year_gan, year_zhi, birth_hour_zhi)
    sihua = _si_hua_for_stars(year_gan, palaces)
    da_xian = _pai_da_xian(palaces, wuxing_ju, gender)

    return {
        "birth": birth_info,
        "static": {
            "ming_gong": palaces[0],
            "palaces": palaces,
            "wuxing_ju": wuxing_ju,
            "sihua": sihua,
            "da_xian": da_xian,
        },
    }


def compute_ziwei_dynamic(ziwei_static):
    """紫微动态层: 当前大限/流年/流月/流日"""
    today = datetime.now()
    birth_info = ziwei_static.get("birth", {})
    clock_time = birth_info.get("clock_time", "12:00")
    hour, _ = map(int, clock_time.split(":"))
    birth_hour_zhi = _ZHI[((hour + 1) // 2) % 12]

    solar = Solar.fromYmd(today.year, today.month, today.day)
    lunar = solar.getLunar()

    dou_jun_idx = (2 - _ZHI.index(birth_hour_zhi)) % 12
    liunian_ming_idx = (dou_jun_idx + lunar.getMonth() - 1) % 12
    liuyue_ming_idx = (liunian_ming_idx + lunar.getMonth() - 1) % 12
    liuri_ming_idx = (liuyue_ming_idx + lunar.getDay() - 1) % 12

    palaces = ziwei_static.get("static", {}).get("palaces", [])

    return {
        "current": {
            "dayun": _find_current_daxian(ziwei_static),
            "liunian": palaces[liunian_ming_idx] if palaces else {"name": "?"},
            "liuyue": palaces[liuyue_ming_idx] if palaces else {"name": "?"},
            "liuri": palaces[liuri_ming_idx] if palaces else {"name": "?"},
        }
    }
