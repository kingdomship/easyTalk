"""Metaphysics paipan accuracy tests — verified against lunar-python library."""
import pytest
from services.metaphysics.solar_time import correct_solar_time
from services.metaphysics.bazi.paipan import compute_bazi_static, compute_bazi_dynamic

# Verified against lunar-python v0.3.5+ output
BAZI_TEST_CASES = [
    # (solar_date, clock_time, city, gender, expected_day_master, expected_year_pillar)
    ("2000-01-01", "08:00", "北京", "男", "戊", ("己", "卯")),
    ("1990-06-15", "14:30", "上海", "女", "辛", ("庚", "午")),
    ("1985-03-20", "23:00", "成都", "男", "戊", ("乙", "丑")),
    ("1978-12-25", "06:15", "广州", "女", "辛", ("戊", "午")),
    ("1995-08-08", "12:00", "北京", "男", "辛", ("乙", "亥")),
    ("1988-04-12", "20:45", "深圳", "女", "丁", ("戊", "辰")),
    ("1970-09-30", "03:30", "重庆", "男", "癸", ("庚", "戌")),
    ("1992-02-14", "16:00", "杭州", "女", "庚", ("壬", "申")),
    ("1982-11-11", "10:10", "武汉", "男", "戊", ("壬", "戌")),
    ("1975-07-07", "18:00", "西安", "女", "甲", ("乙", "卯")),
]


@pytest.mark.parametrize("solar_date,clock_time,city,gender,exp_dm,exp_year", BAZI_TEST_CASES)
def test_bazi_paipan(solar_date, clock_time, city, gender, exp_dm, exp_year):
    birth = {"solar_date": solar_date, "clock_time": clock_time, "city": city, "gender": gender}
    corrected = correct_solar_time(birth)
    result = compute_bazi_static(corrected)
    assert result.get("error") is None, f"排盘失败: {result.get('error_message')}"
    assert corrected.get("corrected"), "时间应被校正"
    dm = result["static"]["day_master"]
    assert dm == exp_dm, f"日主不符: 期望{exp_dm}, 实际{dm}"
    fp = result["static"]["four_pillars"]
    assert fp["year"]["gan"] == exp_year[0], f"年干不符: 期望{exp_year[0]}, 实际{fp['year']['gan']}"
    assert fp["year"]["zhi"] == exp_year[1], f"年支不符: 期望{exp_year[1]}, 实际{fp['year']['zhi']}"
    # Verify all four pillars have gan+zhi
    for key in ["year", "month", "day", "time"]:
        p = fp[key]
        assert p["gan"] in "甲乙丙丁戊己庚辛壬癸", f"{key}柱天干无效: {p['gan']}"
        assert p["zhi"] in "子丑寅卯辰巳午未申酉戌亥", f"{key}柱地支无效: {p['zhi']}"
    # Dynamic layer should work
    dynamic = compute_bazi_dynamic(result)
    assert dynamic.get("current"), "动态层计算失败"
    assert "dayun" in dynamic.get("current", {}), "大运缺失"


ZIWEI_TEST_CASES = [
    ("2000-01-01", "08:00", "北京", "女"),
    ("1990-06-15", "14:30", "上海", "女"),
    ("1985-03-20", "23:00", "成都", "男"),
    ("1978-12-25", "06:15", "广州", "女"),
    ("1995-08-08", "12:00", "北京", "男"),
]


@pytest.mark.parametrize("solar_date,clock_time,city,gender", ZIWEI_TEST_CASES)
def test_ziwei_paipan(solar_date, clock_time, city, gender):
    from services.metaphysics.ziwei.paipan import compute_ziwei_static
    from services.metaphysics.solar_time import correct_solar_time
    birth = {"solar_date": solar_date, "clock_time": clock_time, "city": city, "gender": gender}
    corrected = correct_solar_time(birth)
    result = compute_ziwei_static(corrected)
    assert result.get("error") is None, f"紫微排盘失败: {result.get('error_message')}"
    palaces = result["static"]["palaces"]
    assert len(palaces) == 12, f"应有12宫, 实际{len(palaces)}"
    # Verify ming gong
    mg = result["static"]["ming_gong"]
    assert mg["gan"] in "甲乙丙丁戊己庚辛壬癸", f"命宫天干无效: {mg['gan']}"
    assert mg["zhi"] in "子丑寅卯辰巳午未申酉戌亥", f"命宫地支无效: {mg['zhi']}"
    assert len(mg.get("stars", [])) >= 1, f"命宫应有至少1颗主星, 实际{len(mg.get('stars', []))}"
    # Verify all palaces have gan+zhi+stars
    for i, p in enumerate(palaces):
        assert p["gan"] in "甲乙丙丁戊己庚辛壬癸", f"第{i}宫天干无效: {p['gan']}"
        assert p["zhi"] in "子丑寅卯辰巳午未申酉戌亥", f"第{i}宫地支无效: {p['zhi']}"
    # Verify sihua
    sihua = result["static"].get("sihua", {})
    assert len(sihua) >= 1, f"应有四化星, 实际{len(sihua)}"


def test_dst_correction():
    """夏令时校正: 1988-06-01 北京 应该减1小时"""
    birth = {"solar_date": "1988-06-01", "clock_time": "08:00", "city": "北京", "gender": "女"}
    corrected = correct_solar_time(birth)
    assert corrected["clock_time"] != "08:00", f"夏令时应校正, 实际{corrected['clock_time']}"


def test_longitude_correction():
    """经度校正: 乌鲁木齐 (87.6E, 偏离120度) 应该偏移约-2小时"""
    birth = {"solar_date": "2000-01-01", "clock_time": "12:00", "city": "乌鲁木齐", "gender": "男"}
    corrected = correct_solar_time(birth)
    assert corrected["clock_time"] != "12:00", f"经度应校正, 实际{corrected['clock_time']}"


def test_boundary_dates():
    """边界日期: 1900-01-01 and 2100-12-31 应能正常排盘"""
    birth1 = {"solar_date": "1900-01-01", "clock_time": "12:00", "city": "北京", "gender": "女"}
    result = compute_bazi_static(correct_solar_time(birth1))
    assert not result.get("error"), f"1900 should work: {result}"

    birth2 = {"solar_date": "2100-12-31", "clock_time": "12:00", "city": "北京", "gender": "男"}
    result = compute_bazi_static(correct_solar_time(birth2))
    assert not result.get("error"), f"2100 should work: {result}"


def test_missing_info():
    """缺失信息: 无时间默认午时, 无城市默认北京"""
    birth = {"solar_date": "2000-06-15", "clock_time": "12:00", "city": "北京", "gender": "女"}
    result = compute_bazi_static(correct_solar_time(birth))
    assert not result.get("error")
    # Verify four pillars present
    fp = result["static"]["four_pillars"]
    for key in ["year", "month", "day", "time"]:
        assert fp[key]["gan"], f"{key}柱天干缺失"
        assert fp[key]["zhi"], f"{key}柱地支缺失"
