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
    NAREDBA = "naredba"
    PRAVILNIK = "pravilnik"
    POSTANOVLENIE = "postanovlenie"
    UKAZ = "ukaz"
    RESHENIE_KS = "reshenie_ks"
    RESHENIE_NS = "reshenie_ns"


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
    act_type: Mapped[ActType] = mapped_column(Enum(ActType, name="act_type"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_short: Mapped[Optional[str]] = mapped_column(Text)
    number: Mapped[Optional[str]] = mapped_column(Text)
    adoption_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    dv_broy: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_year: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_position: Mapped[int] = mapped_column(Integer, nullable=False)
    issuing_body: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ActStatus] = mapped_column(Enum(ActStatus, name="act_status"), nullable=False)

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
        Enum(ElementType, name="element_type"), nullable=False
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
    operation: Mapped[AmendmentOp] = mapped_column(Enum(AmendmentOp, name="amendment_op"), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Reference(Base):
    __tablename__ = "reference"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_expression_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expression.id", ondelete="CASCADE"), nullable=False
    )
    source_e_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_work_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="SET NULL")
    )
    target_e_id: Mapped[Optional[str]] = mapped_column(Text)
    reference_type: Mapped[ReferenceType] = mapped_column(
        Enum(ReferenceType, name="reference_type"), nullable=False
    )


class ExternalId(Base):
    __tablename__ = "external_id"
    __table_args__ = (UniqueConstraint("work_id", "source"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[ExternalSource] = mapped_column(
        Enum(ExternalSource, name="external_source"), nullable=False
    )
    external_value: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)

    work: Mapped[Work] = relationship(back_populates="external_ids")
