import pytest

from scripts.artmaks_cell_qr_mapping import parse_mapping


def test_csv_bom_header_and_duplicates():
    rows = [f"А-1-{index};QR-{index}" for index in range(882)]
    raw = ("address;barcode\n" + "\n".join(rows)).encode("utf-8-sig")
    parsed = parse_mapping(raw)
    assert len(parsed) == 882
    assert parsed["А-1-0"] == "QR-0"
    with pytest.raises(ValueError, match="duplicate address"):
        parse_mapping(("\n".join(rows) + "\nА-1-0;OTHER").encode())
    with pytest.raises(ValueError, match="duplicate barcode"):
        parse_mapping(("\n".join(rows) + "\nOTHER;QR-0").encode())
    with pytest.raises(ValueError, match="Expected 882"):
        parse_mapping(b"address;barcode\nA-1-1;QR-1")
