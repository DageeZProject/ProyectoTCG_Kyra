# main.py
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from database import engine, SetModel, RarityModel, CardModel, PriceHistoryModel, SetRarityConfigModel, UserModel, init_db

app = FastAPI(
    title="Pokémon TCG Analytics - Cloud Ready",
    version="5.0.0"
)

# Inicializar BD al arrancar
@app.on_event("startup")
def on_startup():
    init_db()

def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()

# ----------------------------------------------------
# ESQUEMAS PYDANTIC
# ----------------------------------------------------

class CustomRarityInput(BaseModel):
    rarity_name: str
    pull_rate: float
    custom_avg_price: float

class CustomAnalyticsRequest(BaseModel):
    user_id: str = "david"
    set_id: str
    product_name: str
    packs_count: int
    product_price_eur: float
    rarities: List[CustomRarityInput]

DEFAULT_PULL_RATES = {
    "common": 4.0, "uncommon": 3.0, "rare": 1.0,
    "double rare": 0.143, "ultra rare": 0.067,
    "illustration rare": 0.077, "special illustration rare": 0.031, "hyper rare": 0.018
}

# ----------------------------------------------------
# ENDPOINTS
# ----------------------------------------------------

@app.get("/")
def read_index():
    return FileResponse("index.html")

@app.get("/api/sets")
def get_all_sets(db: Session = Depends(get_db)):
    sets = db.query(SetModel).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "release_date": s.release_date,
            "total_cards": s.total_cards,
            "pack_price_eur": float(s.pack_price_eur)
        }
        for s in sets
    ]

@app.get("/api/analytics/{set_id}")
def get_set_analytics(set_id: str, user_id: str = "david", db: Session = Depends(get_db)):
    target_set = db.query(SetModel).filter(SetModel.id == set_id).first()
    if not target_set:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' no encontrado.")

    # Asegurar que el usuario existe
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        user = UserModel(id=user_id, name=user_id.capitalize())
        db.add(user)
        db.commit()

    total_ev: float = 0.0
    rarities_breakdown = []
    rarities = db.query(RarityModel).all()

    for rarity in rarities:
        latest_prices = (
            db.query(
                CardModel.id,
                func.avg(PriceHistoryModel.price).label("avg_price")
            )
            .join(PriceHistoryModel, CardModel.id == PriceHistoryModel.card_id)
            .filter(CardModel.set_id == set_id, CardModel.rarity_id == rarity.id)
            .group_by(CardModel.id)
            .all()
        )

        card_count = len(latest_prices)
        if card_count == 0:
            continue

        prices_list = [float(p.avg_price) for p in latest_prices if p.avg_price is not None]
        api_avg_price = sum(prices_list) / card_count if prices_list else 0.0

        # Buscar configuración filtrando por USER_ID + SET_ID + RARITY_ID
        config = db.query(SetRarityConfigModel).filter(
            SetRarityConfigModel.user_id == user_id,
            SetRarityConfigModel.set_id == set_id,
            SetRarityConfigModel.rarity_id == rarity.id
        ).first()

        if not config:
            def_rate = DEFAULT_PULL_RATES.get(rarity.name.lower().strip(), 0.05)
            config = SetRarityConfigModel(
                user_id=user_id,
                set_id=set_id,
                rarity_id=rarity.id,
                pull_rate=def_rate,
                custom_avg_price=api_avg_price
            )
            db.add(config)
            db.commit()
            db.refresh(config)

        final_price = float(config.custom_avg_price) if (config.custom_avg_price and config.custom_avg_price > 0) else api_avg_price
        pull_r = float(config.pull_rate)

        ev_contribution = pull_r * final_price
        total_ev += ev_contribution

        rarities_breakdown.append({
            "rarity": rarity.name,
            "cards_count": card_count,
            "pull_rate": pull_r,
            "avg_price_eur": round(final_price, 2),
            "ev_contribution_eur": round(ev_contribution, 2)
        })

    pack_cost = float(target_set.pack_price_eur)
    roi_percentage = ((total_ev - pack_cost) / pack_cost) * 100.0 if pack_cost > 0 else 0.0

    return {
        "set_id": target_set.id,
        "set_name": target_set.name,
        "user_id": user_id,
        "pack_price_eur": pack_cost,
        "expected_value_eur": round(total_ev, 2),
        "roi_percentage": round(roi_percentage, 2),
        "is_profitable": roi_percentage > 0,
        "rarities_breakdown": rarities_breakdown
    }

@app.post("/api/analytics/custom-simulation")
def calculate_custom_analytics(payload: CustomAnalyticsRequest, db: Session = Depends(get_db)):
    target_set = db.query(SetModel).filter(SetModel.id == payload.set_id).first()
    if not target_set:
        raise HTTPException(status_code=404, detail=f"El set '{payload.set_id}' no existe.")

    # Asegurar que el usuario existe
    user = db.query(UserModel).filter(UserModel.id == payload.user_id).first()
    if not user:
        user = UserModel(id=payload.user_id, name=payload.user_id.capitalize())
        db.add(user)
        db.commit()

    single_pack_ev: float = 0.0
    breakdown = []

    for item in payload.rarities:
        rarity_db = db.query(RarityModel).filter(func.lower(RarityModel.name) == item.rarity_name.lower().strip()).first()
        if rarity_db:
            config = db.query(SetRarityConfigModel).filter(
                SetRarityConfigModel.user_id == payload.user_id,
                SetRarityConfigModel.set_id == payload.set_id,
                SetRarityConfigModel.rarity_id == rarity_db.id
            ).first()

            if not config:
                config = SetRarityConfigModel(
                    user_id=payload.user_id,
                    set_id=payload.set_id,
                    rarity_id=rarity_db.id,
                    pull_rate=float(item.pull_rate),
                    custom_avg_price=float(item.custom_avg_price)
                )
                db.add(config)
            else:
                config.pull_rate = float(item.pull_rate)
                config.custom_avg_price = float(item.custom_avg_price)

        ev_contribution = float(item.pull_rate) * float(item.custom_avg_price)
        single_pack_ev += ev_contribution

        breakdown.append({
            "rarity": item.rarity_name,
            "pull_rate": float(item.pull_rate),
            "custom_avg_price_eur": round(float(item.custom_avg_price), 2),
            "ev_contribution_eur": round(ev_contribution, 2)
        })

    db.commit()

    packs_cnt = float(payload.packs_count)
    total_product_ev = single_pack_ev * packs_cnt
    cost = float(payload.product_price_eur)
    
    roi_percentage = ((total_product_ev - cost) / cost) * 100.0 if cost > 0 else 0.0
    net_profit_loss = total_product_ev - cost

    return {
        "set_id": target_set.id,
        "set_name": target_set.name,
        "user_id": payload.user_id,
        "product_name": payload.product_name,
        "packs_count": payload.packs_count,
        "product_price_eur": round(cost, 2),
        "single_pack_ev_eur": round(single_pack_ev, 2),
        "total_product_ev_eur": round(total_product_ev, 2),
        "net_profit_loss_eur": round(net_profit_loss, 2),
        "roi_percentage": round(roi_percentage, 2),
        "is_profitable": roi_percentage > 0,
        "breakdown": breakdown
    }
    # main.py (Añadir al final del archivo)
from ingest import fetch_and_ingest

@app.post("/api/admin/ingest")
@app.get("/api/admin/ingest")
def trigger_ingest():
    """Endpoint de administración para ejecutar la ingesta de datos en la nube."""
    try:
        fetch_and_ingest()
        return {"status": "success", "message": "¡Ingesta de datos completada con éxito en la base de datos!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante la ingesta: {str(e)}")