from wybthon import email, max_length, min_length, required, validate


def test_required():
    assert validate("", [required()]) is not None
    assert validate("hi", [required()]) is None


def test_min_max_length():
    assert validate("a", [min_length(2)]) is not None
    assert validate("ab", [min_length(2)]) is None
    assert validate("abcd", [max_length(3)]) is not None


def test_email_validator():
    assert validate("test@example.com", [email()]) is None
    assert validate("not-an-email", [email()]) is not None
