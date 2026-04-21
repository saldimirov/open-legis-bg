import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DvRef(BaseModel):
    broy: int = Field(..., description="DV issue number (брой).")
    year: int = Field(..., description="Publication year.")
    position: Optional[int] = Field(None, description="Position within the issue (1-based). Null when unknown.")


class WorkOut(BaseModel):
    uri: str = Field(..., description="ELI URI of the work, e.g. `/eli/bg/zakon/2024/my-law`.")
    title: str = Field(..., description="Full official title of the act.")
    title_short: Optional[str] = Field(None, description="Short / colloquial title, if present.")
    type: str = Field(..., description="Act type key, e.g. `zakon`, `zid`, `byudjet`.")
    dv_ref: DvRef = Field(..., description="State Gazette reference where the act was first published.")
    external_ids: dict[str, str] = Field(default_factory=dict, description="Known external identifiers keyed by source.")


class ExpressionOut(BaseModel):
    date: dt.date = Field(..., description="Effective date of this version.")
    lang: str = Field(..., description="BCP-47 language code, e.g. `bul`.")
    is_latest: bool = Field(False, description="True if this is the most recent known version.")


class ElementOut(BaseModel):
    e_id: str = Field(..., description="AKN element identifier, e.g. `art_1` or `sec_final__para_3`.")
    type: str = Field(..., description="AKN element type: `article`, `paragraph`, `chapter`, `section`, etc.")
    num: Optional[str] = Field(None, description="Displayed number as it appears in the law, e.g. `Чл. 1.`")
    heading: Optional[str] = Field(None, description="Section or chapter heading text.")
    text: Optional[str] = Field(None, description="Plain-text content of the element (leaf nodes only).")
    children: list["ElementOut"] = Field(default_factory=list, description="Nested child elements.")


class Links(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    self: str = Field(..., description="Canonical URL of this resource.")
    akn_xml: Optional[str] = Field(None, description="URL for the Akoma Ntoso XML representation.")
    rdf: Optional[str] = Field(None, description="URL for the RDF Turtle representation.")
    work: Optional[str] = Field(None, description="URL of the parent work (present on expression/element resources).")
    expression: Optional[str] = Field(None, description="URL of the parent expression (present on element resources).")
    previous_versions: list[str] = Field(default_factory=list, description="URLs of earlier expressions, oldest first.")


class ResourceOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    uri: str = Field(..., description="ELI URI identifying this resource.")
    work: WorkOut
    expression: Optional[ExpressionOut] = Field(None, description="Present when the resource is an expression or element.")
    element: Optional[ElementOut] = Field(None, description="Present when the resource is a specific element.")
    links: Links = Field(alias="_links")


class WorkListItem(BaseModel):
    uri: str = Field(..., description="ELI URI of the work.")
    title: str = Field(..., description="Full official title.")
    type: str = Field(..., description="Act type key.")
    dv_ref: DvRef


class WorkList(BaseModel):
    items: list[WorkListItem]
    total: int = Field(..., description="Total matching works (across all pages).")
    page: int = Field(..., description="Current page number (1-based).")
    page_size: int = Field(..., description="Number of items per page.")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error message.", examples=["Work not found: /eli/bg/zakon/2024/my-law"])


class RateLimitResponse(BaseModel):
    error: str = Field(..., description="Rate limit exceeded message.", examples=["60 per 1 minute"])
