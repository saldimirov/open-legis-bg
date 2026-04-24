import datetime as dt
import enum
import uuid
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ActType(str, enum.Enum):
    KONSTITUTSIYA = "konstitutsiya"
    KODEKS = "kodeks"
    ZAKON = "zakon"
    ZID = "zid"
    BYUDJET = "byudjet"
    NAREDBA = "naredba"
    PRAVILNIK = "pravilnik"
    POSTANOVLENIE = "postanovlenie"
    UKAZ = "ukaz"
    RESHENIE = "reshenie"
    INSTRUKTSIYA = "instruktsiya"
    TARIFA = "tarifa"
    ZAPOVED = "zapoved"
    DEKLARATSIYA = "deklaratsiya"
    OPREDELENIE = "opredelenie"
    DOGOVOR = "dogovor"
    SAOBSHTENIE = "saobshtenie"
    RATIFIKATSIYA = "ratifikatsiya"
    # Legacy compound reshenie_* values kept for DB backward compatibility
    RESHENIE_KS = "reshenie_ks"
    RESHENIE_NS = "reshenie_ns"
    RESHENIE_MS = "reshenie_ms"
    RESHENIE_KEVR = "reshenie_kevr"
    RESHENIE_KFN = "reshenie_kfn"
    RESHENIE_NHIF = "reshenie_nhif"


class Issuer(str, enum.Enum):
    NS = "ns"                   # Народно събрание
    MS = "ms"                   # Министерски съвет
    PRESIDENT = "president"     # Президент на Републиката
    MINISTRY = "ministry"       # Министерство
    COMMISSION = "commission"   # Регулаторна комисия (КЕВР, КФН, НЗОК …)
    AGENCY = "agency"           # Агенция
    COURT = "court"             # Съд (общо)
    KS = "ks"                   # Конституционен съд
    VAS = "vas"                 # Върховен административен съд
    VSS = "vss"                 # Висш съдебен съвет
    BNB = "bnb"                 # Българска народна банка
    MUNICIPALITY = "municipality"
    OTHER = "other"


class ActStatus(str, enum.Enum):
    IN_FORCE = "in_force"
    REPEALED = "repealed"
    PARTIALLY_IN_FORCE = "partially_in_force"


class ElementType(str, enum.Enum):
    PART = "part"
    TITLE = "title"
    CHAPTER = "chapter"
    SECTION = "section"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    POINT = "point"
    LETTER = "letter"
    HCONTAINER = "hcontainer"


class AmendmentOp(str, enum.Enum):
    INSERTION = "insertion"
    SUBSTITUTION = "substitution"
    REPEAL = "repeal"
    RENUMBERING = "renumbering"


class ConsolidationOpType(str, enum.Enum):
    # Element-level
    ELEMENT_SUBSTITUTION = "ELEMENT_SUBSTITUTION"  # whole element replaced
    ELEMENT_INSERTION = "ELEMENT_INSERTION"          # new element added
    ELEMENT_REPEAL = "ELEMENT_REPEAL"                # element marked отменен
    # Text-level (within an element)
    TEXT_SUBSTITUTION = "TEXT_SUBSTITUTION"          # word/phrase replaced
    TEXT_INSERTION = "TEXT_INSERTION"                # text appended/prepended
    TEXT_DELETION = "TEXT_DELETION"                  # text removed


class ConsolidationOpStatus(str, enum.Enum):
    PARSED = "PARSED"        # extracted by LLM, target_ref_raw populated
    RESOLVED = "RESOLVED"    # target_e_id matched to a real element
    APPLIED = "APPLIED"      # op applied to produce a consolidated expression
    FAILED = "FAILED"        # parse or resolution error


class ReferenceType(str, enum.Enum):
    CITES = "cites"
    DEFINES = "defines"


