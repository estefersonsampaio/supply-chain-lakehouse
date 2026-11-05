"""Generator settings."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class GeneratorConfig:
    """All knobs of the simulation.

    The same config (and seed) always produces the same files. Running with more
    days produces the same files for the first days plus new ones, which is what
    an incremental ingestion needs.
    """

    seed: int = 42
    start_date: date = date(2026, 1, 5)
    days: int = 60
    n_finished: int = 12
    n_components: int = 30
    n_suppliers: int = 10
    n_customers: int = 3
    import_share: float = 0.3
    horizon_days: int = 20
    firm_days: int = 5
    dirty_rate: float = 0.02

    def __post_init__(self) -> None:
        if self.days < 1:
            raise ValueError("days must be at least 1")
        if not 0 <= self.dirty_rate <= 1:
            raise ValueError("dirty_rate must be between 0 and 1")
        if self.firm_days > self.horizon_days:
            raise ValueError("firm_days cannot be greater than horizon_days")
