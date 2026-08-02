"""BaZi paipan: four pillars, ten gods, hidden stems, nayin, dayun, liunian, shensha."""
import logging
from datetime import datetime, date
from lunar_python import Solar

logger = logging.getLogger("metaphysics")

# 六十甲子纳音表
_NAYIN_TABLE = {
    "甲子": "海中金", "乙丑": "海中金", "丙寅": "炉中火", "丁卯": "炉中火",
    "戊辰": "大林木", "己巳": "大林木", "庚午": "路旁土", "辛未": "路旁土",
    "壬申": "剑锋金", "癸酉": "剑锋金", "甲戌": "山头火", "乙亥": "山头火",
    "丙子": "涧下水", "丁丑": "涧下水", "戊寅": "城头土", "己卯": "城头土",
    "庚辰": "白蜡金", "辛巳": "白蜡金", "壬午": "杨柳木", "癸未": "杨柳木",
    "甲申": "泉中水", "乙酉": "泉中水", "丙戌": "屋上土", "丁亥": "屋上土",
    "戊子": "霹雳火", "己丑": "霹雳火", "庚寅": "松柏木", "辛卯": "松柏木",
    "壬辰": "长流水", "癸巳": "长流水", "甲午": "沙中金", "乙未": "沙中金",
    "丙申": "山下火", "丁酉": "山下火", "戊戌": "平地木", "己亥": "平地木",
    "庚子": "壁上土", "辛丑": "壁上土", "壬寅": "金箔金", "癸卯": "金箔金",
    "甲辰": "覆灯火", "乙巳": "覆灯火", "丙午": "天河水", "丁未": "天河水",
    "戊申": "大驿土", "己酉": "大驿土", "庚戌": "钗钏金", "辛亥": "钗钏金",
    "壬子": "桑柘木", "癸丑": "桑柘木", "甲寅": "大溪水", "乙卯": "大溪水",
    "丙辰": "沙中土", "丁巳": "沙中土", "戊午": "天上火", "己未": "天上火",
    "庚申": "石榴木", "辛酉": "石榴木", "壬戌": "大海水", "癸亥": "大海水",
}

# 12地支藏干表（本气/中气/余气）
_HIDDEN_STEMS = {
    "子": ["癸"],
    "丑": ["己", "癸", "辛"],
    "寅": ["甲", "丙", "戊"],
    "卯": ["乙"],
    "辰": ["戊", "乙", "癸"],
    "巳": ["丙", "庚", "戊"],
    "午": ["丁", "己"],
    "未": ["己", "丁", "乙"],
    "申": ["庚", "壬", "戊"],
    "酉": ["辛"],
    "戌": ["戊", "辛", "丁"],
    "亥": ["壬", "甲"],
}

# 天干十神关系 (日干 vs 他干) — 完整10天干
_TEN_GOD_MAP = {
    "甲": {"甲": "比肩", "乙": "劫财", "丙": "食神", "丁": "伤官",
           "戊": "偏财", "己": "正财", "庚": "七杀", "辛": "正官", "壬": "偏印", "癸": "正印"},
    "乙": {"甲": "劫财", "乙": "比肩", "丙": "伤官", "丁": "食神",
           "戊": "正财", "己": "偏财", "庚": "正官", "辛": "七杀", "壬": "正印", "癸": "偏印"},
    "丙": {"甲": "偏印", "乙": "正印", "丙": "比肩", "丁": "劫财",
           "戊": "食神", "己": "伤官", "庚": "偏财", "辛": "正财", "壬": "七杀", "癸": "正官"},
    "丁": {"甲": "正印", "乙": "偏印", "丙": "劫财", "丁": "比肩",
           "戊": "伤官", "己": "食神", "庚": "正财", "辛": "偏财", "壬": "正官", "癸": "七杀"},
    "戊": {"甲": "七杀", "乙": "正官", "丙": "偏印", "丁": "正印",
           "戊": "比肩", "己": "劫财", "庚": "食神", "辛": "伤官", "壬": "偏财", "癸": "正财"},
    "己": {"甲": "正官", "乙": "七杀", "丙": "正印", "丁": "偏印",
           "戊": "劫财", "己": "比肩", "庚": "伤官", "辛": "食神", "壬": "正财", "癸": "偏财"},
    "庚": {"甲": "偏财", "乙": "正财", "丙": "七杀", "丁": "正官",
           "戊": "偏印", "己": "正印", "庚": "比肩", "辛": "劫财", "壬": "食神", "癸": "伤官"},
    "辛": {"甲": "正财", "乙": "偏财", "丙": "正官", "丁": "七杀",
           "戊": "正印", "己": "偏印", "庚": "劫财", "辛": "比肩", "壬": "伤官", "癸": "食神"},
    "壬": {"甲": "食神", "乙": "伤官", "丙": "偏财", "丁": "正财",
           "戊": "七杀", "己": "正官", "庚": "偏印", "辛": "正印", "壬": "比肩", "癸": "劫财"},
    "癸": {"甲": "伤官", "乙": "食神", "丙": "正财", "丁": "偏财",
           "戊": "正官", "己": "七杀", "庚": "正印", "辛": "偏印", "壬": "劫财", "癸": "比肩"},
}

