import pytest

from shared.validators import parse_string_list


class TestParseStringList:
    def test_json_array_string(self):
        result = parse_string_list('["http://a.com","http://b.com"]')
        assert result == ["http://a.com", "http://b.com"]

    def test_comma_separated_string(self):
        result = parse_string_list("http://a.com,http://b.com")
        assert result == ["http://a.com", "http://b.com"]

    def test_comma_separated_with_whitespace(self):
        result = parse_string_list("http://a.com , http://b.com")
        assert result == ["http://a.com", "http://b.com"]

    def test_passthrough_list(self):
        origins = ["http://a.com", "http://b.com"]
        result = parse_string_list(origins)
        assert result == origins

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list("")

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON array"):
            parse_string_list("[not valid json")

    def test_json_mixed_types_array_raises(self):
        with pytest.raises(ValueError, match="must be an array of strings"):
            parse_string_list('["http://a.com", 123]')

    def test_json_empty_array_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list("[]")

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list([])

    def test_comma_separated_skips_empty_segments(self):
        result = parse_string_list("http://a.com,,http://b.com,")
        assert result == ["http://a.com", "http://b.com"]

    def test_comma_only_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list(",")

    def test_multiple_commas_only_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_string_list(",,,,")
