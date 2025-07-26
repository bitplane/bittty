from pytest import raises

from example_package.program import add_two_numbers


def test_add_two_numbers():
    result = add_two_numbers(1, 1)

    assert result == 2


def test_add_two_strings():
    """
    Example failing test
    """
    with raises(ValueError):
        add_two_numbers(1, 1)
