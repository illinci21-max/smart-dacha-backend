from app.services.nutrient_ledger_service import parse_nutrient_amounts


def test_parse_nutrient_amounts_from_recommendation_text():
    entry = parse_nutrient_amounts("N 2.6г + P 1,0г + K 3.4г + Mg 0.3г + Ca 0.5г")

    assert entry.nitrogen_g_m2 == 2.6
    assert entry.phosphorus_g_m2 == 1.0
    assert entry.potassium_g_m2 == 3.4
    assert entry.magnesium_g_m2 == 0.3
    assert entry.calcium_g_m2 == 0.5
