"""Silver layout: raw ERP column -> clean English column, with the rule kind to apply.

Kinds:
    code  material code: trimmed and uppercased; flagged if it was not in the
          standard ERP format (uppercase, padded to 15 characters)
    id    other identifiers (documents, suppliers, customers): trimmed
    text  free text: trimmed
    int   integer
    date  YYYYMMDD text -> DATE; impossible dates are quarantined
    qty   quantity -> DECIMAL(18,3); decimal commas are fixed; negative values (and zero,
          unless zero is valid for the extract) are quarantined
    unit  unit of measure, normalized to PC / KG / L (grams are converted to KG)

Every extract carries the ERP internal record number (R_E_C_N_O_ -> erp_record_id). It
never changes, so it links a quarantined row to the corrected version that the source
sends later.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Col:
    raw: str
    name: str
    kind: str = "text"


@dataclass(frozen=True)
class SilverSpec:
    extract: str
    columns: tuple[Col, ...]
    key: tuple[str, ...]
    snapshot: bool = False
    references: tuple[str, ...] = ()  # clean columns that must exist in materials
    zero_qty_allowed: bool = False

    @property
    def raw_columns(self) -> list[str]:
        return [c.raw for c in self.columns]

    def of_kind(self, kind: str) -> list[Col]:
        return [c for c in self.columns if c.kind == kind]


SPECS: tuple[SilverSpec, ...] = (
    SilverSpec(
        extract="materials",
        columns=(
            Col("B1_COD", "material_code", "code"),
            Col("B1_DESC", "description"),
            Col("B1_TIPO", "material_type"),
            Col("B1_UM", "unit", "unit"),
            Col("B1_PE", "lead_time_days", "int"),
            Col("B1_ESTSEG", "safety_stock", "qty"),
            Col("B1_PROC", "main_supplier_code", "id"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("material_code",),
        snapshot=True,
        zero_qty_allowed=True,
    ),
    SilverSpec(
        extract="bom",
        columns=(
            Col("G1_COD", "parent_material_code", "code"),
            Col("G1_COMP", "component_material_code", "code"),
            Col("G1_QUANT", "qty_per", "qty"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("parent_material_code", "component_material_code"),
        snapshot=True,
        references=("parent_material_code", "component_material_code"),
    ),
    SilverSpec(
        extract="suppliers",
        columns=(
            Col("A2_COD", "supplier_code", "id"),
            Col("A2_LOJA", "store", "id"),
            Col("A2_NOME", "name"),
            Col("A2_PAIS", "country"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("supplier_code",),
        snapshot=True,
    ),
    SilverSpec(
        extract="customers",
        columns=(
            Col("A1_COD", "customer_code", "id"),
            Col("A1_LOJA", "store", "id"),
            Col("A1_NOME", "name"),
            Col("A1_PAIS", "country"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("customer_code",),
        snapshot=True,
    ),
    SilverSpec(
        extract="customer_schedules",
        columns=(
            Col("ZA1_CLIENT", "customer_code", "id"),
            Col("ZA1_LOJA", "store", "id"),
            Col("ZA1_PROD", "material_code", "code"),
            Col("ZA1_RELEAS", "release_number", "id"),
            Col("ZA1_DTEMIS", "release_date", "date"),
            Col("ZA1_DTENT", "due_date", "date"),
            Col("ZA1_QUANT", "quantity", "qty"),
            Col("ZA1_TIPO", "schedule_type"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("customer_code", "material_code", "release_number", "due_date"),
        references=("material_code",),
        zero_qty_allowed=True,
    ),
    SilverSpec(
        extract="purchase_orders",
        columns=(
            Col("C7_NUM", "po_number", "id"),
            Col("C7_ITEM", "po_item", "id"),
            Col("C7_FORNECE", "supplier_code", "id"),
            Col("C7_LOJA", "store", "id"),
            Col("C7_PRODUTO", "material_code", "code"),
            Col("C7_UM", "unit", "unit"),
            Col("C7_QUANT", "quantity", "qty"),
            Col("C7_EMISSAO", "order_date", "date"),
            Col("C7_DATPRF", "promised_date", "date"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("po_number", "po_item"),
        references=("material_code",),
    ),
    SilverSpec(
        extract="goods_receipts",
        columns=(
            Col("D1_DOC", "invoice_number", "id"),
            Col("D1_FORNECE", "supplier_code", "id"),
            Col("D1_LOJA", "store", "id"),
            Col("D1_PEDIDO", "po_number", "id"),
            Col("D1_ITEMPC", "po_item", "id"),
            Col("D1_COD", "material_code", "code"),
            Col("D1_QUANT", "quantity", "qty"),
            Col("D1_DTDIGIT", "receipt_date", "date"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("invoice_number", "po_number", "po_item"),
        references=("material_code",),
    ),
    SilverSpec(
        extract="inventory_movements",
        columns=(
            Col("D3_DOC", "movement_doc", "id"),
            Col("D3_TM", "movement_type", "id"),
            Col("D3_COD", "material_code", "code"),
            Col("D3_LOCAL", "warehouse", "id"),
            Col("D3_QUANT", "quantity", "qty"),
            Col("D3_EMISSAO", "movement_date", "date"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("movement_doc",),
        references=("material_code",),
    ),
    SilverSpec(
        extract="shipments",
        columns=(
            Col("D2_DOC", "shipment_doc", "id"),
            Col("D2_ITEM", "shipment_item", "id"),
            Col("D2_CLIENTE", "customer_code", "id"),
            Col("D2_LOJA", "store", "id"),
            Col("D2_COD", "material_code", "code"),
            Col("D2_QUANT", "quantity", "qty"),
            Col("D2_EMISSAO", "shipment_date", "date"),
            Col("R_E_C_N_O_", "erp_record_id", "int"),
        ),
        key=("shipment_doc", "shipment_item"),
        references=("material_code",),
    ),
)

SPEC_BY_EXTRACT = {spec.extract: spec for spec in SPECS}
