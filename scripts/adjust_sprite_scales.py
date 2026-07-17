"""Adjust cell_scale and anchor for all sprites based on real-world proportions.

One-shot script. Reads all 10 category JSON files, applies keyword-based rules
to set appropriate cell_scale and add anchor (head_top / hold) fields.

Usage: python3 scripts/adjust_sprite_scales.py [--dry-run]
"""

import json
import os
import sys

SPRITE_DIR = os.path.join(os.path.dirname(__file__), "..", "services", "identity", "sprites")

# ── cell_scale rules ──────────────────────────────────────────────
# (keyword_chars → cell_scale), checked in order, first match wins.
# Check is: any keyword char in sprite's keywords list or name.
SCALE_RULES = [
    # ── Tiny ──
    (0.5, ["尘", "粉", "屑", "粒", "泡", "菌", "霉"]),
    # ── Insects (tiny) ──
    (0.55, ["蜂", "蚁", "蝇", "蚊", "萤", "蜻", "蝴蝶", "蛾", "蝉", "蜓", "蟋蟀",
            "蝽", "蚪", "瓢虫", "蚂蚱", "蜘", "蟑", "蝎", "蚕", "毛毛虫", "甲虫", "螳", "蟋"]),
    # ── Weather particles ──
    (0.5, ["雨", "雪", "雾", "霜", "露", "雹", "霰", "霾", "水珠", "水花"]),
    # ── Sky effects (high count, light weight) ──
    (0.6, ["花瓣", "落叶", "枫叶", "羽毛", "蒲公英", "星尘", "魔法尘", "樱花雨"]),
    # ── Small flowers (single bloom) ──
    (0.75, ["花", "玫瑰", "向日葵", "郁金香", "雏菊", "康乃馨", "荷花", "牡丹", "百合", "菊花",
            "梅花", "桃花", "兰花", "薰衣草", "昙花", "牵牛花", "栀子花", "绣球花",
            "紫罗兰", "茉莉", "水仙", "杜鹃", "山茶", "风信子", "勿忘我", "彼岸花", "鸢尾",
            "铃兰", "三色堇", "芙蓉", "木槿", "丁香", "桔梗", "芍药", "海棠",
            "睡莲", "樱花草", "矢车菊", "马蹄莲", "鹤望兰", "含羞草", "仙人掌花", "四叶草",
            "狗尾草", "蒲公英花"]),
    # ── Leaves / petals (single) ──
    (0.7, ["叶", "叶子", "绿芽", "嫩芽", "芒", "絮", "草"]),
    # ── Small objects ──
    (0.85, ["扣", "针", "钉", "钥匙", "硬币", "糖", "果冻", "布丁", "豆", "仁", "籽",
            "钮扣", "别针", "大头针", "图钉", "回形针", "夹子", "橡皮", "戒指", "项链",
            "耳环", "手链", "胸针", "徽章", "奖章", "邮票"]),
    # ── Fruits / Vegetables ──
    (1.0, ["苹果", "梨", "橘子", "橙子", "柠檬", "香蕉", "葡萄", "樱桃", "草莓", "蓝莓",
           "芒果", "猕猴桃", "桃子", "杏", "李子", "石榴", "西瓜", "哈密瓜", "甜瓜",
           "番茄", "辣椒", "黄瓜", "茄子", "萝卜", "胡萝卜", "洋葱", "大蒜", "姜",
           "土豆", "红薯", "南瓜", "苦瓜", "四季豆", "豌豆", "玉米", "花生", "栗子",
           "橄榄", "无花果", "枣", "椰", "百香果", "火龙果", "荔枝", "龙眼", "榴莲",
           "山竹", "杨梅", "枇杷", "柿子", "山楂", "桑葚", "奇异果", "牛油果",
           "青椒", "灯笼椒", "西兰花", "花菜", "菠菜", "白菜", "卷心菜", "芹菜",
           "香菇", "蘑菇", "灵芝", "金针菇", "松茸", "木耳", "银耳"]),
    # ── Food / Drinks ──
    (1.1, ["面", "饭", "饼", "蛋糕", "面包", "饺子", "馄饨", "粽子", "月饼", "寿司",
           "便当", "火锅", "烤肉", "炸鸡", "薯条", "汉堡", "披萨", "热狗", "三明治",
           "意大利面", "方便面", "拉面", "米粉", "粥", "汤", "沙拉",
           "咖啡", "茶", "奶茶", "果汁", "可乐", "啤酒", "红酒", "鸡尾酒",
           "奶瓶", "酒杯", "茶杯", "咖啡杯", "马克杯", "瓶子", "盘子", "碗",
           "冰棍", "雪糕", "甜甜圈", "马卡龙", "巧克力", "饼干", "爆米花",
           "薯片", "坚果", "瓜子", "棉花糖", "棒棒糖", "太妃糖", "泡泡糖"]),
    # ── Small/Medium animals ──
    (1.1, ["鸟", "雀", "燕", "鸽", "鹰", "猫头鹰", "鸡", "鸭", "鹅", "鹦鹉",
           "鱼", "虾", "蟹", "蛙", "鼠", "兔", "猫", "狗", "蛇", "龟",
           "企鹅", "海鸥", "火烈鸟", "天鹅", "孔雀", "乌鸦", "喜鹊", "麻雀",
           "金鱼", "锦鲤", "小丑鱼", "海马", "海星", "水母", "章鱼", "乌贼",
           "蜥蜴", "变色龙", "壁虎", "仓鼠", "松鼠", "刺猬", "豚鼠"]),
    # ── Larger animals ──
    (1.4, ["狐", "狼", "鹿", "羊", "猪", "牛", "马", "虎", "狮", "熊",
           "猴", "猩", "象", "鲸", "鲨", "鳄", "豹", "斑马", "长颈鹿",
           "骆驼", "犀牛", "河马", "海象", "海狮", "海豹", "海牛", "海豚",
           "虎鲸", "驼鹿", "羚羊", "野牛", "大猩猩", "猩猩", "狒狒", "袋鼠",
           "考拉", "树懒", "食蚁兽", "犰狳", "穿山甲", "北极熊", "熊猫",
           "狮子", "老虎", "金毛", "哈士奇", "柯基", "柴犬", "泰迪",
           "霸王龙", "恐龙", "剑龙", "三角龙", "翼龙"]),
    # ── Trees / Large plants ──
    (1.5, ["树", "松", "柏", "柳", "槐", "枫", "橡", "椰", "竹", "桉", "杉",
           "银杏", "梧桐", "榕树", "白杨", "红杉", "木棉", "凤凰木", "圣诞树"]),
    # ── Vehicles / Transport ──
    (1.8, ["车", "船", "艇", "飞机", "火车", "卡车", "巴士", "公交", "火箭",
           "航天", "地铁", "坦克", "直升", "潜艇", "摩托", "自行", "滑板",
           "跑车", "SUV", "吉普", "消防车", "警车", "救护车", "出租车",
           "热气球", "飞艇", "帆船", "游轮", "货轮", "太空船", "UFO"]),
    # ── Buildings / Landmarks ──
    (2.0, ["楼", "塔", "桥", "城", "堡", "宫殿", "金字塔", "长城", "大厦",
           "教堂", "寺庙", "清真寺", "灯塔", "风车", "亭子", "宝塔",
           "学校", "医院", "图书馆", "博物馆", "银行", "邮局", "车站",
           "机场", "工厂", "仓库", "谷仓", "摩天轮", "过山车", "喷泉",
           "雕塑", "纪念碑", "拱门", "鸟居", "四合院", "土楼", "别墅",
           "茅草屋", "木屋", "雪屋", "蒙古包", "帐篷"]),
    # ── Sun / Moon ──
    (2.2, ["太阳", "月亮", "地球", "行星", "星球"]),
    # ── Head-top items (need to be visible above head) ──
    (1.5, ["帽", "冠", "皇冠", "王冠", "花环", "角", "猫耳", "兔耳", "光环", "触角",
           "头巾", "头盔", "斗笠", "耳机", "蝴蝶结", "发箍", "发夹", "便签"]),
    # ── Hold items (held near chin) ──
    (1.2, ["伞", "雨伞", "太阳伞", "气球", "魔法棒", "魔杖", "话筒", "麦克风",
           "扇子", "爱心", "情书", "信封", "礼物盒", "礼物"]),
]


