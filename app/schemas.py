from typing import Literal

from pydantic import BaseModel, Field, model_validator

EntryType = Literal["food", "drink", "exercise"]


class ParsedEntrySchema(BaseModel):
    type: EntryType
    name: str = ""
    calories_in: int | None = None
    calories_out: int | None = None

    @model_validator(mode="after")
    def one_side_set(self) -> "ParsedEntrySchema":
        cin = self.calories_in if self.calories_in is not None else 0
        cout = self.calories_out if self.calories_out is not None else 0
        if cin > 0 and cout > 0:
            raise ValueError("entry must not set both calories_in and calories_out")
        if cin <= 0 and cout <= 0:
            raise ValueError("entry needs positive calories_in or calories_out")
        return self


class LLMParseResponse(BaseModel):
    entries: list[ParsedEntrySchema] = Field(default_factory=list)
