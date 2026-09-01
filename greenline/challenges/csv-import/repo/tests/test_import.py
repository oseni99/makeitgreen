import pytest

from customer_import import ImportFormatError, import_customers


def test_valid_file_is_normalized() -> None:
    result = import_customers(b"external_id,email,age\n c-1 ,ADA@EXAMPLE.COM,36\n")
    assert result.accepted == ({"external_id": "c-1", "email": "ada@example.com", "age": 36},)
    assert result.rejected == ()


def test_bad_rows_are_quarantined_without_losing_good_rows() -> None:
    payload = (
        b"external_id,email,age\n"
        b"c-1,ada@example.com,36\n"
        b"c-2,not-an-email,unknown\n"
        b",nobody@example.com,20\n"
        b"c-3,grace@example.com,42\n"
    )
    result = import_customers(payload)
    assert [row["external_id"] for row in result.accepted] == ["c-1", "c-3"]
    assert result.rejected == (
        {"row": 3, "reason": "invalid_email"},
        {"row": 4, "reason": "missing_external_id"},
    )


def test_utf8_bom_is_not_part_of_first_header() -> None:
    result = import_customers("\ufeffexternal_id,email,age\nc-1,a@example.com,9\n".encode())
    assert result.accepted[0]["external_id"] == "c-1"


def test_missing_schema_is_a_file_error() -> None:
    with pytest.raises(ImportFormatError, match="missing columns: age"):
        import_customers(b"external_id,email\nc-1,a@example.com\n")


def test_invalid_utf8_is_a_file_error() -> None:
    with pytest.raises(ImportFormatError, match="UTF-8"):
        import_customers(b"external_id,email,age\nc-1,\xff,9\n")
