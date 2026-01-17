from app.core.timeline_mentions import normalize_mentions


def test_normalize_mentions_trims_lowercases_strips_at_and_dedupes():
    assert normalize_mentions([" User@Test.com ", "@user@test.com", "", "  ", "2", "2"]) == [
        "user@test.com",
        "2",
    ]


def test_normalize_mentions_empty_list_returns_empty():
    assert normalize_mentions([]) == []
