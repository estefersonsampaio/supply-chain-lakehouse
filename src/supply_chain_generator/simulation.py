"""Day-by-day simulation of the plant.

Each business day, in this order:

1. goods arrive from suppliers (receipts against open purchase order lines);
2. production covers the firm customer demand of the next two business days,
   limited by the components in stock (consumption follows the bill of materials);
3. shipments send what each customer scheduled as firm for today;
4. each customer sends a new delivery schedule (release) for the next business days;
5. a simple MRP reorder rule creates purchase orders for components.

The output is clean, consistent data. Data problems are added later, in dirt.py.
"""

import math
import random
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta

from supply_chain_generator.business_calendar import (
    add_business_days,
    business_days,
    erp_date,
    roll_forward,
)
from supply_chain_generator.config import GeneratorConfig
from supply_chain_generator.extracts import (
    TM_CONSUMPTION,
    TM_INITIAL_BALANCE,
    TM_PRODUCTION_ENTRY,
    format_qty,
    pad_code,
)
from supply_chain_generator.master_data import MasterData, build_master_data

STORE = "01"  # ERP "loja" (branch of a customer or supplier)
WAREHOUSE = "01"
PRODUCTION_COVER_DAYS = 2


@dataclass
class OpenPoLine:
    number: str
    item: str
    supplier: str
    material: str
    qty_open: float
    arrival: date


@dataclass
class DayOutput:
    day: date
    rows: dict[str, list[dict[str, str]]] = field(default_factory=dict)


