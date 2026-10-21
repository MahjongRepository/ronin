import pytest

from shared.validators import parse_string_list


class TestParseStringList:
    def test_parse_string_list__when_json_array_string__should_return_items(self):
        result = parse_string_list('["http://a.com","http://b.com"]')
        assert result == ["http://a.com", "http://b.com"]

    def test_parse_string_list__when_comma_separated__should_return_items(self):
        result = parse_string_list("http://a.com,http://b.com")
        assert result == ["http://a.com", "http://b.com"]

    def test_parse_string_list__when_comma_separated_with_whitespace__should_strip_items(self):
        result = parse_string_list("http://a.com , http://b.com")
        assert result == ["http://a.com", "http://b.com"]

    def test_parse_string_list__when_list__should_pass_through(self):
        origins = ["http://a.com", "http://b.com"]
        result = parse_string_list(origins)
        assert result == origins

    def test_parse_string_list__when_empty_string__should_raise(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list("")

    def test_parse_string_list__when_invalid_json__should_raise(self):
        with pytest.raises(ValueError, match="Invalid JSON array"):
            parse_string_list("[not valid json")

    def test_parse_string_list__when_json_array_has_non_strings__should_raise(self):
        with pytest.raises(ValueError, match="must be an array of strings"):
            parse_string_list('["http://a.com", 123]')

    def test_parse_string_list__when_json_array_empty__should_raise(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list("[]")

    def test_parse_string_list__when_list_empty__should_raise(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list([])

    def test_parse_string_list__when_comma_separated_has_empty_segments__should_skip_them(self):
        result = parse_string_list("http://a.com,,http://b.com,")
        assert result == ["http://a.com", "http://b.com"]

    def test_parse_string_list__when_single_comma__should_raise(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list(",")

    def test_parse_string_list__when_only_commas__should_raise(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list(",,,,")

    def test_parse_string_list__when_allow_empty_and_list_empty__should_return_empty(self):
        assert parse_string_list([], allow_empty=True) == []

    def test_parse_string_list__when_allow_empty_and_json_array_empty__should_return_empty(self):
        assert parse_string_list("[]", allow_empty=True) == []

    def test_parse_string_list__when_allow_empty_and_only_commas__should_return_empty(self):
        assert parse_string_list(",", allow_empty=True) == []

    def test_parse_string_list__when_allow_empty_and_empty_string__should_raise(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list("", allow_empty=True)
