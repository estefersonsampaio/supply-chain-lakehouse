"""Master data: materials, bill of materials, suppliers and customers.

Everything is fictional. Customers are anonymous automakers (OEM_A, OEM_B...) and
suppliers are numbered.
"""

import math
import random
from dataclasses import dataclass, field

FINISHED_PARTS = (
    "ENGINE MOUNT BRACKET",
    "CONTROL ARM",
    "STEERING KNUCKLE",
    "BRAKE PEDAL ASSY",
    "SEAT FRAME",
    "DOOR HINGE",
    "EXHAUST HANGER",
    "RADIATOR SUPPORT",
    "BUMPER BEAM",
    "FUEL TANK STRAP",
    "PARKING BRAKE LEVER",
    "HOOD LATCH",
    "TOW HOOK",
    "BATTERY TRAY",
    "SHOCK ABSORBER MOUNT",
)

COMPONENTS = (
    ("STEEL SHEET 2MM", "KG"),
    ("STEEL SHEET 3MM", "KG"),
    ("STEEL TUBE 25MM", "KG"),
    ("ALUMINIUM BAR", "KG"),
    ("HEX BOLT M8X20", "PC"),
    ("HEX BOLT M10X30", "PC"),
    ("NUT M8", "PC"),
    ("NUT M10", "PC"),
    ("WASHER 8MM", "PC"),
    ("RUBBER BUSHING", "PC"),
    ("BALL JOINT", "PC"),
    ("BEARING 6204", "PC"),
    ("SPRING CLIP", "PC"),
    ("RIVET 4MM", "PC"),
    ("WELDING WIRE", "KG"),
    ("BLACK PAINT", "L"),
    ("PRIMER", "L"),
    ("ZINC COATING", "KG"),
    ("PLASTIC CAP", "PC"),
    ("CABLE ASSY", "PC"),
    ("HINGE PIN", "PC"),
    ("SPOT WELD NUT", "PC"),
    ("GASKET", "PC"),
    ("LOCK PLATE", "PC"),
    ("STEEL WIRE 5MM", "KG"),
    ("POWDER COAT", "KG"),
    ("SEALANT", "L"),
    ("LABEL", "PC"),
    ("PACKAGING BOX", "PC"),
    ("PALLET", "PC"),
)

DOMESTIC_COUNTRY = "BR"
IMPORT_COUNTRIES = ("DE", "CN", "JP", "US", "IT")


@dataclass
class Supplier:
    code: str
    name: str
    country: str

    @property
    def importer(self) -> bool:
        return self.country != DOMESTIC_COUNTRY


@dataclass
class Customer:
    code: str
    name: str
    country: str = DOMESTIC_COUNTRY


@dataclass
class Material:
    code: str
    description: str
    mtype: str  # PA = finished product, MP = raw material / component
    unit: str
    lead_time_days: int  # calendar days
    supplier: str = ""
    safety_stock: float = 0.0
    daily_usage: float = 0.0  # average daily demand (PA) or consumption (MP)


@dataclass
class BomLine:
    parent: str
    component: str
    qty_per: float


@dataclass
class MasterData:
    materials: dict[str, Material]
    bom: list[BomLine]
    suppliers: dict[str, Supplier]
    customers: dict[str, Customer]
    # customer code -> {finished material code: base daily quantity}
    customer_items: dict[str, dict[str, int]] = field(default_factory=dict)

    def finished(self) -> list[Material]:
        return [m for m in self.materials.values() if m.mtype == "PA"]

    def components(self) -> list[Material]:
        return [m for m in self.materials.values() if m.mtype == "MP"]

    def bom_of(self, parent: str) -> list[BomLine]:
        return [line for line in self.bom if line.parent == parent]


def _round_for_unit(value: float, unit: str) -> float:
    if unit == "PC":
        return float(math.ceil(value))
    return round(value, 2)


def build_master_data(
    rng: random.Random,
    n_finished: int,
    n_components: int,
    n_suppliers: int,
    n_customers: int,
    import_share: float,
) -> MasterData:
    if not 1 <= n_finished <= len(FINISHED_PARTS):
        raise ValueError(f"n_finished must be between 1 and {len(FINISHED_PARTS)}")
    if not 2 <= n_components <= len(COMPONENTS):
        raise ValueError(f"n_components must be between 2 and {len(COMPONENTS)}")
    if not 1 <= n_customers <= 26:
        raise ValueError("n_customers must be between 1 and 26")

    n_importers = round(n_suppliers * import_share)
    suppliers: dict[str, Supplier] = {}
    for i in range(1, n_suppliers + 1):
        country = rng.choice(IMPORT_COUNTRIES) if i <= n_importers else DOMESTIC_COUNTRY
        code = f"S{i:05d}"
        suppliers[code] = Supplier(code=code, name=f"SUPPLIER {i:02d}", country=country)

    materials: dict[str, Material] = {}
    for i, (name, unit) in enumerate(COMPONENTS[:n_components], start=1):
        supplier = rng.choice(list(suppliers.values()))
        lead_time = rng.randint(30, 60) if supplier.importer else rng.randint(5, 15)
        code = f"MP{i:04d}"
        materials[code] = Material(
            code=code,
            description=name,
            mtype="MP",
            unit=unit,
            lead_time_days=lead_time,
            supplier=supplier.code,
        )

    for i, name in enumerate(FINISHED_PARTS[:n_finished], start=1):
        code = f"PA{i:04d}"
        materials[code] = Material(
            code=code, description=name, mtype="PA", unit="PC", lead_time_days=1
        )

    component_codes = [m.code for m in materials.values() if m.mtype == "MP"]
    bom: list[BomLine] = []
    for parent in (m for m in materials.values() if m.mtype == "PA"):
        for component in rng.sample(
            component_codes, k=min(rng.randint(2, 4), len(component_codes))
        ):
            unit = materials[component].unit
            if unit == "PC":
                qty_per = float(rng.randint(1, 6))
            elif unit == "KG":
                qty_per = round(rng.uniform(0.2, 3.5), 2)
            else:
                qty_per = round(rng.uniform(0.05, 0.4), 2)
            bom.append(BomLine(parent=parent.code, component=component, qty_per=qty_per))

    customers = {
        f"C{i:05d}": Customer(code=f"C{i:05d}", name=f"OEM_{chr(64 + i)}")
        for i in range(1, n_customers + 1)
    }

    finished_codes = [m.code for m in materials.values() if m.mtype == "PA"]
    customer_items: dict[str, dict[str, int]] = {code: {} for code in customers}
    for code in customers:
        k = min(rng.randint(4, 8), len(finished_codes))
        for material in rng.sample(finished_codes, k=k):
            customer_items[code][material] = rng.randint(20, 200)
    # every finished product is sold to at least one customer
    for material in finished_codes:
        if not any(material in items for items in customer_items.values()):
            customer_items[rng.choice(list(customers))][material] = rng.randint(20, 200)

    master = MasterData(materials, bom, suppliers, customers, customer_items)
    _set_usage_and_safety_stock(master)
    return master


def _set_usage_and_safety_stock(master: MasterData) -> None:
    for material in master.finished():
        material.daily_usage = float(
            sum(items.get(material.code, 0) for items in master.customer_items.values())
        )
        material.safety_stock = float(math.ceil(2 * material.daily_usage))

    for line in master.bom:
        parent = master.materials[line.parent]
        master.materials[line.component].daily_usage += parent.daily_usage * line.qty_per

    for material in master.components():
        material.daily_usage = round(material.daily_usage, 3)
        material.safety_stock = _round_for_unit(5 * material.daily_usage, material.unit)
