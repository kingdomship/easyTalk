"""Interpreter — build reading prompts (4-layer model). Does NOT call LLM."""
import logging

logger = logging.getLogger("metaphysics")

_DISCLAIMER = "\n\n---\n⚠️ 以上内容仅供文化研究与娱乐参考，不构成人生决策依据。"

# Ten Gods → OCEAN mapping
_TEN_GOD_OCEAN = {
    "正官": {"C": 0.7, "desc": "尽责性↑(自律、守规矩)"},
    "七杀": {"N": 0.6, "C": 0.5, "desc": "神经质↑(压力驱动) + 尽责性↑(果断)"},
    "正印": {"O": 0.6, "desc": "开放性↑(好学、包容)"},
    "偏印": {"O": 0.8, "desc": "开放性↑↑(独特思维)"},
    "正财": {"C": 0.6, "desc": "尽责性↑(务实、节俭)"},
    "偏财": {"E": 0.6, "desc": "外向性↑(慷慨、社交)"},
    "食神": {"O": 0.5, "E": 0.5, "desc": "开放性↑(创造力) + 外向性↑(享乐)"},
    "伤官": {"O": 0.8, "N": 0.5, "desc": "开放性↑↑(才华) + 神经质↑(叛逆)"},
    "比肩": {"E": 0.4, "A": -0.3, "desc": "外向性↑(独立) + 宜人性↓(竞争)"},
    "劫财": {"E": 0.6, "A": -0.3, "desc": "外向性↑(社交) + 宜人性↓(冲动)"},
}

# Ziwei main star → Attachment style
_STAR_ATTACHMENT = {
    "紫微": "安全型倾向", "天机": "焦虑型倾向", "太阳": "安全型倾向",
    "武曲": "回避型倾向", "天同": "安全型倾向", "廉贞": "焦虑/回避混合",
    "天府": "安全型倾向", "太阴": "安全/焦虑混合", "贪狼": "回避型倾向",
    "巨门": "焦虑型倾向", "天相": "安全型倾向", "天梁": "安全型倾向",
    "七杀": "回避型倾向", "破军": "焦虑+回避混合(高焦虑高回避)",
}

# Wuxing → Panksepp emotion
_WUXING_PANKSEPP = {
    "木": {"system": "SEEKING", "excess": "探索欲过强(焦躁)", "deficit": "缺乏动力(抑郁)"},
    "火": {"system": "PLAY+LUST", "excess": "过度兴奋", "deficit": "缺乏激情"},
    "土": {"system": "CARE", "excess": "过度操心", "deficit": "缺乏共情"},
    "金": {"system": "RAGE+FEAR", "excess": "易怒/悲伤", "deficit": "缺乏边界"},
    "水": {"system": "FEAR+PANIC/GRIEF", "excess": "恐惧/孤僻", "deficit": "缺乏直觉"},
}


def build_fallback_reading(chart, scope="general"):
    """Layer 1 only fallback — pure template, no LLM needed."""
    bazi = chart.get("bazi", {}).get("static", {})
    ziwei = chart.get("ziwei", {}).get("static", {})

    parts = []

    pillars = bazi.get("four_pillars", {})
    dm = bazi.get("day_master", "?")
    if pillars:
        parts.append(f"八字: {pillars.get('year',{}).get('gan','?')}{pillars.get('year',{}).get('zhi','?')}年 "
                     f"{pillars.get('month',{}).get('gan','?')}{pillars.get('month',{}).get('zhi','?')}月 "
                     f"{pillars.get('day',{}).get('gan','?')}{pillars.get('day',{}).get('zhi','?')}日 "
                     f"{pillars.get('time',{}).get('gan','?')}{pillars.get('time',{}).get('zhi','?')}时")
        parts.append(f"日主: {dm}")
        gj = bazi.get("geju", {})
        if gj:
            parts.append(f"格局: {gj.get('type', '?')}, {gj.get('strength', '?')}")

    mg = ziwei.get("ming_gong", {})
    if mg:
        stars = [s for s in mg.get("stars", []) if "[" not in s]
        parts.append(f"紫微命宫: {mg.get('gan','?')}{mg.get('zhi','?')}, 主星: {', '.join(stars) if stars else '无'}")
        wj_labels = ["水二局", "木三局", "金四局", "土五局", "火六局"]
        wj = ziwei.get("wuxing_ju", 3)
        parts.append(f"五行局: {wj_labels[wj-2] if 2 <= wj <= 6 else f'局{wj}'}")

    body = "\n".join(parts)
    return f"## 命盘基础信息\n\n{body}\n\n⚠️ AI 深度解读暂时不可用，以上为基础命盘信息。请稍后再试。{_DISCLAIMER}"


def build_reading_prompt(chart, scope, kb_entries, user_portrait=""):
    """Build 4-layer reading prompt."""
    scope_names = {
        "general": "本命盘总览", "career": "事业运势", "love": "感情运势",
        "health": "健康状况", "ming_gong": "命宫综合", "personality": "性格分析",
        "dayun": "大运分析", "liunian": "流年运势", "liuyue": "流月运势",
    }
    scope_name = scope_names.get(scope, scope)

    l1 = _build_layer1_data(chart, scope)
    l2 = _build_layer2_references(kb_entries)
    l3 = _build_layer3_psych(scope, user_portrait)
    l4 = _build_layer4_constraints()

    return f"""## 命理分析任务

### 分析范围
{scope_name}

{_DISCLAIMER}

### 命盘数据
{l1}

{l2}

{l3}

{l4}

请基于以上命盘数据和分析约束，生成一份结构化的命理分析报告。
"""


