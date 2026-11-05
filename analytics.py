# analytics.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import engine, SetModel, RarityModel, CardModel, PriceHistoryModel

# Probabilidades estimadas por sobre para Scarlet & Violet (pull rates comunitarios)
DEFAULT_PULL_RATES = {
    "Common": 4.0,                      # ~4 comunes por sobre
    "Uncommon": 3.0,                    # ~3 infrecuentes por sobre
    "Double Rare": 0.143,               # ~1 de cada 7 sobres (ex)
    "Ultra Rare": 0.067,                # ~1 de cada 15 sobres (Full Art)
    "Illustration Rare": 0.077,         # ~1 de cada 13 sobres (AR)
    "Special Illustration Rare": 0.031, # ~1 de cada 32 sobres (SAR)
    "Hyper Rare": 0.018                 # ~1 de cada 54 sobres (Gold)
}

def update_rarity_pull_rates():
    """Actualiza la base de datos SQLite con las probabilidades por rareza."""
    with Session(engine) as session:
        for rarity_name, rate in DEFAULT_PULL_RATES.items():
            rarity = session.query(RarityModel).filter_by(name=rarity_name).first()
            if rarity:
                rarity.pull_rate = rate
        session.commit()
    print("¡Pull rates actualizados correctamente en la base de datos!")


def calculate_set_analytics(set_id: str):
    """Calcula el Valor Esperado (EV) y el ROI % para un set específico."""
    with Session(engine) as session:
        target_set = session.get(SetModel, set_id)
        if not target_set:
            print(f"No se encontró el set con ID '{set_id}'.")
            return

        print(f"\n==========================================")
        print(f" ANÁLISIS DE RENTABILIDAD: {target_set.name.upper()}")
        print(f"==========================================")

        total_ev = 0.0
        rarities = session.query(RarityModel).all()

        print(f"\n{'Rareza':<28} | {'Cartas':<7} | {'Precio Med (€)':<14} | {'EV Aportado (€)':<15}")
        print("-" * 72)

        for rarity in rarities:
            # Subconsulta para obtener el último precio registrado de cada carta
            latest_prices = (
                session.query(
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

            # Precio promedio de las cartas de esta rareza
            avg_price_rarity = sum(p.avg_price for p in latest_prices) / card_count

            # Valor esperado que aporta esta rareza al sobre: (Probabilidad * Precio Promedio)
            ev_contribution = rarity.pull_rate * avg_price_rarity
            total_ev += ev_contribution

            print(f"{rarity.name:<28} | {card_count:<7} | €{avg_price_rarity:<13.2f} | €{ev_contribution:<14.2f}")

        # Cálculo de rentabilidad vs precio del sobre
        pack_cost = target_set.pack_price_eur
        roi_percentage = ((total_ev - pack_cost) / pack_cost) * 100

        print("-" * 72)
        print(f"Precio estimado por sobre:  €{pack_cost:.2f}")
        print(f"Valor Esperado (EV) total:  €{total_ev:.2f}")
        print(f"Índice de Rentabilidad ROI: {roi_percentage:+.2f}%")
        
        if roi_percentage > 0:
            print("Dictamen: ¡SOBRE RENTABLE DE ABRIR! 🎉")
        else:
            print("Dictamen: NO RENTABLE (Conviene conservar el sobre sellado) 🔒")

if __name__ == "__main__":
    update_rarity_pull_rates()
    calculate_set_analytics("sv01")