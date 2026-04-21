import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DvRef(BaseModel):
    broy: int
    year: int
    position: Optional[int] = None


class WorkOut(BaseModel):
    uri: str
    title: str
    title_short: Optional[str] = None
    type: str
    dv_ref: DvRef
    external_ids: dict[str, str] = Field(default_factory=dict)


class ExpressionOut(BaseModel):
    date: dt.date
    lang: str
    is_latest: bool = False


class ElementOut(BaseModel):
    e_id: str
    type: str
    num: Optional[str] = None
    heading: Optional[str] = None
    text: Optional[str] = None
    children: list["ElementOut"] = Field(default_factory=list)


class Links(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    self: str
    akn_xml: Optional[str] = None
    rdf: Optional[str] = None
    work: Optional[str] = None
    expression: Optional[str] = None
    previous_versions: list[str] = Field(default_factory=list)


class ResourceOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    uri: str
    work: WorkOut
    expression: Optional[ExpressionOut] = None
    element: Optional[ElementOut] = None
    links: Links = Field(alias="_links")


class WorkListItem(BaseModel):
    uri: str
    title: str
    type: str
    dv_ref: DvRef


class WorkList(BaseModel):
    items: list[WorkListItem]
    total: int
    page: int
    page_size: int