# 天干/地支列表
_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 旬空表: 日柱干支 → 空亡地支对
_XUN_KONG_TABLE = {}
_xun_groups = [
    (["甲子", "乙丑", "丙寅", "丁卯", "戊辰", "己巳", "庚午", "辛未", "壬申", "癸酉"], ("戌", "亥")),
    (["甲戌", "乙亥", "丙子", "丁丑", "戊寅", "己卯", "庚辰", "辛巳", "壬午", "癸未"], ("申", "酉")),
    (["甲申", "乙酉", "丙戌", "丁亥", "戊子", "己丑", "庚寅", "辛卯", "壬辰", "癸巳"], ("午", "未")),
    (["甲午", "乙未", "丙申", "丁酉", "戊戌", "己亥", "庚子", "辛丑", "壬寅", "癸卯"], ("辰", "巳")),
    (["甲辰", "乙巳", "丙午", "丁未", "戊申", "己酉", "庚戌", "辛亥", "壬子", "癸丑"], ("寅", "卯")),
    (["甲寅", "乙卯", "丙辰", "丁巳", "戊午", "己未", "庚申", "辛酉", "壬戌", "癸亥"], ("子", "丑")),
]
for _group, _kong in _xun_groups:
    for _gz in _group:
        _XUN_KONG_TABLE[_gz] = _kong

# 神煞表 (日干查)
_SHENSHA_BY_DAY_GAN = {
    "甲": {"天乙贵人": ["丑", "未"], "太极贵人": ["子", "午"], "文昌": "巳", "羊刃": "卯"},
    "乙": {"天乙贵人": ["子", "申"], "太极贵人": ["子", "午"], "文昌": "午", "羊刃": "寅"},
    "丙": {"天乙贵人": ["亥", "酉"], "太极贵人": ["卯", "酉"], "文昌": "申", "羊刃": "午"},
    "丁": {"天乙贵人": ["亥", "酉"], "太极贵人": ["卯", "酉"], "文昌": "酉", "羊刃": "巳"},
    "戊": {"天乙贵人": ["丑", "未"], "太极贵人": ["辰", "戌"], "文昌": "申", "羊刃": "午"},
    "己": {"天乙贵人": ["子", "申"], "太极贵人": ["辰", "戌"], "文昌": "酉", "羊刃": "巳"},
    "庚": {"天乙贵人": ["丑", "未"], "太极贵人": ["寅", "亥"], "文昌": "亥", "羊刃": "酉"},
    "辛": {"天乙贵人": ["午", "寅"], "太极贵人": ["寅", "亥"], "文昌": "子", "羊刃": "申"},
    "壬": {"天乙贵人": ["卯", "巳"], "太极贵人": ["巳", "卯"], "文昌": "寅", "羊刃": "子"},
    "癸": {"天乙贵人": ["卯", "巳"], "太极贵人": ["巳", "卯"], "文昌": "卯", "羊刃": "亥"},
}

# 神煞表 (日支/年支查)
_SHENSHA_BY_ZHI = {
    "子": {"桃花": "酉", "驿马": "寅", "华盖": "辰"},
    "丑": {"桃花": "午", "驿马": "亥", "华盖": "丑"},
    "寅": {"桃花": "卯", "驿马": "申", "华盖": "戌"},
    "卯": {"桃花": "子", "驿马": "巳", "华盖": "未"},
    "辰": {"桃花": "酉", "驿马": "寅", "华盖": "辰"},
    "巳": {"桃花": "午", "驿马": "亥", "华盖": "丑"},
    "午": {"桃花": "卯", "驿马": "申", "华盖": "戌"},
    "未": {"桃花": "子", "驿马": "巳", "华盖": "未"},
    "申": {"桃花": "酉", "驿马": "寅", "华盖": "辰"},
    "酉": {"桃花": "午", "驿马": "亥", "华盖": "丑"},
    "戌": {"桃花": "卯", "驿马": "申", "华盖": "戌"},
    "亥": {"桃花": "子", "驿马": "巳", "华盖": "未"},
}


def _get_nayin(gan, zhi):
    return _NAYIN_TABLE.get(gan + zhi, "未知")


