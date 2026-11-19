# =====================================================================
# [1105 2~3교시 필기] models.py : SQLAlchemy 2.0 ORM 모델 정의
# =====================================================================
# ★ 수업 필기 오타 교정 포인트:
#   - `Interger`        -> `Integer`
#   - `autocrement=True`-> `autoincrement=True`
#   - `ForignKey`       -> `ForeignKey`
#   - `Mappde`          -> `Mapped`
# =====================================================================

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    """
    [2교시 & 3교시 핵심 모델] users 테이블과 매핑되는 Python 클래스
    """

    __tablename__ = "orm_users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    age: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # [3교시 5) 1:N 관계 매핑] 한 명의 User가 여러 개의 Order를 가질 수 있음
    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Order(Base):
    """
    [3교시 5) Users와 Orders 1:N 관계 및 JOIN 실습용 모델]
    """

    __tablename__ = "orm_orders"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    item_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("orm_users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # N:1 역방향 참조 (Order -> User)
    user: Mapped["User"] = relationship(
        "User",
        back_populates="orders",
    )

