"""WMS-680: contract for the serialized document lines used by printing."""

from app.api.inbound_intake import InboundIntakeLineOut
from app.api.outbound_shipment import OutboundShipmentLineOut
from app.api.packaging_tasks import PackagingTaskLineOut


def test_c680_03_and_c680_07_document_line_payloads_expose_own_variant_size_and_color() -> None:
    """The three real print routes cannot rely on a delayed frontend catalogue."""
    for response_line in (
        InboundIntakeLineOut,
        PackagingTaskLineOut,
        OutboundShipmentLineOut,
    ):
        fields = response_line.model_fields
        assert {"size", "wb_size"}.intersection(fields), response_line.__name__
        assert {"color", "wb_color"}.intersection(fields), response_line.__name__