def build_hehun_reading_prompt(chart_self, chart_other, hehun_result, kb_entries):
    """Build hehun (合婚) reading prompt."""
    l1_self = _build_layer1_data(chart_self, "general")
    l1_other = _build_layer1_data(chart_other, "general")
    l2 = _build_layer2_references(kb_entries)

    hehun_str = f"""合婚结果:
- 纳音关系: {hehun_result.get('nayan_relation', '?')}
- 干支合: {hehun_result.get('ganzhi_he', '?')}
- 十神互补: {hehun_result.get('shishen_complement', '?')}
- 五行互补: {hehun_result.get('wuxing_balance', '?')}
"""

    return f"""## 合婚分析任务

### 本人命盘
{l1_self}

### 对方命盘
{l1_other}

### 合盘数据
{hehun_str}

{l2}

{_build_layer4_constraints()}

请基于双方命盘和合盘数据，分析两人关系的契合度与潜在课题。
{_DISCLAIMER}
"""


def _build_layer1_data(chart, scope):
    """Layer 1: chart JSON → structured natural language."""
    parts = []
    bazi = chart.get("bazi", {})
    b_static = bazi.get("static", {})
    b_cur = bazi.get("current", {})

    pillars = b_static.get("four_pillars", {})
    if pillars:
        p_str = "  ".join(
            f"{k}:{v.get('gan','?')}{v.get('zhi','?')}" for k, v in pillars.items()
        )
        parts.append(f"四柱: {p_str}")

    dm = b_static.get("day_master", "?")
    parts.append(f"日主: {dm}")

    ten_gods = b_static.get("ten_gods_gan", {})
    if ten_gods:
        parts.append(f"十神: {', '.join(f'{k}={v}' for k, v in ten_gods.items() if v != '日主')}")

    gj = b_static.get("geju", {})
    if gj:
        parts.append(f"格局: {gj.get('type','?')}, {gj.get('strength','?')}, 调候: {gj.get('tiao_hou','?')}")

    if b_cur:
        dy = b_cur.get("dayun", {})
        ln = b_cur.get("liunian", {})
        if dy:
            parts.append(f"当前大运: {dy.get('gan','?')}{dy.get('zhi','?')} ({dy.get('start_age','?')}岁起)")
        if ln:
            parts.append(f"当前流年: {ln.get('gan','?')}{ln.get('zhi','?')}年 ({ln.get('ten_god','?')})")

    ziwei = chart.get("ziwei", {})
    z_static = ziwei.get("static", {})
    palaces = z_static.get("palaces", [])
    if palaces:
        parts.append(f"\n紫微十二宫 ({z_static.get('wuxing_ju','?')}局):")
        for p in palaces:
            stars_clean = [s.split("[")[0] for s in p.get("stars", [])]
            parts.append(f"  {p['name']}({p.get('gan','?')}{p['zhi']}): {', '.join(stars_clean) if stars_clean else '—'}")

    sihua = z_static.get("sihua", {})
    if sihua:
        sihua_parts = []
        for hua, info in sihua.items():
            if info:
                sihua_parts.append(f"{hua}({info['star']}在{info['palace']})")
        if sihua_parts:
            parts.append(f"生年四化: {', '.join(sihua_parts)}")

    return "\n".join(parts)


def _build_layer2_references(kb_entries):
    """Layer 2: Classical reference injection."""
    if not kb_entries:
        return "### 古籍参考\n(无匹配条目)"
    lines = ["### 古籍参考"]
    for e in kb_entries[:5]:
        lines.append(f"- {e.get('classical_ref', '')}")
    return "\n".join(lines)


def _build_layer3_psych(scope, user_portrait):
    """Layer 3: Psych cross-mapping hints."""
    lines = ["### 心理映射参考", "（以下为命理 x 心理学交叉提示，帮助提供更立体的分析）"]
    if user_portrait:
        lines.append(f"\n用户画像: {user_portrait[:500]}")
    if scope in ("general", "personality"):
        lines.append("- 十神分布 → OCEAN人格维度关联（正官↔尽责性, 食神↔开放性, 比肩↔外倾性...）")
        lines.append("- 命宫主星 → 依恋风格倾向（紫微↔安全, 天机↔焦虑, 武曲↔回避...）")
    if scope in ("general", "love"):
        lines.append("- 夫妻宫主星 + 桃花星 → 感情模式分析")
    if scope in ("general", "career"):
        lines.append("- 官禄宫/财帛宫 + 格局 → 事业/财务倾向")
    if scope in ("general", "health"):
        lines.append("- 疾厄宫 + 五行平衡 → Panksepp情绪系统关联")
    return "\n".join(lines)


def _build_layer4_constraints():
    """Layer 4: Output constraints."""
    return """### 输出约束
1. 用"从命理的角度看..."而非"你注定..."
2. 信号强度标注: 多指标一致→✅强信号, 单一指标→⚠️仅供参考, 指标矛盾→❌矛盾需展开
3. 凶象转译为风险提示，不说宿命论断
4. 禁止使用"一定/绝对/肯定"等绝对词
5. 不主动预测灾祸/死亡/重大疾病"""
