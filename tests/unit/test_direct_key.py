import uuid

from app.services.conversation_service import direct_key


def test_direct_key_is_symmetric_and_sorted():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert direct_key(a, b) == direct_key(b, a)
    first, second = direct_key(a, b).split(":")
    assert first < second


def test_direct_key_fits_the_column():
    assert len(direct_key(uuid.uuid4(), uuid.uuid4())) <= 80
