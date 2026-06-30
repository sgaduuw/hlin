"""SQLAlchemy 2.0 models.

Two entity families (see CONTEXT.md "Why two entity families"):

* Tracked persons: ``Person`` and the care machinery hanging off it
  (``Appointment``, ``RecurringObligation``, ``VaccinationRecord``).
* Contacts: ``Contact`` (the kids' social network) linked to the
  children they belong to via ``ContactPersonLink``, and to a friend's
  parent via a self-referencing ``parent_contact_id``.

``role``/``status``/contact ``kind`` are constrained enums (small, stable
sets). ``Appointment.kind`` / ``RecurringObligation.kind`` are
deliberately free strings: an open-ended vocabulary that should not need
a migration to extend. ``APPOINTMENT_KINDS`` only suggests values for the
UI dropdown; nothing enforces it.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(enum.StrEnum):
    CHILD = "child"
    ADULT = "adult"  # the household grown-ups (maintainer + partner)
    ELDER = "elder"  # their parents


class AppointmentStatus(enum.StrEnum):
    DUE = "due"
    BOOKED = "booked"
    DONE = "done"
    CANCELLED = "cancelled"


class ContactKind(enum.StrEnum):
    FRIEND = "friend"
    PARENT = "parent"
    FAMILY = "family"
    OTHER = "other"


# Suggested appointment/obligation kinds for the UI dropdown. NOT enforced;
# the columns accept any string (see module docstring).
APPOINTMENT_KINDS: tuple[str, ...] = (
    "tandarts",
    "huisarts",
    "cjg",
    "specialist",
    "eye",
    "hearing",
    "other",
)


def _str_enum(enum_cls: type[enum.Enum]) -> SAEnum:
    """A non-native (VARCHAR + CHECK) enum column storing the member value."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=16,
        values_callable=lambda e: [member.value for member in e],
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Person(Base):
    """Someone the household actively tracks: a child, an adult, an elder."""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    role: Mapped[Role] = mapped_column(_str_enum(Role))
    bsn: Mapped[str | None] = mapped_column(String(16), nullable=True)
    huisarts: Mapped[str | None] = mapped_column(Text, nullable=True)
    tandarts: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    obligations: Mapped[list[RecurringObligation]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    vaccinations: Mapped[list[VaccinationRecord]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    friends: Mapped[list[Contact]] = relationship(
        secondary="contact_person_link", back_populates="linked_persons"
    )
    login: Mapped[User | None] = relationship(back_populates="person", uselist=False)

    @property
    def audit_label(self) -> str:
        return self.name


class Appointment(Base):
    __tablename__ = "appointment"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # loose vocabulary, unconstrained
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        _str_enum(AppointmentStatus), default=AppointmentStatus.DUE
    )
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    person: Mapped[Person] = relationship(back_populates="appointments")

    @property
    def audit_label(self) -> str:
        return f"{self.kind} for {self.person.name}"


class RecurringObligation(Base):
    __tablename__ = "recurring_obligation"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # loose vocabulary, unconstrained
    interval_months: Mapped[int] = mapped_column(Integer)
    # Drives the derived next-due date. NULL == never done, i.e. due now.
    last_done: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    person: Mapped[Person] = relationship(back_populates="obligations")

    @property
    def audit_label(self) -> str:
        return f"{self.kind} for {self.person.name}"


class VaccinationRecord(Base):
    __tablename__ = "vaccination_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    vaccine: Mapped[str] = mapped_column(String(120))
    where: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    person: Mapped[Person] = relationship(back_populates="vaccinations")

    @property
    def audit_label(self) -> str:
        return f"{self.vaccine} for {self.person.name}"


class ContactPersonLink(Base):
    """Many-to-many edge: a friend Contact belongs to one or more children."""

    __tablename__ = "contact_person_link"

    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), primary_key=True
    )


class Contact(Base):
    """A member of the kids' social network. Directory + birthday only.

    No care machinery: contacts deliberately have no appointments,
    obligations, or vaccination records (see CONTEXT.md). A friend points
    to their parent via ``parent_contact_id`` so one parent is stored once
    and reached from each of their children's rows.
    """

    __tablename__ = "contact"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[ContactKind] = mapped_column(_str_enum(ContactKind), default=ContactKind.FRIEND)
    parent_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contact.id", ondelete="SET NULL"), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent: Mapped[Contact | None] = relationship(remote_side=[id], back_populates="dependents")
    dependents: Mapped[list[Contact]] = relationship(back_populates="parent")
    linked_persons: Mapped[list[Person]] = relationship(
        secondary="contact_person_link", back_populates="friends"
    )

    @property
    def audit_label(self) -> str:
        return self.name


class User(Base):
    """A household login. Minimal multi-user auth: username + password hash,
    no roles (every user is a full editor), no self-registration (accounts
    are managed via the `flask user` CLI).

    A login MAY be linked to a tracked ``Person`` (``person_id``, optional
    1:1): "this login is me". Unique so two logins cannot claim the same
    person; ``SET NULL`` so deleting the person just unlinks the login
    (deleting people and revoking logins stay separate concerns)."""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), unique=True, nullable=True
    )

    person: Mapped[Person | None] = relationship(back_populates="login")


class AuditLog(Base):
    """Append-only record of who changed what, when. Written atomically with
    the change it describes (the same request session commits both), so the
    trail has no silent gaps.

    ``actor_*`` and ``target_*`` are weakly referenced (no foreign key): the
    actor username is snapshotted so a row stays readable after the login is
    deleted, and ``target_id`` outlives the row it documents (notably a
    deletion). A weak ``actor_user_id`` also means a stale session user id
    can never FK-violate the atomic write. See hlin/audit.py for the recorder
    and the ``AuditAction`` vocabulary."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
