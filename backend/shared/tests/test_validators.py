import pytest

from shared.validators import parse_cors_origins


class TestParseCorsOrigins:
    def test_json_array_string(self):
        result = parse_cors_origins('["http://a.com","http://b.com"]')
        assert result == ["http://a.com", "http://b.com"]

    def test_comma_separated_string(self):
        result = parse_cors_origins("http://a.com,http://b.com")
        assert result == ["http://a.com", "http://b.com"]

    def test_comma_separated_with_whitespace(self):
        result = parse_cors_origins("http://a.com , http://b.com")
        assert result == ["http://a.com", "http://b.com"]

    def test_passthrough_list(self):
        origins = ["http://a.com", "http://b.com"]
        result = parse_cors_origins(origins)
        assert result == origins

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_cors_origins("")

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON array"):
            parse_cors_origins("[not valid json")

    def test_json_mixed_types_array_raises(self):
        with pytest.raises(ValueError, match="must be an array of strings"):
            parse_cors_origins('["http://a.com", 123]')

    def test_json_empty_array(self):
        result = parse_cors_origins("[]")
        assert result == []

    def test_comma_separated_skips_empty_segments(self):
        result = parse_cors_origins("http://a.com,,http://b.com,")
        assert result == ["http://a.com", "http://b.com"]
