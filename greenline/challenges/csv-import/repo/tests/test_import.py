import pytest

from customer_import import ImportFormatError, import_customers


def test_valid_file_is_normalized() -> None:
    result = import_customers(b"external_id,email,age\n c-1 ,ADA@EXAMPLE.COM,36\n")
    assert result.accepted == ({"external_id": "c-1", "email": "ada@example.com", "age": 36},)
    assert result.rejected == ()


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (",nobody@example.com,20", "missing_external_id"),
        ("   ,nobody@example.com,20", "missing_external_id"),
        ("c-1,not-an-email,20", "invalid_email"),
        ("c-1,@example.com,20", "invalid_email"),
        ("c-1,nobody@,20", "invalid_email"),
        ("c-1,nobody@example.com,unknown", "invalid_age"),
        ("c-1,nobody@example.com,-1", "invalid_age"),
        ("c-1,nobody@example.com,", "invalid_age"),
    ],
)
def test_invalid_row_is_quarantined(row: str, reason: str) -> None:
    payload = f"external_id,email,age\n{row}\n".encode()

    result = import_customers(payload)

    assert result.accepted == ()
    assert result.rejected == ({"row": 2, "reason": reason},)


def test_bad_rows_are_quarantined_while_later_good_rows_keep_source_order() -> None:
    payload = (
        b"external_id,email,age\n"
        b" c-1 ,ADA@EXAMPLE.COM,36\n"
        b"c-2,not-an-email,20\n"
        b"c-3,grace@example.com,42\n"
        b",nobody@example.com,20\n"
        b"c-4,LINUS@EXAMPLE.COM,55\n"
    )

    result = import_customers(payload)

    assert result.accepted == (
        {"external_id": "c-1", "email": "ada@example.com", "age": 36},
        {"external_id": "c-3", "email": "grace@example.com", "age": 42},
        {"external_id": "c-4", "email": "linus@example.com", "age": 55},
    )
    assert result.rejected == (
        {"row": 3, "reason": "invalid_email"},
        {"row": 5, "reason": "missing_external_id"},
    )


def test_utf8_bom_is_not_part_of_first_header() -> None:
    result = import_customers("\ufeffexternal_id,email,age\nc-1,a@example.com,9\n".encode())
    assert result.accepted[0]["external_id"] == "c-1"


@pytest.mark.parametrize(
    ("header", "missing"),
    [
        ("external_id,email", "age"),
        ("external_id,age", "email"),
        ("email,age", "external_id"),
    ],
)
def test_missing_schema_is_a_file_error(header: str, missing: str) -> None:
    with pytest.raises(ImportFormatError, match=f"missing columns: {missing}"):
        import_customers(f"{header}\nvalue,value\n".encode())


@pytest.mark.parametrize("invalid_byte", [b"\xff", b"\xfe"])
def test_invalid_utf8_is_a_file_error(invalid_byte: bytes) -> None:
    with pytest.raises(ImportFormatError, match="UTF-8"):
        import_customers(b"external_id,email,age\nc-1," + invalid_byte + b",9\n")
