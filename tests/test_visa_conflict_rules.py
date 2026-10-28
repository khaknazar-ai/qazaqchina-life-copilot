from datetime import date

import pytest

from backend.app.domain.enums import SourceType, TrustLevel, UserScenario
from backend.app.domain.sources import SourceReference
from backend.app.source_conflicts.claims import compare_claims
from backend.app.source_conflicts.visa_rules import extract_visa_claims


def source(content: str, source_id: str = "A", **overrides) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        title="China immigration guidance",
        source_type=SourceType.official,
        trust_level=TrustLevel.level_1_official,
        content=content,
        **overrides,
    )


def detected(left: str, right: str, **overrides):
    return compare_claims(
        extract_visa_claims(source(left)) + extract_visa_claims(source(right, "B", **overrides))
    )


@pytest.mark.parametrize(
    ("rule_id", "left", "right"),
    [
        (
            "visa.enter_before_meaning",
            "Visa Enter Before is the last permitted entry date.",
            "Visa Enter Before is the last permitted departure date.",
        ),
        (
            "visa.stay_count_anchor",
            "Visa duration of stay is counted from the day of entry.",
            "Visa duration of stay is counted from the next day after entry.",
        ),
        (
            "visa_free.single_stay_days",
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a single stay of 30 days."
            ),
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a single stay of 60 days."
            ),
        ),
        (
            "visa_free.cumulative_stay_days",
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a cumulative stay of 90 days within 180 days."
            ),
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a cumulative stay of 120 days within 180 days."
            ),
        ),
        (
            "visa_free.rolling_window_days",
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a cumulative stay of 90 days within 180 days."
            ),
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a cumulative stay of 90 days within 365 days."
            ),
        ),
        (
            "visa_free.employment_allowed",
            (
                "Kazakhstan citizens under the bilateral visa-free agreement are "
                "not allowed to engage in local employment."
            ),
            (
                "Kazakhstan citizens under the bilateral visa-free agreement are "
                "allowed to engage in local employment."
            ),
        ),
        (
            "student.off_campus.university_approval",
            (
                "Foreign students holding student residence permits must obtain "
                "university approval for off-campus internships."
            ),
            (
                "Foreign students holding student residence permits do not need "
                "university approval for off-campus internships."
            ),
        ),
        (
            "student.off_campus.residence_endorsement",
            (
                "Foreign students holding student residence permits require an "
                "endorsement for off-campus internships."
            ),
            (
                "Foreign students holding student residence permits do not need "
                "an endorsement for off-campus internships."
            ),
        ),
        (
            "residence_application.after_entry_days",
            "X1 visa holders must apply for a residence permit within 30 days after entry.",
            "X1 visa holders must apply for a residence permit within 60 days after entry.",
        ),
        (
            "visa_extension.before_expiry_days",
            (
                "Visa holders must submit an extension application 7 days before "
                "the permitted stay expiry."
            ),
            (
                "Visa holders must submit an extension application 30 days before "
                "the permitted stay expiry."
            ),
        ),
        (
            "residence_extension.before_expiry_days",
            (
                "Residence permit holders must submit a renewal application 30 "
                "days before permit expiry."
            ),
            (
                "Residence permit holders must submit a renewal application 7 "
                "days before permit expiry."
            ),
        ),
        (
            "accommodation.registration_required",
            "Foreigners in private homes must complete accommodation registration.",
            "Foreigners in private homes do not need accommodation registration.",
        ),
        (
            "accommodation.online_registration_accepted",
            (
                "For foreigners in private homes, online accommodation "
                "registration is accepted with legal effect."
            ),
            (
                "For foreigners in private homes, online accommodation "
                "registration is not accepted with legal effect."
            ),
        ),
        (
            "accommodation.repeat_registration_required",
            (
                "Foreigners in private homes returning to the same habitual home "
                "with the same valid residence permit must complete repeat "
                "accommodation registration."
            ),
            (
                "Foreigners in private homes returning to the same habitual home "
                "with the same valid residence permit do not need repeat "
                "accommodation registration."
            ),
        ),
    ],
)
def test_explicit_assertions_detected(rule_id, left, right):
    found = detected(left, right)
    assert [item.rule_id for item in found] == [rule_id]
    assert found[0].quotes == [left, right]
    assert found[0].conflict_kind == "potential_contradiction"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (
            "Виза «Въехать до» означает последнюю дату въезда.",
            "Виза «Въехать до» означает последнюю дату выезда.",
        ),
        (
            "Срок пребывания по визе считается со дня въезда.",
            "Срок пребывания по визе считается со следующего дня после въезда.",
        ),
        ("签证入境有效期是最后入境日期。", "签证入境有效期是离境截止日期。"),
        ("签证停留期自入境之日计算。", "签证停留期从入境次日起计算。"),
        (
            "哈萨克斯坦公民持普通护照按照双边免签协定单次停留不超过30日。",
            "哈萨克斯坦公民持普通护照按照双边免签协定单次停留不超过60日。",
        ),
        (
            "哈萨克斯坦公民按照双边免签协定每180日累计停留不超过90日。",
            "哈萨克斯坦公民按照双边免签协定每180日累计停留不超过120日。",
        ),
        ("哈萨克斯坦公民按照双边免签协定不得就业。", "哈萨克斯坦公民按照双边免签协定可以就业。"),
        (
            "外国留学生持学习居留许可参加校外实习需要学校批准。",
            "外国留学生持学习居留许可参加校外实习无需学校批准。",
        ),
        (
            (
                "Иностранные студенты со студенческим ВНЖ обязаны получить "
                "одобрение университета для стажировки вне кампуса."
            ),
            (
                "Иностранные студенты со студенческим ВНЖ не должны получать "
                "одобрение университета для стажировки вне кампуса."
            ),
        ),
    ],
)
def test_multilingual_explicit_assertions(left, right):
    assert detected(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a cumulative stay of 90 days within 180 days."
            ),
            (
                "British citizens under the unilateral visa-free policy have no "
                "limit on total days of stay within 180 days."
            ),
        ),
        (
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a single stay of 30 days."
            ),
            (
                "Kazakhstan citizens under the unilateral visa-free policy have a "
                "single stay of 60 days."
            ),
        ),
        (
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a single stay of 30 days."
            ),
            "Kazakhstan citizens have a single visa-free stay of 60 days.",
        ),
        (
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a single stay of 30 days."
            ),
            (
                "Kazakhstan citizens with ordinary passports under the bilateral "
                "visa-free agreement have a single stay of 60 days."
            ),
        ),
        ("Visa validity permits entry for 90 days.", "Visa duration of stay is 30 days."),
        (
            "Visa Enter Before is the last permitted entry date.",
            "Residence permit expiry is the last permitted departure date.",
        ),
        (
            "X1 visa holders must apply for a residence permit within 30 days after entry.",
            "X2 visa holders must apply for a residence permit within 60 days after entry.",
        ),
        (
            "X1 visa holders must apply for a residence permit within 30 days after entry.",
            "The authority must issue an X1 residence permit within 15 days after entry.",
        ),
        (
            (
                "Visa holders must submit an extension application 7 days before "
                "permitted stay expiry."
            ),
            (
                "Residence permit holders must submit a renewal application 30 "
                "days before permit expiry."
            ),
        ),
        (
            (
                "Foreign students holding student residence permits must obtain "
                "university approval for off-campus internships."
            ),
            (
                "Foreign students holding student residence permits do not need "
                "university approval for on-campus internships."
            ),
        ),
        (
            (
                "Foreign students holding student residence permits must obtain "
                "university approval for off-campus internships."
            ),
            (
                "Foreign students with an X2 visa do not need university approval "
                "for off-campus internships."
            ),
        ),
        (
            (
                "Kazakhstan citizens under the bilateral visa-free agreement are "
                "not allowed to engage in local employment."
            ),
            (
                "Kazakhstan citizens under the bilateral visa-free agreement are "
                "allowed to attend business meetings."
            ),
        ),
        (
            "Foreigners in private homes must complete accommodation registration.",
            "Foreigners in hotels do not need to complete accommodation registration personally.",
        ),
        (
            "Foreigners in private homes must complete accommodation registration.",
            "Foreigners in private homes do not need accommodation registration?",
        ),
        (
            "Foreigners in private homes must complete accommodation registration.",
            (
                "Foreigners in private homes do not need accommodation "
                "registration. Except when staying longer than one day."
            ),
        ),
        (
            "Foreigners in private homes must complete accommodation registration.",
            "I stayed with a friend and did not need accommodation registration.",
        ),
        (
            "Visa Enter Before is the last permitted entry date.",
            "Visa Enter Before used to be the last permitted departure date.",
        ),
        (
            "Visa Enter Before is the last permitted entry date.",
            "If a restriction applies, Visa Enter Before is the last permitted departure date.",
        ),
        (
            (
                "Foreigners in private homes returning to the same habitual home "
                "with the same valid residence permit must complete repeat "
                "accommodation registration."
            ),
            (
                "Foreigners in private homes returning to a different home with a "
                "valid residence permit do not need repeat accommodation "
                "registration."
            ),
        ),
        (
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "a cumulative stay of 90 days within 180 days."
            ),
            (
                "Kazakhstan citizens under the bilateral visa-free agreement have "
                "no limit on total days of stay."
            ),
        ),
    ],
)
def test_different_or_unknown_conditions_are_not_conflicts(left, right):
    assert detected(left, right) == []


