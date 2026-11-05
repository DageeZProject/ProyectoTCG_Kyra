# ingest.py
import requests
from sqlalchemy.orm import Session
from database import engine, SetModel, RarityModel, CardModel, PriceHistoryModel, SetRarityConfigModel, init_db

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
    print("🔄 Verificando e inicializando tablas en la base de datos...")
    init_db()

    session = Session(engine)

    try:
        # 1. Catálogo completo de rarezas
        base_rarities = [
            "Common", "Uncommon", "Rare", "Double Rare", 
            "Ultra Rare", "Illustration Rare", "Special Illustration Rare", "Hyper Rare"
        ]
        
        rarity_map = {}
        for r_name in base_rarities:
            db_rarity = session.query(RarityModel).filter(RarityModel.name == r_name).first()
            if not db_rarity:
                db_rarity = RarityModel(name=r_name)
                session.add(db_rarity)
                session.commit()
                session.refresh(db_rarity)
            rarity_map[r_name.lower()] = db_rarity.id

        for set_info in SETS_TO_INGEST:
            set_id = set_info["id"]
            print(f"📦 Ingestando set: {set_info['name']} ({set_id})...")

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

            # Petición a TCGdex API
            url = f"https://api.tcgdex.net/v2/en/sets/{set_id}"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"⚠️ No se pudo consultar el set {set_id}")
                continue

            set_data = resp.json()
            cards_list = set_data.get("cards", [])
            total_cards_count = len(cards_list)
            db_set.total_cards = total_cards_count
            session.commit()

            if total_cards_count == 0:
                continue

            # 2. Clasificación proporcional según el tamaño real del set
            for idx, card_summary in enumerate(cards_list):
                card_id = card_summary.get("id")
                if not card_id:
                    continue

                db_card = session.query(CardModel).filter(CardModel.id == card_id).first()
                if not db_card:
                    card_name = card_summary.get("name", "Card")
                    
                    # Proporción relativa (0.0 a 1.0)
                    pct = idx / total_cards_count

                    if pct < 0.40:
                        r_name = "Common"
                    elif pct < 0.68:
                        r_name = "Uncommon"
                    elif pct < 0.80:
                        r_name = "Rare"
                    elif pct < 0.88:
                        r_name = "Double Rare"
                    elif pct < 0.93:
                        r_name = "Ultra Rare"
                    elif pct < 0.96:
                        r_name = "Illustration Rare"
                    elif pct < 0.985:
                        r_name = "Special Illustration Rare"
                    else:
                        r_name = "Hyper Rare"

                    r_id = rarity_map.get(r_name.lower(), rarity_map["common"])

                    db_card = CardModel(
                        id=card_id,
                        name=card_name,
                        number=card_summary.get("localId", str(idx + 1)),
                        image_url=card_summary.get("image"),
                        set_id=set_id,
                        rarity_id=r_id
                    )
                    session.add(db_card)
                    
                    price_record = PriceHistoryModel(
                        card_id=card_id,
                        price=1.50,
                        currency="EUR",
                        source="Cardmarket"
                    )
                    session.add(price_record)

            session.commit()

            # 3. Asignar configuraciones completas para los perfiles multiusuario
            rarities_in_db = session.query(RarityModel).all()
            profiles = ["david", "amigo"]

            for profile in profiles:
                for rarity in rarities_in_db:
                    config = session.query(SetRarityConfigModel).filter(
                        SetRarityConfigModel.user_id == profile,
                        SetRarityConfigModel.set_id == set_id,
                        SetRarityConfigModel.rarity_id == rarity.id
                    ).first()

                    if not config:
                        r_key = rarity.name.lower().strip()
                        initial_pull_rate = DEFAULT_PULL_RATES.get(r_key, 0.05)
                        
                        est_price = 0.50
                        if "illustration" in r_key:
                            est_price = 10.00
                        elif "special" in r_key:
                            est_price = 30.00
                        elif "ultra" in r_key or "hyper" in r_key:
                            est_price = 15.00
                        elif "double" in r_key:
                            est_price = 3.50
                        elif "rare" in r_key:
                            est_price = 1.50

                        config = SetRarityConfigModel(
                            user_id=profile,
                            set_id=set_id,
                            rarity_id=rarity.id,
                            pull_rate=initial_pull_rate,
                            custom_avg_price=est_price
                        )
                        session.add(config)

            session.commit()
            print(f"✅ Ingesta de '{set_info['name']}' corregida con éxito.")

    except Exception as e:
        session.rollback()
        print(f"❌ Error en ingesta: {e}")
        raise e
    finally:
        session.close()

if __name__ == "__main__":
    fetch_and_ingest()