class ExternalSource(str, enum.Enum):
    LEX_BG = "lex_bg"
    PARLIAMENT_BG = "parliament_bg"
    DV_PARLIAMENT_BG = "dv_parliament_bg"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Work(Base):
    __tablename__ = "work"
    __table_args__ = (UniqueConstraint("dv_broy", "dv_year", "dv_position"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    eli_uri: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    act_type: Mapped[ActType] = mapped_column(Enum(ActType, name="act_type", values_callable=lambda x: [e.value for e in x]), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_short: Mapped[Optional[str]] = mapped_column(Text)
    number: Mapped[Optional[str]] = mapped_column(Text)
    adoption_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    dv_broy: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_year: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_position: Mapped[int] = mapped_column(Integer, nullable=False)
    issuing_body: Mapped[Optional[str]] = mapped_column(Text)
    issuer: Mapped[Optional[Issuer]] = mapped_column(Enum(Issuer, name="issuer", values_callable=lambda x: [e.value for e in x]), nullable=True)
    status: Mapped[ActStatus] = mapped_column(Enum(ActStatus, name="act_status", values_callable=lambda x: [e.value for e in x]), nullable=False)

    expressions: Mapped[list["Expression"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
    external_ids: Mapped[list["ExternalId"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class Expression(Base):
    __tablename__ = "expression"
    __table_args__ = (UniqueConstraint("work_id", "expression_date", "language"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    expression_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="bul")
    akn_xml: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    work: Mapped[Work] = relationship(back_populates="expressions")
    elements: Mapped[list["Element"]] = relationship(
        back_populates="expression", cascade="all, delete-orphan"
    )


class Element(Base):
    __tablename__ = "element"
    __table_args__ = (UniqueConstraint("expression_id", "e_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    expression_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expression.id", ondelete="CASCADE"), nullable=False
    )
    e_id: Mapped[str] = mapped_column(Text, nullable=False)
    parent_e_id: Mapped[Optional[str]] = mapped_column(Text)
    element_type: Mapped[ElementType] = mapped_column(
        Enum(ElementType, name="element_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    num: Mapped[Optional[str]] = mapped_column(Text)
    heading: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[Optional[str]] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    expression: Mapped[Expression] = relationship(back_populates="elements")


class Amendment(Base):
    __tablename__ = "amendment"

    id: Mapped[uuid.UUID] = _uuid_pk()
    amending_work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    target_work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    target_e_id: Mapped[Optional[str]] = mapped_column(Text)
    operation: Mapped[AmendmentOp] = mapped_column(Enum(AmendmentOp, name="amendment_op", values_callable=lambda x: [e.value for e in x]), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    ops: Mapped[list["ConsolidationOp"]] = relationship(
        back_populates="amendment", cascade="all, delete-orphan"
    )


class ConsolidationOp(Base):
    """One parsed operation extracted from a single § paragraph of a ZID.

    A single § can yield multiple ops (e.g. "се правят следните изменения:
    1. ... 2. ..."), hence sequence.
    """
    __tablename__ = "consolidation_op"

    id: Mapped[uuid.UUID] = _uuid_pk()
    amendment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amendment.id", ondelete="CASCADE"), nullable=False
    )
    source_e_id: Mapped[str] = mapped_column(Text, nullable=False)   # § e_id in ZID
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_ref_raw: Mapped[str] = mapped_column(Text, nullable=False)  # "чл. 32, ал. 5"
    target_e_id: Mapped[Optional[str]] = mapped_column(Text)           # resolved e_id
    op_type: Mapped[ConsolidationOpType] = mapped_column(
        Enum(ConsolidationOpType, name="consolidation_op_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    old_text: Mapped[Optional[str]] = mapped_column(Text)
    new_text: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ConsolidationOpStatus] = mapped_column(
        Enum(ConsolidationOpStatus, name="consolidation_op_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConsolidationOpStatus.PARSED,
    )
    error: Mapped[Optional[str]] = mapped_column(Text)

    amendment: Mapped[Amendment] = relationship(back_populates="ops")


class Reference(Base):
    __tablename__ = "reference"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_expression_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expression.id", ondelete="CASCADE"), nullable=False
    )
    source_e_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Verbatim text as it appears in the law — preserved for display and re-resolution
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Resolved target — nullable until the referenced law exists in the corpus
    target_work_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="SET NULL")
    )
    target_e_id: Mapped[Optional[str]] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_type: Mapped[ReferenceType] = mapped_column(
        Enum(ReferenceType, name="reference_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )


class ExternalId(Base):
    __tablename__ = "external_id"
    __table_args__ = (UniqueConstraint("work_id", "source"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[ExternalSource] = mapped_column(
        Enum(ExternalSource, name="external_source", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    external_value: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)

    work: Mapped[Work] = relationship(back_populates="external_ids")
