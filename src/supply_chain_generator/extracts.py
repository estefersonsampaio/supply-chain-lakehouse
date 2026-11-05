"""Layout of the nine ERP extracts.

Column names follow the style of a classic ERP: a two-letter table prefix and short
uppercase names (B1_COD, C7_QUANT...). Material codes are padded with spaces to 15
characters, as fixed-width ERP fields usually are. The silver layer translates all of
this into clean English names; the mapping is in docs/data-dictionary.md.
"""

from dataclasses import dataclass

MATERIAL_CODE_WIDTH = 15


@dataclass(frozen=True)
class ExtractSpec:
    name: str
    columns: tuple[str, ...]
    snapshot: bool = False
    code_columns: tuple[str, ...] = ()
    reference_columns: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()
    qty_columns: tuple[str, ...] = ()
    unit_column: str | None = None


EXTRACTS: dict[str, ExtractSpec] = {
    spec.name: spec
    for spec in (
        ExtractSpec(
            name="materials",
            columns=("B1_COD", "B1_DESC", "B1_TIPO", "B1_UM", "B1_PE", "B1_ESTSEG", "B1_PROC"),
            snapshot=True,
            code_columns=("B1_COD",),
            qty_columns=("B1_ESTSEG",),
            unit_column="B1_UM",
        ),
        ExtractSpec(
            name="bom",
            columns=("G1_COD", "G1_COMP", "G1_QUANT"),
            snapshot=True,
            code_columns=("G1_COD", "G1_COMP"),
            reference_columns=("G1_COMP",),
            qty_columns=("G1_QUANT",),
        ),
        ExtractSpec(
            name="suppliers",
            columns=("A2_COD", "A2_LOJA", "A2_NOME", "A2_PAIS"),
            snapshot=True,
        ),
        ExtractSpec(
            name="customers",
            columns=("A1_COD", "A1_LOJA", "A1_NOME", "A1_PAIS"),
            snapshot=True,
        ),
        ExtractSpec(
            name="customer_schedules",
            columns=(
                "ZA1_CLIENT",
                "ZA1_LOJA",
                "ZA1_PROD",
                "ZA1_RELEAS",
                "ZA1_DTEMIS",
                "ZA1_DTENT",
                "ZA1_QUANT",
                "ZA1_TIPO",
            ),
            code_columns=("ZA1_PROD",),
            reference_columns=("ZA1_PROD",),
            date_columns=("ZA1_DTEMIS", "ZA1_DTENT"),
            qty_columns=("ZA1_QUANT",),
        ),
        ExtractSpec(
            name="purchase_orders",
            columns=(
                "C7_NUM",
                "C7_ITEM",
                "C7_FORNECE",
                "C7_LOJA",
                "C7_PRODUTO",
                "C7_UM",
                "C7_QUANT",
                "C7_EMISSAO",
                "C7_DATPRF",
            ),
            code_columns=("C7_PRODUTO",),
            reference_columns=("C7_PRODUTO",),
            date_columns=("C7_EMISSAO", "C7_DATPRF"),
            qty_columns=("C7_QUANT",),
            unit_column="C7_UM",
        ),
        ExtractSpec(
            name="goods_receipts",
            columns=(
                "D1_DOC",
                "D1_FORNECE",
                "D1_LOJA",
                "D1_PEDIDO",
                "D1_ITEMPC",
                "D1_COD",
                "D1_QUANT",
                "D1_DTDIGIT",
            ),
            code_columns=("D1_COD",),
            reference_columns=("D1_COD",),
            date_columns=("D1_DTDIGIT",),
            qty_columns=("D1_QUANT",),
        ),
        ExtractSpec(
            name="inventory_movements",
            columns=("D3_DOC", "D3_TM", "D3_COD", "D3_LOCAL", "D3_QUANT", "D3_EMISSAO"),
            code_columns=("D3_COD",),
            reference_columns=("D3_COD",),
            date_columns=("D3_EMISSAO",),
            qty_columns=("D3_QUANT",),
        ),
        ExtractSpec(
            name="shipments",
            columns=(
                "D2_DOC",
                "D2_ITEM",
                "D2_CLIENTE",
                "D2_LOJA",
                "D2_COD",
                "D2_QUANT",
                "D2_EMISSAO",
            ),
            code_columns=("D2_COD",),
            reference_columns=("D2_COD",),
            date_columns=("D2_EMISSAO",),
            qty_columns=("D2_QUANT",),
        ),
    )
}

# Inventory movement types (D3_TM). As in many ERPs, codes up to 499 are entries and
# codes from 500 up are exits.
TM_PRODUCTION_ENTRY = "001"
TM_INITIAL_BALANCE = "499"
TM_CONSUMPTION = "501"


def pad_code(code: str) -> str:
    return code.ljust(MATERIAL_CODE_WIDTH)


def format_qty(value: float) -> str:
    """Plain decimal text with a dot, no trailing zeros (120, 12.5, 0.25)."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"