class Simulator:
    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self.rng = random.Random(config.seed)
        self.master: MasterData = build_master_data(
            self.rng,
            n_finished=config.n_finished,
            n_components=config.n_components,
            n_suppliers=config.n_suppliers,
            n_customers=config.n_customers,
            import_share=config.import_share,
        )
        self.stock: dict[str, float] = defaultdict(float)
        self.open_po: list[OpenPoLine] = []
        # (customer, material, due date) -> firm quantity from the latest release
        self.firm: dict[tuple[str, str, date], int] = {}
        # (customer, material, due date) -> quantity in the latest release (firm or not)
        self.last_qty: dict[tuple[str, str, date], int] = {}
        self.release_seq: dict[str, int] = defaultdict(int)
        self.seq: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------ helpers
    def _next(self, counter: str, width: int) -> str:
        self.seq[counter] += 1
        return str(self.seq[counter]).zfill(width)

    def _lead_business_days(self, calendar_days: int) -> int:
        return max(1, round(calendar_days * 5 / 7))

    def _qty(self, value: float, unit: str) -> float:
        return float(math.floor(value)) if unit == "PC" else round(value, 2)

    # ---------------------------------------------------------------- snapshots
    def master_rows(self) -> dict[str, list[dict[str, str]]]:
        m = self.master
        return {
            "materials": [
                {
                    "B1_COD": pad_code(mat.code),
                    "B1_DESC": mat.description,
                    "B1_TIPO": mat.mtype,
                    "B1_UM": mat.unit,
                    "B1_PE": str(mat.lead_time_days),
                    "B1_ESTSEG": format_qty(mat.safety_stock),
                    "B1_PROC": mat.supplier,
                }
                for mat in m.materials.values()
            ],
            "bom": [
                {
                    "G1_COD": pad_code(line.parent),
                    "G1_COMP": pad_code(line.component),
                    "G1_QUANT": format_qty(line.qty_per),
                }
                for line in m.bom
            ],
            "suppliers": [
                {"A2_COD": s.code, "A2_LOJA": STORE, "A2_NOME": s.name, "A2_PAIS": s.country}
                for s in m.suppliers.values()
            ],
            "customers": [
                {"A1_COD": c.code, "A1_LOJA": STORE, "A1_NOME": c.name, "A1_PAIS": c.country}
                for c in m.customers.values()
            ],
        }

    # -------------------------------------------------------------------- steps
    def _initial_balance(self, day: date) -> list[dict[str, str]]:
        rows = []
        for mat in self.master.materials.values():
            if mat.mtype == "PA":
                qty = math.ceil(3 * mat.daily_usage)
            else:
                lead = self._lead_business_days(mat.lead_time_days)
                qty = self._qty(mat.safety_stock + mat.daily_usage * (lead + 5), mat.unit)
                if qty == 0:
                    qty = 100.0 if mat.unit == "PC" else 50.0
            self.stock[mat.code] = float(qty)
            rows.append(self._movement(day, TM_INITIAL_BALANCE, mat.code, qty))
        return rows

    def _movement(self, day: date, tm: str, material: str, qty: float) -> dict[str, str]:
        return {
            "D3_DOC": self._next("D3_DOC", 9),
            "D3_TM": tm,
            "D3_COD": pad_code(material),
            "D3_LOCAL": WAREHOUSE,
            "D3_QUANT": format_qty(qty),
            "D3_EMISSAO": erp_date(day),
        }

    def _receive(self, day: date) -> list[dict[str, str]]:
        rows = []
        arriving = [line for line in self.open_po if line.arrival == day]
        invoices: dict[str, str] = {}
        for line in arriving:
            unit = self.master.materials[line.material].unit
            qty = line.qty_open
            if self.rng.random() < 0.08:  # partial delivery, the rest comes later
                qty = self._qty(line.qty_open * self.rng.uniform(0.7, 0.95), unit)
            if qty <= 0:
                qty = line.qty_open
            if line.supplier not in invoices:
                invoices[line.supplier] = "NF" + self._next("D1_DOC", 9)
            rows.append(
                {
                    "D1_DOC": invoices[line.supplier],
                    "D1_FORNECE": line.supplier,
                    "D1_LOJA": STORE,
                    "D1_PEDIDO": line.number,
                    "D1_ITEMPC": line.item,
                    "D1_COD": pad_code(line.material),
                    "D1_QUANT": format_qty(qty),
                    "D1_DTDIGIT": erp_date(day),
                }
            )
            self.stock[line.material] += qty
            line.qty_open = round(line.qty_open - qty, 3)
            if line.qty_open > 0:
                line.arrival = add_business_days(day, self.rng.randint(2, 6))
        self.open_po = [line for line in self.open_po if line.qty_open > 0]
        return rows

    def _firm_demand(self, material: str, start: date, n_days: int) -> int:
        days = {add_business_days(start, i) for i in range(n_days)}
        return sum(
            qty for (_, mat, due), qty in self.firm.items() if mat == material and due in days
        )

    def _produce(self, day: date) -> list[dict[str, str]]:
        rows = []
        for product in self.master.finished():
            need = (
                self._firm_demand(product.code, day, PRODUCTION_COVER_DAYS)
                + product.safety_stock
                - self.stock[product.code]
            )
            if need <= 0:
                continue
            bom = self.master.bom_of(product.code)
            feasible = min(self.stock[line.component] / line.qty_per for line in bom)
            qty = math.floor(min(need, feasible))
            if qty <= 0:
                continue
            rows.append(self._movement(day, TM_PRODUCTION_ENTRY, product.code, qty))
            self.stock[product.code] += qty
            for line in bom:
                unit = self.master.materials[line.component].unit
                used = round(qty * line.qty_per, 3) if unit != "PC" else qty * line.qty_per
                rows.append(self._movement(day, TM_CONSUMPTION, line.component, used))
                self.stock[line.component] = round(self.stock[line.component] - used, 3)
        return rows

    def _ship(self, day: date) -> list[dict[str, str]]:
        rows = []
        for customer, items in self.master.customer_items.items():
            doc = None
            item_no = 0
            for material in items:
                due = self.firm.get((customer, material, day), 0)
                if due <= 0:
                    continue
                qty = min(due, math.floor(self.stock[material]))
                if qty > 0 and self.rng.random() < 0.04:  # short shipment
                    qty = math.floor(qty * 0.8)
                if qty <= 0:
                    continue
                if doc is None:
                    doc = self._next("D2_DOC", 9)
                item_no += 1
                rows.append(
                    {
                        "D2_DOC": doc,
                        "D2_ITEM": str(item_no).zfill(2),
                        "D2_CLIENTE": customer,
                        "D2_LOJA": STORE,
                        "D2_COD": pad_code(material),
                        "D2_QUANT": format_qty(qty),
                        "D2_EMISSAO": erp_date(day),
                    }
                )
                self.stock[material] -= qty
        return rows

    def _release_schedules(self, day: date) -> list[dict[str, str]]:
        rows = []
        cfg = self.config
        for customer, items in self.master.customer_items.items():
            self.release_seq[customer] += 1
            release = str(self.release_seq[customer]).zfill(6)
            for material, base in items.items():
                for i in range(1, cfg.horizon_days + 1):
                    due = add_business_days(day, i)
                    key = (customer, material, due)
                    firm = i <= cfg.firm_days
                    previous = self.firm.get(key)
                    if previous is not None and self.rng.random() < 0.85:
                        qty = previous  # firm quantities rarely change
                    elif key in self.last_qty and self.rng.random() < 0.6:
                        qty = max(0, round(self.last_qty[key] * self.rng.uniform(0.9, 1.1)))
                    else:
                        qty = max(0, round(base * self.rng.gauss(1.0, 0.15)))
                    self.last_qty[key] = qty
                    if firm:
                        self.firm[key] = qty
                    rows.append(
                        {
                            "ZA1_CLIENT": customer,
                            "ZA1_LOJA": STORE,
                            "ZA1_PROD": pad_code(material),
                            "ZA1_RELEAS": release,
                            "ZA1_DTEMIS": erp_date(day),
                            "ZA1_DTENT": erp_date(due),
                            "ZA1_QUANT": format_qty(qty),
                            "ZA1_TIPO": "F" if firm else "P",
                        }
                    )
        return rows

    def _purchase(self, day: date) -> list[dict[str, str]]:
        rows = []
        orders: dict[str, tuple[str, int]] = {}  # supplier -> (PO number, last item)
        for mat in self.master.components():
            if mat.daily_usage <= 0:
                continue
            lead = self._lead_business_days(mat.lead_time_days)
            reorder_point = mat.safety_stock + mat.daily_usage * lead
            on_order = sum(line.qty_open for line in self.open_po if line.material == mat.code)
            position = self.stock[mat.code] + on_order
            if position >= reorder_point:
                continue
            raw = reorder_point - position + mat.daily_usage * 15
            lot = 100 if mat.unit == "PC" else 10
            qty = float(math.ceil(raw / lot) * lot)
            number, item = orders.get(mat.supplier, (self._next("C7_NUM", 6), 0))
            item += 1
            orders[mat.supplier] = (number, item)
            promised = roll_forward(day + timedelta(days=mat.lead_time_days))
            arrival = add_business_days(promised, self._delivery_delay(mat.supplier))
            if arrival <= day:
                arrival = add_business_days(day, 1)
            item_code = str(item).zfill(4)
            self.open_po.append(OpenPoLine(number, item_code, mat.supplier, mat.code, qty, arrival))
            rows.append(
                {
                    "C7_NUM": number,
                    "C7_ITEM": item_code,
                    "C7_FORNECE": mat.supplier,
                    "C7_LOJA": STORE,
                    "C7_PRODUTO": pad_code(mat.code),
                    "C7_UM": mat.unit,
                    "C7_QUANT": format_qty(qty),
                    "C7_EMISSAO": erp_date(day),
                    "C7_DATPRF": erp_date(promised),
                }
            )
        return rows

    def _delivery_delay(self, supplier_code: str) -> int:
        """Business days between the promised date and the real arrival (negative = early)."""
        r = self.rng.random()
        if self.master.suppliers[supplier_code].importer:
            if r < 0.4:
                return self.rng.randint(-3, 0)
            if r < 0.8:
                return self.rng.randint(1, 7)
            return self.rng.randint(8, 20)
        if r < 0.05:
            return -1
        if r < 0.75:
            return 0
        if r < 0.93:
            return self.rng.randint(1, 2)
        return self.rng.randint(3, 5)

    # ---------------------------------------------------------------------- run
    def run(self) -> Iterator[DayOutput]:
        cfg = self.config
        master_rows = self.master_rows()
        first = True
        for day in business_days(cfg.start_date, cfg.days):
            out = DayOutput(day=day, rows={name: list(rows) for name, rows in master_rows.items()})
            movements = self._initial_balance(day) if first else []
            first = False
            out.rows["goods_receipts"] = self._receive(day)
            movements += self._produce(day)
            out.rows["inventory_movements"] = movements
            out.rows["shipments"] = self._ship(day)
            out.rows["customer_schedules"] = self._release_schedules(day)
            out.rows["purchase_orders"] = self._purchase(day)
            yield out