# ── Anchor rules ──────────────────────────────────────────────────
# head_top: items worn on top of head (anchor_ry = -18)
HEAD_TOP = {
    "帽", "帽子", "鸭舌帽", "草帽", "礼帽", "棒球帽", "魔术帽", "安全帽",
    "头盔", "斗笠", "皇冠", "王冠", "花环", "光环", "天使光环",
    "恶魔角", "独角兽角", "猫耳", "兔耳", "鹿角", "触角", "天线",
    "头巾", "头带", "耳机", "蝴蝶结", "发箍", "发夹", "发饰",
    "便签", "墨镜", "太阳镜",
}

# face: items worn on the face (anchor_ry = -12, eye level)
FACE_ITEMS = {
    "眼镜", "墨镜", "太阳镜", "VR眼镜", "潜水镜", "口罩", "面罩",
    "单片眼镜", "眼罩",
}

# hold: items held near chin/chest (anchor_ry = 20)
HOLD = {
    "玫瑰", "向日葵", "郁金香", "雏菊", "康乃馨", "荷花", "牡丹", "百合",
    "菊花", "梅花", "桃花", "兰花", "薰衣草", "昙花", "牵牛花",
    "栀子花", "绣球花", "紫罗兰", "茉莉", "水仙", "杜鹃", "山茶",
    "风信子", "勿忘我", "彼岸花", "鸢尾", "铃兰", "三色堇", "芙蓉",
    "木槿", "丁香", "桔梗", "芍药", "海棠", "花", "睡莲", "马蹄莲",
    "爱心", "情书", "信封", "礼物盒", "礼物", "咖啡杯", "茶杯", "酒杯",
    "奶瓶", "书", "手机", "铅笔", "钢笔", "毛笔", "粉笔", "画笔",
    "气球", "棒棒糖", "魔法棒", "魔杖", "话筒", "麦克风", "扇子",
    "伞", "雨伞", "太阳伞", "玫瑰花",
}


