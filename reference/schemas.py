# =====================================================================
# [1105 3교시 필기] schemas.py : Pydantic 요청(Request) / 응답(Response) 스키마
# =====================================================================
# - SQLAlchemy 모델(models.py) : 데이터베이스 테이블과 연결되는 객체
# - Pydantic 모델(schemas.py)  : API 요청 데이터 검증 및 응답 JSON 직렬화
# =====================================================================

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    name: str
    age: int


class UserResponse(BaseModel):
    # SQLAlchemy ORM 객체(User)의 속성(user.id, user.name, user.age)을 읽어서
    # 바로 Pydantic 응답 모델로 변환할 수 있도록 허용하는 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int


class OrderCreate(BaseModel):
    item_name: str
    price: int


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_name: str
    price: int
    user_id: int


class UserWithOrdersResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int
    orders: list[OrderResponse] = []

