import datetime

import pytest
from lxml import html as lh

from myfitnesspal_mcp import diary, mfp_client

TODAY = datetime.date(2026, 7, 8)


def meal_id(doc, meal):
    return diary.resolve_meal(doc, meal)[0]


def test_food_search_parses_results_and_csrf(client):
    results, csrf = diary.food_search(client, "banana")
    assert csrf == "CSRF123"
    assert [r["food_id"] for r in results] == ["111", "222"]
    first = results[0]
    assert first["weight_id"] == "10"
    assert first["name"] == "Banana"
    assert first["external_id"] == "999"
    assert first["brand"] == "Fresh Fruit"
    assert first["calories"] == 105.0


def test_food_search_degrades_without_external_id(client):
    results, _ = diary.food_search(client, "banana")
    second = results[1]
    assert second["external_id"] is None
    assert second["calories"] == 196.0


def test_search_food_enriches_macros(client):
    client.food_details[999] = {
        "calories": 105.0,
        "verified": True,
        "nutrition": {"protein": 1.3, "carbohydrates": 27.0, "fat": 0.4},
        "serving_sizes": [{"value": 1, "unit": "medium"}],
    }
    candidates = diary.search_food(client, "banana", limit=2)
    assert len(candidates) == 2
    enriched = candidates[0]
    assert enriched["protein"] == 1.3
    assert enriched["carbs"] == 27.0
    assert enriched["serving"] == "1 medium"
    assert enriched["verified"] is True
    degraded = candidates[1]
    assert degraded["protein"] is None
    assert degraded["calories"] == 196.0


def test_search_food_survives_detail_failures(client):
    candidates = diary.search_food(client, "banana", limit=1)
    assert candidates[0]["calories"] == 105.0
    assert candidates[0]["protein"] is None


def test_diary_page_requests_username_less_url(client):
    diary.diary_page(client, TODAY)
    _, url, _ = client.session.calls[-1]
    assert url == "https://www.myfitnesspal.com/food/diary?date=2026-07-08"


def test_meal_headers_lists_labels_in_document_order(custom_meals_diary_html):
    doc = lh.fromstring(custom_meals_diary_html)
    assert diary.meal_headers(doc) == [
        "Fruits/Veggies/Nuts/Seeds",
        "Dairy/Eggs",
        "Meat",
        "Grains/Cereal/Breads/Potatoes",
        "Snacks/Misc",
        "Supplements/Sauces/Spreads",
    ]


def test_meal_headers_ignore_nutrient_column_headings(diary_html):
    doc = lh.fromstring(diary_html)
    assert diary.meal_headers(doc) == ["Breakfast", "Lunch", "Dinner", "Snacks"]


BLANK_SECOND_MEAL = (
    "<table>"
    "<tr class='meal_header'><td>Breakfast</td></tr>"
    "<tr><td><a data-food-entry-id='b1'>Eggs</a></td></tr>"
    "<tr class='meal_header'><td> </td></tr>"
    "<tr><td><a data-food-entry-id='u1'>Mystery Bar</a></td></tr>"
    "<tr class='meal_header'><td>Dinner</td></tr>"
    "<tr class='meal_header'><td>Snacks</td></tr>"
    "</table>"
)


def test_diary_entries_map_meals(client):
    doc, token = diary.diary_page(client, TODAY)
    assert token == "DIARYTOKEN"
    entries = diary.diary_entries(doc)
    assert [(e["meal"], e["entry_id"]) for e in entries] == [
        ("breakfast", "e1"),
        ("breakfast", "e2"),
        ("lunch", "e3"),
    ]


def test_get_note_double_unescapes_body(client, make_response):
    client.session.route(
        "GET", "food/note", make_response(json_data={"item": {"body": "a &amp;amp; b"}})
    )
    assert diary.get_note(client, TODAY) == "a & b"
    method, url, kwargs = client.session.calls[-1]
    assert method == "GET"
    assert "food/note?date=2026-07-08" in url


def test_get_note_empty_is_none(client, make_response):
    client.session.route(
        "GET", "food/note", make_response(json_data={"item": {"body": ""}})
    )
    assert diary.get_note(client, TODAY) is None


@pytest.fixture
def water_client(client, make_response):
    client.session.route(
        "GET", "food/water", make_response(json_data={"item": {"milliliters": 480}})
    )
    client.session.route("POST", "food/water", make_response(status_code=200))
    return client


