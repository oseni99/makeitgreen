# Import contract

Required columns are `external_id`, `email`, and `age`. A missing column invalidates the file. Invalid UTF-8 also invalidates the file.

After a valid header, bad rows are quarantined as `{row, reason}` and processing continues. Reasons are `missing_external_id`, `invalid_email`, or `invalid_age`. CSV row numbers include the header, so the first data row is row 2.