def _match_scale(name: str, keywords: list[str]) -> float | None:
    """Check name + keywords against SCALE_RULES. Returns cell_scale or None.

    Uses longest-match-wins to avoid false positives: e.g. "雨伞" (umbrella)
    should match the 3-char rule "雨伞" at 1.2, not the 1-char rule "雨" at 0.5.
    Name matches get +1000 priority over keyword-only matches to prevent
    keyword false-positives (e.g. 鸢尾 has keyword 蓝蝴蝶花 but is a flower, not insect).
    """
    search_set = {name}
    for kw in keywords:
        search_set.add(kw)
    search_text = " ".join(search_set)
    best_cs = None
    best_len = 0
    for cs, chars in SCALE_RULES:
        for ch in chars:
            if ch in search_text:
                eff_len = len(ch) + (1000 if ch in name else 0)
                if eff_len > best_len:
                    best_len = eff_len
                    best_cs = cs
    return best_cs


def _match_anchor(name: str) -> tuple[str, int, int] | None:
    """Return (anchor_type, rx, ry) or None."""
    if name in FACE_ITEMS:
        return ("head_top", 0, -12)  # eye level
    if name in HEAD_TOP:
        return ("head_top", 0, -18)
    if name in HOLD:
        return ("hold", 0, 20)
    return None


def adjust_sprites(dry_run: bool = False):
    """Read all JSON files, adjust cell_scale and anchor, write back."""
    json_files = sorted(
        f for f in os.listdir(SPRITE_DIR)
        if f.endswith(".json") and not f.startswith("_")
    )
    if not json_files:
        print(f"ERROR: No JSON files found in {SPRITE_DIR}")
        sys.exit(1)

    total = 0
    scale_changes = 0
    anchor_added = 0
    scale_dist: dict[float, int] = {}
    anchor_dist: dict[str, int] = {}
    # Per-category default cell_scale when no rule matches
    cat_defaults = {
        "animals": 1.1, "nature": 1.0, "food": 1.1, "objects": 1.2,
        "weather": 0.6, "symbols": 1.0, "fantasy": 1.0, "people": 1.2,
        "transport": 1.8, "buildings": 2.0,
    }

    for fname in json_files:
        path = os.path.join(SPRITE_DIR, fname)
        with open(path, encoding="utf-8") as f:
            sprites = json.load(f)

        cat = fname.replace(".json", "")
        default_cs = cat_defaults.get(cat, 1.0)
        modified = False

        for s in sprites:
            total += 1
            name = s.get("name", "")
            keywords = s.get("keywords", [])

            # ── cell_scale ──
            old_cs = s.get("cell_scale", 2.0)
            new_cs = _match_scale(name, keywords)
            if new_cs is None:
                new_cs = default_cs
            new_cs = round(new_cs, 2)
            if abs(old_cs - new_cs) > 0.001:
                s["cell_scale"] = new_cs
                scale_changes += 1
                modified = True
            scale_dist[new_cs] = scale_dist.get(new_cs, 0) + 1

            # ── anchor ──
            # Skip sprites with count >= 10 (particle effects, not holdable)
            count = s.get("count", 1)
            if count < 10 and not s.get("anchor"):
                anchor_info = _match_anchor(name)
                if anchor_info:
                    atype, rx, ry = anchor_info
                    s["anchor"] = atype
                    s["anchor_rx"] = rx
                    s["anchor_ry"] = ry
                    # Ensure weight=0 and duration≥30 for head_top items
                    if atype == "head_top":
                        s["weight"] = 0
                        s["duration"] = max(s.get("duration", 30), 30)
                        s["count"] = 1
                    elif atype == "hold":
                        s["weight"] = 0
                        s["duration"] = max(s.get("duration", 3), 3.0)
                        s["count"] = 1
                        s["spread"] = 0
                    anchor_added += 1
                    anchor_dist[atype] = anchor_dist.get(atype, 0) + 1
                    modified = True

        if modified and not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sprites, f, ensure_ascii=False, indent=2)
            print(f"  ✓ {fname}: {len(sprites)} sprites updated")
        elif modified:
            print(f"  [DRY-RUN] {fname}: {len(sprites)} sprites would be updated")
        else:
            print(f"  - {fname}: no changes")

    # ── Summary ──
    print(f"\n{'DRY-RUN — ' if dry_run else ''}Summary:")
    print(f"  Total sprites: {total}")
    print(f"  cell_scale changes: {scale_changes}")
    print(f"  anchor added: {anchor_added}")

    print(f"\n  cell_scale distribution:")
    for cs in sorted(scale_dist.keys()):
        pct = scale_dist[cs] / total * 100
        bar = "#" * int(pct / 2)
        print(f"    {cs:5.2f}: {scale_dist[cs]:5d} ({pct:5.1f}%) {bar}")

    if anchor_dist:
        print(f"\n  anchor distribution:")
        for a, cnt in sorted(anchor_dist.items()):
            print(f"    {a}: {cnt}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    adjust_sprites(dry_run=dry)
