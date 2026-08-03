"""BaZi hehun (合婚) — 天干五合 + 纳音生克 + 十神互补 + 五行互补"""
import logging

logger = logging.getLogger("metaphysics")

# 天干五合: (甲己)/(乙庚)/(丙辛)/(丁壬)/(戊癸)
_GAN_HE = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛",
           "辛": "丙", "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}

# 地支六合
_ZHI_HE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌",
           "戌": "卯", "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}

# 纳音五行生克评分
_NAYIN_SCORE = {
    ("金", "水"): 10, ("水", "木"): 10, ("木", "火"): 10, ("火", "土"): 10, ("土", "金"): 10,
    ("金", "木"): -5, ("木", "土"): -5, ("土", "水"): -5, ("水", "火"): -5, ("火", "金"): -5,
}

# 十神互补对
_SHISHEN_PAIR = {
    ("正官", "正印"): 8, ("七杀", "食神"): 8, ("正财", "正官"): 7,
    ("食神", "正财"): 7, ("正印", "比肩"): 6, ("偏财", "伤官"): 6,
}


def compute_hehun(self_bazi: dict, other_bazi: dict) -> dict:
    """Compute bazi hehun compatibility score and analysis."""
    self_s = self_bazi.get("static", {})
    other_s = other_bazi.get("static", {})

    self_pillars = self_s.get("four_pillars", {})
    other_pillars = other_s.get("four_pillars", {})

    score = 50  # baseline

    # 1. 天干五合检查 (年柱+日柱)
    ganzhi_he = []
    for key in ["year", "day"]:
        sg = self_pillars.get(key, {}).get("gan", "")
        og = other_pillars.get(key, {}).get("gan", "")
        if _GAN_HE.get(sg) == og:
            ganzhi_he.append(key + "柱天干合: " + sg + og)
            score += 10
        sz = self_pillars.get(key, {}).get("zhi", "")
        oz = other_pillars.get(key, {}).get("zhi", "")
        if _ZHI_HE.get(sz) == oz:
            ganzhi_he.append(key + "柱地支合: " + sz + oz)
            score += 8

    # 2. 纳音生克
    self_nayin = self_s.get("nayin", {})
    other_nayin = other_s.get("nayin", {})
    nayan_relation = ""
    for key in ["year", "day"]:
        sn = _nayin_to_wuxing(self_nayin.get(key, ""))
        on_ = _nayin_to_wuxing(other_nayin.get(key, ""))
        pair = (sn, on_)
        for (a, b), v in _NAYIN_SCORE.items():
            if a in sn and b in on_:
                score += v
                nayan_relation = key + "柱纳音: " + self_nayin.get(key, "?") + "(" + sn + ") vs " + other_nayin.get(key, "?") + "(" + on_ + ") → " + ("相生" if v > 0 else "相克")
                break

    # 3. 十神互补
    self_ten = self_s.get("ten_gods_gan", {})
    other_ten = other_s.get("ten_gods_gan", {})
    shishen_complement = ""
    for key in ["month", "day"]:
        st = self_ten.get(key, "")
        ot = other_ten.get(key, "")
        for (a, b), v in _SHISHEN_PAIR.items():
            if (st == a and ot == b) or (st == b and ot == a):
                score += v
                shishen_complement = key + "柱十神互补: " + st + "↔" + ot
                break

    # 4. 五行互补
    self_wux = _count_wuxing(self_pillars, self_s.get("hidden_stems", {}))
    other_wux = _count_wuxing(other_pillars, other_s.get("hidden_stems", {}))
    wuxing_balance = ""
    for wx in ["金","木","水","火","土"]:
        if self_wux.get(wx, 0) < 2 and other_wux.get(wx, 0) > 4:
            wuxing_balance = "对方" + wx + "旺补本人" + wx + "弱"
            score += 5
        elif other_wux.get(wx, 0) < 2 and self_wux.get(wx, 0) > 4:
            wuxing_balance = "本人" + wx + "旺补对方" + wx + "弱"
            score += 5

    return {
        "compatibility_score": min(100, max(0, score)),
        "nayan_relation": nayan_relation,
        "ganzhi_he": ganzhi_he,
        "shishen_complement": shishen_complement,
        "wuxing_balance": wuxing_balance,
    }


def _nayin_to_wuxing(nayin: str) -> str:
    for wx in ["金", "木", "水", "火", "土"]:
        if wx in nayin:
            return wx
    return "土"


def _count_wuxing(pillars: dict, hidden_stems: dict) -> dict:
    """Count five elements distribution (simplified)."""
    wuxing_gan = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
                  "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
    wuxing_zhi = {"寅": "木", "卯": "木", "巳": "火", "午": "火",
                  "申": "金", "酉": "金", "亥": "水", "子": "水",
                  "辰": "土", "戌": "土", "丑": "土", "未": "土"}
    counts = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
    for key in ["year", "month", "day", "time"]:
        p = pillars.get(key, {})
        wx = wuxing_gan.get(p.get("gan", ""), "")
        if wx:
            counts[wx] += 1
        wx2 = wuxing_zhi.get(p.get("zhi", ""), "")
        if wx2:
            counts[wx2] += 1
    return counts
