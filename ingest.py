# ingest.py
import requests
from sqlalchemy.orm import Session
from database import engine, SetModel, RarityModel, CardModel, PriceHistoryModel, SetRarityConfigModel, init_db

# Mapa de Pull Rates comunitarios iniciales por defecto
DEFAULT_PULL_RATES = {
    "common": 4.0,
    "uncommon": 3.0,
    "rare": 1.0,
    "double rare": 0.143,
    "ultra rare": 0.067,
    "illustration rare": 0.077,
    "special illustration rare": 0.031,
    "hyper rare": 0.018
}

SETS_TO_INGEST = [
    {"id": "sv01", "name": "Scarlet & Violet", "price": 4.50},
    {"id": "sv02", "name": "Paldea Evolved", "price": 4.50},
    {"id": "sv03.5", "name": "151", "price": 5.50}
]

def fetch_and_ingest():
    print("🔄 Asegurando estructura de tablas en SQLite...")
    init_db()

    session = Session(engine)

    try:
        for set_info in SETS_TO_INGEST:
            set_id = set_info["id"]
            print(f"\n📦 Procesando colección: {set_info['name']} ({set_id})...")

            # 1. Crear o actualizar la entidad del Set
            db_set = session.query(SetModel).filter(SetModel.id == set_id).first()
            if not db_set:
                db_set = SetModel(
                    id=set_id,
                    name=set_info["name"],
                    pack_price_eur=set_info["price"]
                )
                session.add(db_set)
                session.commit()
                session.refresh(db_set)

            # 2. Consultar cartas del set a la API externa (TCGdex)
            url = f"https://api.tcgdex.net/v2/en/sets/{set_id}"
            resp = requests.get(url)
            if resp.status_code != 200:
                print(f"⚠️ No se pudo obtener datos para el set {set_id}")
                continue

            set_data = resp.json()
            cards_list = set_data.get("cards", [])
            db_set.total_cards = len(cards_list)
            session.commit()

            print(f"  └─ {len(cards_list)} cartas encontradas. Ingestando información...")

            # 3. Procesar cartas y sus rarezas
            for card_summary in cards_list:
                card_id = card_summary.get("id")
                card_url = f"https://api.tcgdex.net/v2/en/cards/{card_id}"
                c_resp = requests.get(card_url)
                if c_resp.status_code != 200:
                    continue

                card_detail = c_resp.json()
                rarity_name = card_detail.get("rarity", "Common")

                # Obtener o crear Rareza global en la tabla de catálogo
                db_rarity = session.query(RarityModel).filter(RarityModel.name == rarity_name).first()
                if not db_rarity:
                    db_rarity = RarityModel(name=rarity_name)
                    session.add(db_rarity)
                    session.commit()
                    session.refresh(db_rarity)

                # Obtener o crear Carta
                db_card = session.query(CardModel).filter(CardModel.id == card_id).first()
                if not db_card:
                    db_card = CardModel(
                        id=card_id,
                        name=card_detail.get("name", "Unknown"),
                        number=card_detail.get("localId"),
                        image_url=card_detail.get("image"),
                        set_id=set_id,
                        rarity_id=db_rarity.id
                    )
                    session.add(db_card)
                    session.commit()

                # Guardar registro de precio (simulado/estimado para entorno dev si la API no devuelve precio directo)
                price_val = 0.50
                if "illustration" in rarity_name.lower():
                    price_val = 12.00
                elif "special" in rarity_name.lower():
                    price_val = 35.00
                elif "ultra" in rarity_name.lower() or "hyper" in rarity_name.lower():
                    price_val = 20.00
                elif "double" in rarity_name.lower():
                    price_val = 4.00

                price_record = PriceHistoryModel(
                    card_id=card_id,
                    price=price_val,
                    currency="EUR",
                    source="Cardmarket"
                )
                session.add(price_record)

            session.commit()

            # 4. Generar la configuración de Pull Rates y Precios por Set (SetRarityConfigModel)
            print(f"  └─ Generando configuraciones independientes de rareza para '{set_info['name']}'...")
            rarities_in_db = session.query(RarityModel).all()

            for rarity in rarities_in_db:
                # Verificar si ya existe configuración para este par (set_id, rarity_id)
                config = session.query(SetRarityConfigModel).filter(
                    SetRarityConfigModel.set_id == set_id,
                    SetRarityConfigModel.rarity_id == rarity.id
                ).first()

                if not config:
                    r_key = rarity.name.lower().strip()
                    initial_pull_rate = DEFAULT_PULL_RATES.get(r_key, 0.05)

                    # Calcular precio medio inicial de las cartas registradas de esta rareza en este set
                    cards_in_set_rarity = session.query(CardModel).filter(
                        CardModel.set_id == set_id,
                        CardModel.rarity_id == rarity.id
                    ).all()

                    avg_price_init = 0.50
                    if cards_in_set_rarity:
                        total_p = 0.0
                        count_p = 0
                        for c in cards_in_set_rarity:
                            last_price = session.query(PriceHistoryModel).filter(PriceHistoryModel.card_id == c.id).first()
                            if last_price:
                                total_p += last_price.price
                                count_p += 1
                        if count_p > 0:
                            avg_price_init = total_p / count_p

                    config = SetRarityConfigModel(
                        set_id=set_id,
                        rarity_id=rarity.id,
                        pull_rate=initial_pull_rate,
                        custom_avg_price=round(avg_price_init, 2)
                    )
                    session.add(config)

            session.commit()
            print(f"✅ Set '{set_info['name']}' ingestado y configurado con éxito.")

    except Exception as e:
        session.rollback()
        print(f"\n❌ Error durante la ingesta: {e}")
        raise e
    finally:
        session.close()

if __name__ == "__main__":
    fetch_and_ingest()