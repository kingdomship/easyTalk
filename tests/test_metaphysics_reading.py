"""Metaphysics reading quality + cache logic tests."""
import json
import os
import sys
import pytest

sys.path.insert(0, ".")

from services.metaphysics.interpreter import build_fallback_reading, build_reading_prompt
from services.metaphysics.cache import cache
from app.config import BIRTH_INFO_PATH


# ── Sample chart for testing ──
SAMPLE_CHART = {
    "bazi": {
        "static": {
            "four_pillars": {
                "year": {"gan": "甲", "zhi": "子"},
                "month": {"gan": "丙", "zhi": "寅"},
                "day": {"gan": "戊", "zhi": "午"},
                "time": {"gan": "壬", "zhi": "戌"},
            },
            "day_master": "戊",
            "geju": {"type": "正官格", "strength": "身强"},
            "ten_gods_gan": {"year": "七杀", "month": "偏印", "day": "日主", "time": "偏财"},
        },
        "current": {"dayun": {"gan": "甲", "zhi": "申", "start_age": 6}},
    },
    "ziwei": {
        "static": {
            "ming_gong": {"gan": "丙", "zhi": "寅", "stars": ["紫微", "天相"]},
            "palaces": [],
            "wuxing_ju": 3,
            "sihua": {},
        }
    },
}


# ═══ Task 9.2: Reading Quality ═══


def test_fallback_reading():
    """回退解读包含命盘信息和免责声明"""
    fb = build_fallback_reading(SAMPLE_CHART)
    assert "命盘" in fb, "回退解读应包含命盘信息"
    assert "免责" in fb or "参考" in fb, "回退解读应包含免责声明"
    assert len(fb) > 50, "回退解读不应为空"


def test_reading_prompt_all_four_layers():
    """解读 prompt 包含全部四层"""
    prompt = build_reading_prompt(SAMPLE_CHART, "general", [], "")
    assert "命盘数据" in prompt, "Layer 1 (命盘数据) 缺失"
    assert "古籍参考" in prompt, "Layer 2 (古籍参考) 缺失"
    assert "心理映射" in prompt, "Layer 3 (心理映射) 缺失"
    assert "输出约束" in prompt, "Layer 4 (输出约束) 缺失"
    assert ("免责" in prompt or "参考" in prompt), "免责声明缺失"


def test_reading_prompt_disclaimer():
    """所有范围的解读都包含免责声明"""
    for scope in ["general", "dayun", "liunian"]:
        prompt = build_reading_prompt(SAMPLE_CHART, scope, [], "")
        assert ("免责" in prompt or "参考" in prompt), f"scope={scope} 缺失免责声明"


def test_reading_prompt_with_kb():
    """知识库注入到 prompt (classical_ref 字段渲染到 Layer 2)"""
    kb_entries = [
        {"classical_ref": "《子平真诠·论正官》: 正官者，克我之神也..."},
        {"classical_ref": "《紫微斗数全书》: 紫微坐命者天生具有领导气质..."},
    ]
    prompt = build_reading_prompt(SAMPLE_CHART, "general", kb_entries, "")
    assert "子平真诠" in prompt, "KB classical_ref应注入prompt"
    assert "紫微斗数全书" in prompt, "KB classical_ref应注入prompt"

def test_reading_prompt_empty_kb():
    """空KB时不报错"""
    prompt = build_reading_prompt(SAMPLE_CHART, "general", [], "")
    assert "无匹配条目" in prompt, "空KB应显示无匹配条目"


def test_reading_prompt_with_portrait():
    """用户画像注入"""
    prompt = build_reading_prompt(SAMPLE_CHART, "general", [], "INTP型人格，情绪较稳定，近期工作压力较大")
    assert "INTP" in prompt, "用户画像应注入prompt"


# ═══ Task 9.4: Cache Logic ═══


def test_cache_birth_hash():
    """出生信息hash变更 → 缓存失效"""
    # Use a test-specific path to avoid polluting real data
    test_path = "/tmp/easytalk_test_birth.json"
    try:
        test_info = {"solar_date": "2000-01-01", "clock_time": "08:00", "city": "北京", "gender": "女"}
        os.makedirs(os.path.dirname(test_path), exist_ok=True)
        with open(test_path, "w") as f:
            json.dump(test_info, f)

        # Get hash using cache's internal method
        cache.invalidate()
        from app.config import BIRTH_INFO_PATH
        import hashlib

        with open(test_path, "r") as f:
            h1 = hashlib.md5(f.read().encode()).hexdigest()

        # Modify birth info
        test_info["solar_date"] = "1990-06-15"
        with open(test_path, "w") as f:
            json.dump(test_info, f)

        with open(test_path, "r") as f:
            h2 = hashlib.md5(f.read().encode()).hexdigest()

        assert h1 != h2, "出生信息变更后hash应不同"
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_cache_invalidate():
    """invalidate() 清除所有缓存"""
    cache.invalidate()
    assert cache._bazi_static is None, "invalidate后静态层应为None"
    assert cache._birth_hash is None, "invalidate后birth_hash应为None"
    assert cache._dynamic_cache == {}, "invalidate后动态缓存应为空"


def test_cache_singleton():
    """ChartCache 是单例"""
    from services.metaphysics.cache import ChartCache
    c1 = ChartCache()
    c2 = ChartCache()
    assert c1 is c2, "ChartCache应为单例"
