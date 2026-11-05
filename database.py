# database.py
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, ForeignKey, String, Float, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import os

# Si existe la variable de entorno DATABASE_URL (en la nube), usa PostgreSQL; si no, usa SQLite local
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///pokemon_analytics.db")

# Ajuste automático de prefijo para compatibilidad con servicios como Render (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

class Base(DeclarativeBase):
    pass

class UserModel(Base):
    """Representa a los usuarios del sistema (ej: 'david', 'amigo')."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True) # Nombre de usuario o ID
    name: Mapped[str] = mapped_column(String, nullable=False)

    rarity_configs: Mapped[List["SetRarityConfigModel"]] = relationship("SetRarityConfigModel", back_populates="user_rel", cascade="all, delete-orphan")


class SetModel(Base):
    __tablename__ = "sets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    release_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    total_cards: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pack_price_eur: Mapped[float] = mapped_column(Float, default=4.50)

    cards: Mapped[List["CardModel"]] = relationship("CardModel", back_populates="set_rel", cascade="all, delete-orphan")
    rarity_configs: Mapped[List["SetRarityConfigModel"]] = relationship("SetRarityConfigModel", back_populates="set_rel", cascade="all, delete-orphan")


class RarityModel(Base):
    __tablename__ = "rarities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    cards: Mapped[List["CardModel"]] = relationship("CardModel", back_populates="rarity_rel")
    rarity_configs: Mapped[List["SetRarityConfigModel"]] = relationship("SetRarityConfigModel", back_populates="rarity_rel")


class SetRarityConfigModel(Base):
    """Guarda la configuración única de Pull Rate y Precio Medio asociando User + Set + Rareza."""
    __tablename__ = "set_rarity_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, default="default_user")
    set_id: Mapped[str] = mapped_column(String, ForeignKey("sets.id"), nullable=False)
    rarity_id: Mapped[int] = mapped_column(Integer, ForeignKey("rarities.id"), nullable=False)
    
    pull_rate: Mapped[float] = mapped_column(Float, default=0.0)
    custom_avg_price: Mapped[Optional[float]] = mapped_column(Float, default=0.0)

    user_rel: Mapped["UserModel"] = relationship("UserModel", back_populates="rarity_configs")
    set_rel: Mapped["SetModel"] = relationship("SetModel", back_populates="rarity_configs")
    rarity_rel: Mapped["RarityModel"] = relationship("RarityModel", back_populates="rarity_configs")

    __table_args__ = (UniqueConstraint('user_id', 'set_id', 'rarity_id', name='_user_set_rarity_uc'),)


class CardModel(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    set_id: Mapped[str] = mapped_column(String, ForeignKey("sets.id"), nullable=False)
    rarity_id: Mapped[int] = mapped_column(Integer, ForeignKey("rarities.id"), nullable=False)

    set_rel: Mapped["SetModel"] = relationship("SetModel", back_populates="cards")
    rarity_rel: Mapped["RarityModel"] = relationship("RarityModel", back_populates="cards")
    price_history: Mapped[List["PriceHistoryModel"]] = relationship("PriceHistoryModel", back_populates="card_rel", cascade="all, delete-orphan")


class PriceHistoryModel(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[str] = mapped_column(String, ForeignKey("cards.id"), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, default="EUR")
    source: Mapped[str] = mapped_column(String, default="Cardmarket")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    card_rel: Mapped["CardModel"] = relationship("CardModel", back_populates="price_history")


def init_db():
    Base.metadata.create_all(bind=engine)
    print("¡Base de datos verificada con la tabla relacional multiusuario!")

if __name__ == "__main__":
    init_db()