def test_explicit_nonoverlapping_effective_dates_are_not_compared():
    left = (
        "Effective from 2023-01-01 until 2023-12-31, visa Enter Before is "
        "the last permitted entry date."
    )
    right = (
        "Effective from 2024-01-01 until 2024-12-31, visa Enter Before is "
        "the last permitted departure date."
    )
    assert detected(left, right) == []


def test_publication_dates_do_not_become_effective_dates():
    claims = extract_visa_claims(
        source(
            "Visa Enter Before is the last permitted entry date.", date_published=date(2026, 1, 1)
        )
    )
    assert claims[0].valid_from is None
    assert claims[0].valid_until is None


def test_source_scenario_and_city_remain_comparison_boundaries():
    left = "Visa Enter Before is the last permitted entry date."
    right = "Visa Enter Before is the last permitted departure date."
    assert detected(left, right, city="Shanghai") == []
    assert detected(left, right, scenario=UserScenario.work) == []


def test_overlong_quote_does_not_raise():
    assert (
        extract_visa_claims(
            source("x" * 901 + " Visa Enter Before is the last permitted entry date.")
        )
        == []
    )


@pytest.mark.parametrize(
    "quote",
    [
        "Foreign students holding student residence permits require university approval "
        "but do not need an endorsement for off-campus internships.",
        "Foreign students holding student residence permits must not obtain university "
        "approval for off-campus internships.",
        "Visa Enter Before is not the last permitted departure date.",
        "Visa holders must submit an extension application 7 days before entry validity expiry.",
        "Foreigners in private homes holding residence permits "
        "do not need accommodation registration.",
        "In Kazakhstan, the visa Enter Before is the last permitted departure date.",
    ],
)
def test_negation_or_missing_critical_action_scope_requires_manual_review(quote):
    assert extract_visa_claims(source(quote)) == []


