from src.config import ALLOWED_TEST_NUMBER, assert_allowed_destination


def test_only_allows_challenge_number():
    assert_allowed_destination(ALLOWED_TEST_NUMBER)


def test_blocks_other_numbers():
    blocked = "+14155550123"
    try:
        assert_allowed_destination(blocked)
        raised = False
    except ValueError:
        raised = True
    assert raised
