from dataclasses import dataclass


@dataclass
class ParsedEntry:
    entry_type: str
    name: str
    calories_in: int | None = None
    calories_out: int | None = None

    def summary_fragment(self) -> str:
        if self.calories_in:
            return f"{self.name} ({self.calories_in} kcal in)"
        if self.calories_out:
            return f"{self.name} ({self.calories_out} kcal out)"
        return self.name
