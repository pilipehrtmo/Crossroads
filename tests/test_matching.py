"""Skill coverage matching, aliases, team skill gap (pure logic, no database)."""
from types import SimpleNamespace as NS
from app import skills as SK
from app.matching import coverage, explain, label, team_gap


def seat(must="", nice="", filled=False): return NS(skills=must, nice_skills=nice, filled=filled, advisor=False)


def test_aliases_merge_same_skill_in_english_and_chinese():
    assert SK.tags("UI設計, ui design, UI Design") == ["ui design"]
    assert SK.tags("ML，機器學習；Python3") == ["machine learning", "python"]
    assert SK.normalize("ｆｉｇｍａ") == "figma"           # full-width letters


def test_related_skills_are_not_synonyms():
    assert SK.normalize("figma") != SK.normalize("ui design")
    assert SK.normalize("python") != SK.normalize("machine learning")
    assert SK.normalize("data analysis") != SK.normalize("data visualization")
    assert SK.normalize("java") != SK.normalize("javascript")
    assert SK.related("figma", "ui design") and SK.related("ui design", "figma")


def test_coverage_counts_only_must_have_for_the_main_score():
    c = coverage("figma, ui design", seat("figma, ui design, user research"))
    assert c["must_have"] == ["figma", "ui design"] and c["must_missing"] == ["user research"]
    assert label(c) == "2/3 must-have"


def test_nice_to_have_never_makes_up_for_a_missing_must_have():
    s = seat("figma, ui design", "photography, illustration, copywriting")
    all_nice = coverage("figma, photography, illustration, copywriting", s)   # 1 of 2 must, 3 nice
    all_must = coverage("figma, ui design", s)                               # 2 of 2 must, no nice
    assert all_must["rank"] > all_nice["rank"]
    assert coverage("figma, ui design, photography", s)["rank"] > all_must["rank"]   # nice breaks ties


def test_broader_profile_never_ranks_lower():
    s = seat("figma, ui design")
    narrow = coverage("figma, ui design", s); broad = coverage("figma, ui design, python, react, pitching", s)
    assert broad["rank"] == narrow["rank"]   # the old overlap score gave the broader student 40% vs 100%


def test_seat_without_must_have_makes_no_claim():
    c = coverage("python", seat(""))
    assert c["rank"] is None and label(c) is None and explain(c) == ["This seat lists no must-have skills"]


def test_explanations_name_real_skills_in_both_languages():
    c = coverage("figma, interviews", seat("ui design, user research", "photography"))
    en = explain(c)
    assert en[0] == "Covers 0 of 2 must-have skills" and "Missing must-have: ui design, user research" in en
    assert any("has figma, the seat asks for ui design" in x for x in en)        # related, not counted
    zh = explain(c, "zh")
    assert zh[0] == "符合 2 項必備技能中的 0 項"


def test_explanation_says_what_a_person_adds_to_the_team():
    c = coverage("figma, python", seat("figma, python"), team_skills="python, react")
    assert c["adds"] == ["figma"] and "Adds figma, which no one on the team has yet" in explain(c)


def test_team_gap_uses_real_profiles_not_filled_seats():
    lead = NS(skills="python, react"); member = NS(skills="figma")
    roles = [seat("python", filled=True), seat("ui design, figma", filled=True), seat("user research", "interviews")]
    g = team_gap([lead, member], roles)
    # the "ui design" seat is filled, but nobody on the team actually lists ui design: still missing
    assert g["must_covered"] == ["python", "figma"] and g["must_missing"] == ["ui design", "user research"]
    assert g["nice_missing"] == ["interviews"] and g["filled_seats"] == 2 and g["open_seats"] == 1
