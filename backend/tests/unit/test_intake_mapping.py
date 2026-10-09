from app.intake.domain.canonical_fields import SourceType, normalize, suggest


def test_aliases_and_ambiguity_are_deterministic() -> None:
    assert normalize(" 거래_일자 ") == "거래일자"
    result = suggest(SourceType.SALES, 0, ("거래일", "amount", "unknown"))
    assert [m.status for m in result] == ["ALIAS_MATCH", "EXACT", "UNMAPPED"]
    duplicate = suggest(SourceType.SALES, 0, ("거래일", "date"))
    assert all(m.status == "AMBIGUOUS" and m.canonical_field_code is None for m in duplicate)
