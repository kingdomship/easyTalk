"""Ziwei hepan (合盘) — 主星互动 + 夫妻宫飞化交叉 + 大限同步度"""
import logging

logger = logging.getLogger("metaphysics")


def compute_hepan(ziwei_self, ziwei_other):
    """紫微合盘分析 (纯数据，不调LLM)

    Args:
        ziwei_self: 自己的紫微静态命盘
        ziwei_other: 对方的紫微静态命盘

    Returns:
        {compatibility_summary, star_interactions, couple_palace_flying, daxian_sync}
    """
    self_palaces = ziwei_self.get("static", {}).get("palaces", [])
    other_palaces = ziwei_other.get("static", {}).get("palaces", [])

    if not self_palaces or not other_palaces:
        return {"error": True, "error_code": "INCOMPLETE_CHART",
                "error_message": "命盘数据不完整"}

    # 主星互动
    star_interactions = _analyze_star_interactions(self_palaces, other_palaces)

    # 夫妻宫飞化交叉
    couple_flying = _analyze_couple_flying(self_palaces, other_palaces)

    # 大限同步度
    daxian_sync = _analyze_daxian_sync(ziwei_self, ziwei_other)

    return {
        "star_interactions": star_interactions,
        "couple_flying": couple_flying,
        "daxian_sync": daxian_sync,
    }


def _get_palace_by_name(palaces, name):
    for p in palaces:
        if p["name"] == name:
            return p
    return None


def _get_all_stars(palace):
    stars = []
    for s in palace.get("stars", []):
        clean = s.split("[")[0]
        if clean:
            stars.append(clean)
    return stars


def _analyze_star_interactions(self_palaces, other_palaces):
    """主星互动: 双方命宫/夫妻宫主星的和谐度"""
    self_ming = _get_palace_by_name(self_palaces, "命宫")
    other_ming = _get_palace_by_name(other_palaces, "命宫")
    self_fuqi = _get_palace_by_name(self_palaces, "夫妻")
    other_fuqi = _get_palace_by_name(other_palaces, "夫妻")

    # 和谐星组
    _harmony_pairs = [
        ({"紫微", "天府"}, "帝王配"),
        ({"太阳", "太阴"}, "日月配"),
        ({"天同", "天梁"}, "福寿配"),
        ({"武曲", "贪狼"}, "财艺配"),
    ]

    interactions = []
    for label, p1, p2 in [
        ("命宫×命宫", self_ming, other_ming),
        ("命宫×夫妻宫", self_ming, other_fuqi),
        ("夫妻宫×命宫", self_fuqi, other_ming),
    ]:
        if not p1 or not p2:
            continue
        stars1 = set(_get_all_stars(p1))
        stars2 = set(_get_all_stars(p2))
        all_stars = stars1 | stars2
        for pair, desc in _harmony_pairs:
            if pair.issubset(all_stars):
                interactions.append(f"{label}: {desc} ({'/'.join(pair)}同在)")

    return {"interactions": interactions, "total": len(interactions)}


def _analyze_couple_flying(self_palaces, other_palaces):
    """夫妻宫飞化交叉分析"""
    from services.metaphysics.ziwei.sihua import compute_palace_flying

    self_flying = compute_palace_flying(self_palaces)
    other_flying = compute_palace_flying(other_palaces)

    cross = []
    self_fuqi_fly = self_flying.get("夫妻", {})
    other_fuqi_fly = other_flying.get("夫妻", {})

    for hua_type in ["禄", "权", "科", "忌"]:
        self_target = self_fuqi_fly.get(hua_type, {}).get("to", "")
        other_target = other_fuqi_fly.get(hua_type, {}).get("to", "")
        if self_target and other_target:
            cross.append(f"双方夫妻宫{hwa_type}: 自己→{self_target}, 对方→{other_target}")
        elif self_target:
            cross.append(f"自己夫妻宫{hwa_type}入{self_target}")
        elif other_target:
            cross.append(f"对方夫妻宫{hwa_type}入{other_target}")

    return {"cross_flying": cross}


def _analyze_daxian_sync(ziwei_self, ziwei_other):
    """大限同步度: 双方当前大限命宫的关系"""
    from services.metaphysics.ziwei.paipan import _find_current_daxian

    self_dx = _find_current_daxian(ziwei_self)
    other_dx = _find_current_daxian(ziwei_other)

    if not self_dx or not other_dx:
        return {"sync_level": "未知"}

    _ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
    self_idx = _ZHI.index(self_dx.get("zhi", "子"))
    other_idx = _ZHI.index(other_dx.get("zhi", "子"))
    diff = (self_idx - other_idx) % 12

    # 三合=120°, 六合=180° 对面
    if diff in (0, 4, 8):  # 三合
        sync = "三合同步，大限节奏一致"
    elif diff == 6:  # 六冲
        sync = "大限对冲，节奏互补但有张力"
    elif diff in (3, 9):
        sync = "大限呈直角，各自发展"
    else:
        sync = "大限节奏不同步"

    return {
        "self_daxian": {"palace": self_dx["palace"], "start_age": self_dx["start_age"]},
        "other_daxian": {"palace": other_dx["palace"], "start_age": other_dx["start_age"]},
        "sync_level": sync,
    }