def _get_hidden_stems(zhi):
    return _HIDDEN_STEMS.get(zhi, [])


def _get_ten_god(day_gan, other_gan):
    return _TEN_GOD_MAP.get(day_gan, {}).get(other_gan, "?")


def _get_xun_kong(gan, zhi):
    return list(_XUN_KONG_TABLE.get(gan + zhi, ("?", "?")))


def _get_shensha(day_gan, day_zhi, year_zhi, all_zhi):
    """综合查神煞"""
    result = {}
    day_gan_sha = _SHENSHA_BY_DAY_GAN.get(day_gan, {})
    for sha_name, zhi_val in day_gan_sha.items():
        if isinstance(zhi_val, list):
            for z in zhi_val:
                if z in all_zhi:
                    result.setdefault(sha_name, []).append(z)
        elif zhi_val in all_zhi:
            result.setdefault(sha_name, []).append(zhi_val)

    day_zhi_sha = _SHENSHA_BY_ZHI.get(day_zhi, {})
    for sha_name, zhi_val in day_zhi_sha.items():
        if zhi_val in all_zhi:
            result.setdefault(sha_name, []).append(zhi_val)

    year_zhi_sha = _SHENSHA_BY_ZHI.get(year_zhi, {})
    for sha_name, zhi_val in year_zhi_sha.items():
        if sha_name not in result and zhi_val in all_zhi:
            result.setdefault(sha_name, []).append(zhi_val)

    return result


def _find_current_dayun(da_yun_list, current_age):
    if not da_yun_list:
        return None
    if current_age < da_yun_list[0].getStartAge():
        return _dayun_to_dict(da_yun_list[0])
    current = None
    for dy in da_yun_list:
        if dy.getStartAge() <= current_age:
            current = dy
    return _dayun_to_dict(current) if current else None


def _dayun_to_dict(dy):
    return {
        "start_age": dy.getStartAge(),
        "gan": dy.getGanZhi()[0],
        "zhi": dy.getGanZhi()[1],
        "liunian": [],
    }


def compute_bazi_static(birth_info):
    """计算八字静态层: 四柱/十神/藏干/纳音/空亡/神煞"""
    from services.metaphysics.solar_time import normalize_gender

    solar_date = birth_info["solar_date"]
    clock_time = birth_info["clock_time"]
    gender = normalize_gender(birth_info.get("gender", "女"))

    dt = datetime.strptime(f"{solar_date} {clock_time}", "%Y-%m-%d %H:%M")
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()
    ba_zi = lunar.getEightChar()

    year_gan = ba_zi.getYearGan()
    year_zhi = ba_zi.getYearZhi()
    month_gan = ba_zi.getMonthGan()
    month_zhi = ba_zi.getMonthZhi()
    day_gan = ba_zi.getDayGan()
    day_zhi = ba_zi.getDayZhi()
    time_gan = ba_zi.getTimeGan()
    time_zhi = ba_zi.getTimeZhi()

    day_master = day_gan

    ten_gods_gan = {
        "year": _get_ten_god(day_master, year_gan),
        "month": _get_ten_god(day_master, month_gan),
        "day": "日主",
        "time": _get_ten_god(day_master, time_gan),
    }

    hidden_stems = {}
    ten_gods_zhi = {}
    for label, zhi in [("year", year_zhi), ("month", month_zhi), ("day", day_zhi), ("time", time_zhi)]:
        stems = _get_hidden_stems(zhi)
        hidden_stems[label] = stems
        ten_gods_zhi[label] = [_get_ten_god(day_master, s) for s in stems]

    nayin = {
        "year": _get_nayin(year_gan, year_zhi),
        "month": _get_nayin(month_gan, month_zhi),
        "day": _get_nayin(day_gan, day_zhi),
        "time": _get_nayin(time_gan, time_zhi),
    }

    all_zhi = [year_zhi, month_zhi, day_zhi, time_zhi]
    shensha = _get_shensha(day_gan, day_zhi, year_zhi, all_zhi)

    xun_kong = {
        "day": _get_xun_kong(day_gan, day_zhi),
    }

    yun = ba_zi.getYun(gender)
    da_yun_list = yun.getDaYun()
    start_age = da_yun_list[0].getStartAge() if da_yun_list else 0

    # 五行统计 (加权)
    wuxing_count = {"木": 0.0, "火": 0.0, "土": 0.0, "金": 0.0, "水": 0.0}
    _gan_wuxing = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
                   "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
    _zhi_main_wuxing = {"寅": "木", "卯": "木", "巳": "火", "午": "火",
                        "辰": "土", "戌": "土", "丑": "土", "未": "土",
                        "申": "金", "酉": "金", "亥": "水", "子": "水"}
    for gan in [year_gan, month_gan, day_gan, time_gan]:
        wx = _gan_wuxing.get(gan, "")
        if wx:
            wuxing_count[wx] += 1.0
    for zhi, label in [(year_zhi, "year"), (month_zhi, "month"), (day_zhi, "day"), (time_zhi, "time")]:
        h_stems = hidden_stems.get(label, [])
        wx_main = _zhi_main_wuxing.get(zhi, "")
        if h_stems and wx_main:
            wuxing_count[wx_main] += 1.0  # 本气
            if len(h_stems) > 1:
                wx2 = _gan_wuxing.get(h_stems[1], "")
                if wx2:
                    wuxing_count[wx2] += 0.5  # 中气
            if len(h_stems) > 2:
                wx3 = _gan_wuxing.get(h_stems[2], "")
                if wx3:
                    wuxing_count[wx3] += 0.3  # 余气

    static = {
        "four_pillars": {
            "year": {"gan": year_gan, "zhi": year_zhi},
            "month": {"gan": month_gan, "zhi": month_zhi},
            "day": {"gan": day_gan, "zhi": day_zhi},
            "time": {"gan": time_gan, "zhi": time_zhi},
        },
        "day_master": day_master,
        "ten_gods_gan": ten_gods_gan,
        "ten_gods_zhi": ten_gods_zhi,
        "hidden_stems": hidden_stems,
        "nayin": nayin,
        "xun_kong": xun_kong,
        "shensha": shensha,
        "wuxing_count": wuxing_count,
        "yun_start_age": start_age,
    }

    return {
        "birth": birth_info,
        "static": static,
    }


