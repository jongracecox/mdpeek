import pytest

from mdpeek.options import CacheBackend, Engine, Format, Mode, OnTableError, coerce

ALL_ENUMS = [Mode, OnTableError, Format, Engine, CacheBackend]


@pytest.mark.parametrize("enum_cls", ALL_ENUMS)
def test_members_pass_through(enum_cls):
    for member in enum_cls:
        assert coerce(enum_cls, member) is member


@pytest.mark.parametrize("enum_cls", ALL_ENUMS)
def test_strings_are_case_insensitive(enum_cls):
    for member in enum_cls:
        assert coerce(enum_cls, member.value) is member
        assert coerce(enum_cls, member.value.upper()) is member


@pytest.mark.parametrize("enum_cls", ALL_ENUMS)
def test_invalid_value_lists_choices(enum_cls):
    with pytest.raises(ValueError) as exc:
        coerce(enum_cls, "nope")
    for member in enum_cls:
        assert member.value in str(exc.value)


def test_non_string_is_rejected():
    with pytest.raises(ValueError):
        coerce(Mode, 3)  # type: ignore[arg-type]
