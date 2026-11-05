# Data dictionary

The generator writes ERP-style extracts: short uppercase column names with a table prefix, dates as `YYYYMMDD` text, material codes padded with spaces to 15 characters, and `;` as separator. Silver renames every column to the clean name below.

## Conventions in the raw files

| Convention | Example | Silver treatment |
|---|---|---|
| Dates as text `YYYYMMDD` | `20260105` | Parsed to `DATE`; impossible dates go to quarantine |
| Material codes padded to 15 characters | `PA0001␣␣␣␣␣␣␣␣␣` | Trimmed and uppercased |
| "Loja" (branch) of a customer or supplier | `01` | Kept as `store` |
| Movement type `D3_TM`: below 500 = entry, 500 and above = exit | `001`, `501` | Mapped to `direction` (`IN` / `OUT`) |
| Material type `B1_TIPO` | `PA` finished product, `MP` component | Mapped to `material_type` |
| Schedule type `ZA1_TIPO` | `F` firm, `P` forecast | Mapped to `schedule_type` |

## Extracts

### materials (material master, full snapshot)

| Raw | Silver | Description |
|---|---|---|
| `B1_COD` | `material_code` | Material code |
| `B1_DESC` | `description` | Description |
| `B1_TIPO` | `material_type` | `PA` finished product or `MP` component |
| `B1_UM` | `unit` | Unit of measure (`PC`, `KG`, `L`) |
| `B1_PE` | `lead_time_days` | Purchase or production lead time, calendar days |
| `B1_ESTSEG` | `safety_stock` | Safety stock, in the material unit |
| `B1_PROC` | `main_supplier_code` | Main supplier (components only) |

### bom (bill of materials, full snapshot)

| Raw | Silver | Description |
|---|---|---|
| `G1_COD` | `parent_material_code` | Finished product |
| `G1_COMP` | `component_material_code` | Component |
| `G1_QUANT` | `qty_per` | Component quantity per unit of the parent |

### suppliers (full snapshot)

| Raw | Silver | Description |
|---|---|---|
| `A2_COD` | `supplier_code` | Supplier code |
| `A2_LOJA` | `store` | Branch |
| `A2_NOME` | `name` | Name |
| `A2_PAIS` | `country` | Country code; anything other than `BR` is an importer |

### customers (full snapshot)

| Raw | Silver | Description |
|---|---|---|
| `A1_COD` | `customer_code` | Customer code |
| `A1_LOJA` | `store` | Branch |
| `A1_NOME` | `name` | Name (anonymous automakers: `OEM_A`, `OEM_B`...) |
| `A1_PAIS` | `country` | Country code |

### customer_schedules (delivery schedules sent by customers, incremental)

Every business day each customer sends a new release covering the next 20 business days. The first 5 days are firm, the rest is forecast. A new release revises the previous one.

| Raw | Silver | Description |
|---|---|---|
| `ZA1_CLIENT` | `customer_code` | Customer |
| `ZA1_LOJA` | `store` | Branch |
| `ZA1_PROD` | `material_code` | Finished product |
| `ZA1_RELEAS` | `release_number` | Release sequence per customer |
| `ZA1_DTEMIS` | `release_date` | Date the release was issued |
| `ZA1_DTENT` | `due_date` | Requested delivery date |
| `ZA1_QUANT` | `quantity` | Requested quantity |
| `ZA1_TIPO` | `schedule_type` | `F` firm or `P` forecast |

### purchase_orders (incremental)

| Raw | Silver | Description |
|---|---|---|
| `C7_NUM` | `po_number` | Purchase order number |
| `C7_ITEM` | `po_item` | Line number |
| `C7_FORNECE` | `supplier_code` | Supplier |
| `C7_LOJA` | `store` | Supplier branch |
| `C7_PRODUTO` | `material_code` | Component ordered |
| `C7_UM` | `unit` | Unit of measure |
| `C7_QUANT` | `quantity` | Ordered quantity |
| `C7_EMISSAO` | `order_date` | Order date |
| `C7_DATPRF` | `promised_date` | Date promised by the supplier |

### goods_receipts (incremental)

| Raw | Silver | Description |
|---|---|---|
| `D1_DOC` | `invoice_number` | Supplier invoice |
| `D1_FORNECE` | `supplier_code` | Supplier |
| `D1_LOJA` | `store` | Supplier branch |
| `D1_PEDIDO` | `po_number` | Purchase order received |
| `D1_ITEMPC` | `po_item` | Purchase order line |
| `D1_COD` | `material_code` | Component received |
| `D1_QUANT` | `quantity` | Received quantity (deliveries can be partial) |
| `D1_DTDIGIT` | `receipt_date` | Receipt date |

### inventory_movements (incremental)

| Raw | Silver | Description |
|---|---|---|
| `D3_DOC` | `movement_doc` | Movement document |
| `D3_TM` | `movement_type` | `499` initial balance, `001` production entry, `501` consumption |
| `D3_COD` | `material_code` | Material |
| `D3_LOCAL` | `warehouse` | Warehouse |
| `D3_QUANT` | `quantity` | Quantity (always positive; the direction comes from the type) |
| `D3_EMISSAO` | `movement_date` | Movement date |

Stock of a material = initial balance + receipts + production entries − consumption − shipments.

### shipments (incremental)

| Raw | Silver | Description |
|---|---|---|
| `D2_DOC` | `shipment_doc` | Shipping document |
| `D2_ITEM` | `shipment_item` | Line number |
| `D2_CLIENTE` | `customer_code` | Customer |
| `D2_LOJA` | `store` | Customer branch |
| `D2_COD` | `material_code` | Finished product shipped |
| `D2_QUANT` | `quantity` | Shipped quantity |
| `D2_EMISSAO` | `shipment_date` | Shipment date |

## Planted problems

Controlled by `--dirty-rate` (default 2% of rows). Each affected row gets exactly one problem, and every problem is counted in `_manifest/manifest_<YYYYMMDD>.json`.

| Problem | What it looks like |
|---|---|
| `duplicate` | The same row twice (a file line sent again) |
| `code_format` | `pa0001`, ` PA0001`, code without padding |
| `invalid_date` | `00000000`, empty, `20260230`, `20261131` |
| `unit_variant` | `pc`, `UN`, `pcs`, `kg`, `LT`; or `G` with the quantity multiplied by 1000 |
| `bad_quantity` | `0` or a negative quantity |
| `decimal_comma` | `12,5` instead of `12.5` |
| `orphan_reference` | A material code that does not exist (`XX4821`) |