def compute_bazi_dynamic(bazi_static):
    """计算八字动态层: 当前大运/流年/流月/流日"""
    today = date.today()
    current_age = today.year - datetime.strptime(
        bazi_static["birth"]["solar_date"], "%Y-%m-%d"
    ).year

    solar = Solar.fromYmd(today.year, today.month, today.day)
    lunar = solar.getLunar()
    ba_zi = lunar.getEightChar()

    birth_date = datetime.strptime(bazi_static["birth"]["solar_date"], "%Y-%m-%d")
    birth_solar = Solar.fromYmdHms(birth_date.year, birth_date.month, birth_date.day,
                                   birth_date.hour, birth_date.minute, 0)
    birth_lunar = birth_solar.getLunar()
    birth_ba_zi = birth_lunar.getEightChar()
    from services.metaphysics.solar_time import normalize_gender
    gender = normalize_gender(bazi_static["birth"].get("gender", "女"))
    yun = birth_ba_zi.getYun(gender)
    da_yun_list = yun.getDaYun()

    current_dayun = _find_current_dayun(da_yun_list, current_age)

    liunian_gan = ba_zi.getYearGan()
    liunian_zhi = ba_zi.getYearZhi()
    liunian_ten_god = _get_ten_god(bazi_static["static"]["day_master"], liunian_gan)

    liuyue_gan = ba_zi.getMonthGan()
    liuyue_zhi = ba_zi.getMonthZhi()

    liuri_gan = ba_zi.getDayGan()
    liuri_zhi = ba_zi.getDayZhi()
    liuri_ten_god = _get_ten_god(bazi_static["static"]["day_master"], liuri_gan)

    return {
        "current": {
            "dayun": current_dayun,
            "liunian": {"gan": liunian_gan, "zhi": liunian_zhi, "ten_god": liunian_ten_god},
            "liuyue": {"gan": liuyue_gan, "zhi": liuyue_zhi},
            "liuri": {"gan": liuri_gan, "zhi": liuri_zhi, "ten_god": liuri_ten_god},
        }
    }


def _get_liuri_relation(day_master, liuri_gan):
    """日主 vs 流日干 → 关系描述"""
    ten_god = _get_ten_god(day_master, liuri_gan)
    mapping = {
        "比肩": "同类相助",
        "劫财": "竞争多变",
        "食神": "轻松愉悦",
        "伤官": "创意敏锐",
        "正财": "稳定务实",
        "偏财": "意外之喜",
        "正官": "规整有序",
        "七杀": "压力挑战",
        "正印": "静心学习",
        "偏印": "独处思考",
    }
    return mapping.get(ten_god, "平稳")


def _get_today_ganzhi():
    """获取今日干支"""
    today = date.today()
    solar = Solar.fromYmd(today.year, today.month, today.day)
    lunar = solar.getLunar()
    ba_zi = lunar.getEightChar()
    return ba_zi.getDayGan() + ba_zi.getDayZhi()