def test_explicit_effective_period_is_retained_with_exact_quote():
    quote = (
        "Effective from 2023-01-01 until 2023-12-31, "
        "visa Enter Before is the last permitted entry date."
    )
    claims = extract_visa_claims(source(quote))
    assert len(claims) == 1
    assert claims[0].valid_from == date(2023, 1, 1)
    assert claims[0].valid_until == date(2023, 12, 31)
    assert claims[0].quote == quote


def test_university_approval_and_endorsement_are_independent_obligations():
    quote = (
        "Foreign students holding student residence permits require university approval "
        "and an endorsement for off-campus internships."
    )
    assert {claim.rule_id for claim in extract_visa_claims(source(quote))} == {
        "student.off_campus.university_approval",
        "student.off_campus.residence_endorsement",
    }


def test_may_not_employment_is_a_prohibition():
    quote = (
        "Kazakhstan citizens under the bilateral visa-free agreement "
        "may not engage in local employment."
    )
    claims = extract_visa_claims(source(quote))
    assert claims[0].value == "not_allowed"


def test_denied_numeric_threshold_is_not_an_asserted_limit():
    quote = (
        "Kazakhstan citizens under the bilateral visa-free agreement "
        "have not a single stay of 30 days."
    )
    assert extract_visa_claims(source(quote)) == []


