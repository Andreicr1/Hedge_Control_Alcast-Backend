import pytest

from app.core.timeline_threads import thread_key_for


def test_thread_key_for_is_deterministic():
    assert thread_key_for("rfq", 123) == "rfq:123"
    assert thread_key_for("rfq", 123) == "rfq:123"


@pytest.mark.parametrize(
    "subject_type,subject_id",
    [
        ("", 1),
        ("rfq", 0),
        ("rfq", -1),
    ],
)
def test_thread_key_for_rejects_invalid_inputs(subject_type, subject_id):
    with pytest.raises(ValueError):
        thread_key_for(subject_type, subject_id)
