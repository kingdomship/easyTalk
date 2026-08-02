"""Ziwei sihua (四化) module — 生年四化 + 12宫飞化 + 循环忌检测"""
import logging

logger = logging.getLogger("metaphysics")

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

_GAN_SIHUA = {
    "甲": ("廉贞", "破军", "武曲", "太阳"),
    "乙": ("天机", "天梁", "紫微", "太阴"),
    "丙": ("天同", "天机", "文昌", "廉贞"),
    "丁": ("太阴", "天同", "天机", "巨门"),
    "戊": ("贪狼", "太阴", "右弼", "天机"),
    "己": ("武曲", "贪狼", "天梁", "文曲"),
    "庚": ("太阳", "武曲", "太阴", "天同"),
    "辛": ("巨门", "太阳", "文曲", "文昌"),
    "壬": ("天梁", "紫微", "左辅", "武曲"),
    "癸": ("破军", "巨门", "太阴", "贪狼"),
}


def compute_sihua_static(year_gan, palaces):
    """生年四化: 年干 → 禄权科忌落在哪个宫位"""
    mapping = _SIHUA_TABLE.get(year_gan, {})
    result = {"禄": None, "权": None, "科": None, "忌": None}
    for hua_type, star_name in mapping.items():
        for i, p in enumerate(palaces):
            if star_name in p.get("stars", []):
                result[hua_type] = {
                    "star": star_name,
                    "palace": p["name"],
                    "palace_zhi": p["zhi"],
                    "palace_gan": p.get("gan", ""),
                    "palace_idx": i,
                }
                break
    return result


def compute_palace_flying(palaces):
    """12宫飞化: 每宫天干 → 四化飞入宫位"""
    star_to_palace = {}
    for p in palaces:
        for s in p.get("stars", []):
            clean = s.split("[")[0]
            star_to_palace[clean] = p["name"]

    flying = {}
    for p in palaces:
        gan = p.get("gan", "")
        sihua_stars = _GAN_SIHUA.get(gan, ("", "", "", ""))
        p_fly = {}
        for hua_type, star in zip(["禄", "权", "科", "忌"], sihua_stars):
            if star and star in star_to_palace:
                target = star_to_palace[star]
                p_fly[hua_type] = {"star": star, "from": p["name"], "to": target}
        if p_fly:
            flying[p["name"]] = p_fly

    return flying


def detect_cycles(flying):
    """循环忌检测: A忌入B, B忌入A → cycle_warnings"""
    warnings = []
    ji_edges = {}
    for palace, fly in flying.items():
        ji_info = fly.get("忌")
        if ji_info:
            ji_edges[palace] = ji_info["to"]

    checked = set()
    for a, b in ji_edges.items():
        if (a, b) in checked:
            continue
        if b in ji_edges and ji_edges[b] == a:
            warnings.append(f"忌入循环: {a}忌入{b}, {b}忌入{a}")
            checked.add((a, b))
            checked.add((b, a))

    for palace, target in ji_edges.items():
        if target in ("命宫", "夫妻宫", "疾厄宫"):
            warnings.append(f"高危: {palace}忌入{target}")

    return warnings