def test_paid_and_unpaid_student_internships_have_distinct_scope():
    left = (
        "Foreign students holding student residence permits require university approval "
        "for paid off-campus internships."
    )
    right = (
        "Foreign students holding student residence permits do not need university approval "
        "for unpaid off-campus internships."
    )
    assert extract_visa_claims(source(left))
    assert extract_visa_claims(source(right))
    assert detected(left, right) == []


@pytest.mark.parametrize(
    "quote",
    [
        "Foreigners in private homes must complete accommodation registration "
        "on arrival after a change of address.",
        "Foreigners in private homes do not need accommodation registration "
        "for short daytime visits.",
    ],
)
def test_narrow_registration_triggers_are_not_initial_arrival_defaults(quote):
    assert extract_visa_claims(source(quote)) == []


def test_actual_visa_stay_count_wording_suggests_review_without_inventing_effective_dates():
    left = source(
        '"Duration of each stay" refers to the maximum days the holder is permitted '
        "to stay in China on each visit, which is calculated from "
        "the next day of your entry into China.",
        "CVASC",
        date_published=date(2026, 8, 24),
    )
    left.title = "What kind of information does Chinese visa include?"
    right = source(
        "The Duration of Each Stay refers to the maximum number of days a visa holder is permitted "
        "to stay in China after each entry, namely, the maximum number of days a visa holder "
        "can stay in China from the day of entry.",
        "GOV",
        date_published=date(2020, 8, 4),
    )
    claims = extract_visa_claims(left) + extract_visa_claims(right)
    found = compare_claims(claims)
    assert len(found) == 1
    assert found[0].rule_id == "visa.stay_count_anchor"
    assert all(claim.valid_from is None and claim.valid_until is None for claim in claims)
    assert all(quote in (left.content, right.content) for quote in found[0].quotes)


def test_full_article_other_conditions_do_not_suppress_a_remote_independent_visa_rule():
    article = (
        "If an entry is refused, ask the authority about the decision.\n\n"
        "Visa Enter Before is the last permitted entry date.\n\n"
        "Some exceptional cases require additional documents."
    )
    assert [claim.rule_id for claim in extract_visa_claims(source(article))] == [
        "visa.enter_before_meaning"
    ]


@pytest.mark.parametrize(
    "quote",
    [
        "Foreigners in private homes do not need to complete "
        "accommodation registration personally.",
        "Kazakhstan citizens under the bilateral visa-free agreement with Kyrgyzstan "
        "have a single stay of 30 days.",
    ],
)
def test_scope_specific_to_submitter_or_another_country_is_not_generalized(quote):
    assert extract_visa_claims(source(quote)) == []


def test_domestic_and_international_returns_are_different_scopes():
    left = (
        "Foreigners in private homes returning from domestic travel to the same habitual home "
        "with the same valid residence permit must complete repeat accommodation registration."
    )
    right = (
        "Foreigners in private homes returning from abroad to the same habitual home "
        "with the same valid residence permit do not need repeat accommodation registration."
    )
    assert extract_visa_claims(source(left))
    assert extract_visa_claims(source(right))
    assert detected(left, right) == []
