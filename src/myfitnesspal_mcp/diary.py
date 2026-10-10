"""Diary reads and writes against MyFitnessPal's web endpoints.

MFP has no official write API. These calls replicate what the web app's own
JavaScript sends: the legacy /food/search page exposes per-result food_id +
weight_id (the ids /food/add accepts — v2 API ids are rejected), and writes
authenticate with the session's Bearer token plus mfp-* client headers and the
page csrf token.
"""

from datetime import date
from html import unescape
from urllib import parse

from lxml import html as lh

MEAL_ALIASES = {"snack": "snacks"}

DEFAULT_MEAL_POSITIONS = {"breakfast": 0, "lunch": 1, "dinner": 2, "snacks": 3}


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _normalize_meal(meal: str | None) -> str | None:
    if meal is None:
        return None
    lowered = _collapse_whitespace(meal).lower()
    return MEAL_ALIASES.get(lowered, lowered)


class DiaryLookupError(RuntimeError):
    pass


class DiarySignedOut(RuntimeError):
    pass


def _is_meal_header(row) -> bool:
    return "meal_header" in (row.get("class") or "")


def _header_label(header_row, position: int) -> str:
    cells = header_row.xpath("./td")
    name = _collapse_whitespace(cells[0].text_content()) if cells else ""
    return name or f"Meal {position + 1}"


def meal_headers(doc) -> list[str]:
    header_rows = [row for row in doc.xpath("//tr") if _is_meal_header(row)]
    return [_header_label(row, position) for position, row in enumerate(header_rows)]


def api_headers(client, extra: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {client.access_token}",
        "mfp-client-id": "mfp-main-js",
        "mfp-user-id": str(client.user_id),
        "X-Requested-With": "XMLHttpRequest",
    }
    if extra:
        headers.update(extra)
    return headers


def _result_extras(anchor) -> dict:
    extras = {
        "external_id": anchor.get("data-external-id"),
        "brand": None,
        "serving": None,
        "calories": None,
    }
    containers = anchor.xpath("ancestor::li[1]")
    if not containers:
        return extras
    info = containers[0].xpath(".//p[@class='search-nutritional-info']")
    if not info or not info[0].text:
        return extras
    parts = info[0].text.strip().split(",")
    if len(parts) >= 3:
        extras["brand"] = " ".join(parts[0:-2]).strip()
    if len(parts) >= 2:
        extras["serving"] = parts[-2].strip() or None
    calories_text = parts[-1].replace("calories", "").strip()
    try:
        extras["calories"] = float(calories_text)
    except ValueError:
        pass
    return extras


def food_search(client, query: str):
    """Returns (results, csrf_token) scraped from the legacy web search page.

    Each result: {food_id, weight_id, name, external_id, brand, calories} —
    food_id/weight_id feed /food/add; external_id feeds the v2 details API.
    """
    url = parse.urljoin(
        client.BASE_URL_SECURE, f"food/search?search={parse.quote(query)}&page=1"
    )
    resp = client.session.get(url, headers=api_headers(client))
    resp.raise_for_status()
    doc = lh.fromstring(resp.text)
    csrf = doc.xpath("//meta[@name='csrf-token']/@content")
    results = []
    for anchor in doc.xpath("//a[@data-original-id and @data-weight-ids]"):
        weight_ids = [w for w in anchor.get("data-weight-ids").split(",") if w]
        if not weight_ids:
            continue
        result = {
            "food_id": anchor.get("data-original-id"),
            "weight_id": weight_ids[0],
            "weight_ids": weight_ids,
            "name": anchor.text_content().strip(),
        }
        result.update(_result_extras(anchor))
        results.append(result)
    if csrf:
        return results, csrf[0]
    return results, None


def serving_label(serving: dict) -> str | None:
    parts = []
    value = serving.get("value")
    if isinstance(value, (int, float)):
        parts.append(f"{value:g}")
    elif value is not None:
        parts.append(str(value))
    if serving.get("unit"):
        parts.append(str(serving["unit"]))
    return " ".join(parts) or None


def food_details(client, external_id: str | None) -> dict | None:
    if not external_id:
        return None
    try:
        details = client._get_food_item_details(int(external_id))
        nutrition = details["nutrition"]
        return {
            "verified": details.get("verified"),
            "nutrition": {
                "calories": details["calories"],
                "protein": nutrition.get("protein"),
                "carbs": nutrition.get("carbohydrates"),
                "fat": nutrition.get("fat"),
            },
            "serving_sizes": details.get("serving_sizes") or [],
        }
    except Exception:
        return None


def search_food(
    client, query: str, limit: int = 5, with_macros: bool = True
) -> list[dict]:
    results, _ = food_search(client, query)
    candidates = []
    for result in results[:limit]:
        candidate = {
            "name": result["name"],
            "brand": result["brand"],
            "calories": result["calories"],
            "protein": None,
            "carbs": None,
            "fat": None,
            "serving": None,
            "verified": None,
            "food_id": result["food_id"],
            "weight_id": result["weight_id"],
        }
        details = food_details(client, result["external_id"]) if with_macros else None
        if details:
            candidate.update(details["nutrition"])
            candidate["verified"] = details["verified"]
            if details["serving_sizes"]:
                candidate["serving"] = serving_label(details["serving_sizes"][0])
        candidates.append(candidate)
    return candidates


def food_diary_url(client, day: date | None = None) -> str:
    url = parse.urljoin(client.BASE_URL_SECURE, "food/diary")
    if day is None:
        return url
    return f"{url}?date={day.isoformat()}"


def diary_page(client, day: date):
    resp = client.session.get(food_diary_url(client, day), headers=api_headers(client))
    resp.raise_for_status()
    doc = lh.fromstring(resp.text)
    tokens = doc.xpath("//meta[@name='csrf-token']/@content")
    if not tokens:
        raise RuntimeError("couldn't read the MyFitnessPal csrf token")
    if not meal_headers(doc):
        raise DiarySignedOut(
            "the MyFitnessPal diary page has no meal sections; the login "
            "session has likely expired"
        )
    return doc, tokens[0]


def diary_entries(doc) -> list[dict]:
    entries = []
    current_meal = None
    meal_position = -1
    for row in doc.xpath("//tr"):
        if _is_meal_header(row):
            meal_position += 1
            current_meal = _normalize_meal(_header_label(row, meal_position))
            continue
        anchors = row.xpath(".//a[@data-food-entry-id]")
        if anchors:
            entries.append(
                {
                    "entry_id": anchors[0].get("data-food-entry-id"),
                    "meal": current_meal,
                    "name": anchors[0].text_content().strip(),
                }
            )
    return entries


# MFP stores 1 cup as 240 mL and 1 fl oz as 29.5735 mL (verified 2026-09-28 via
# GET /food/water, matching MFP.Tools.UnitConverter.Water in the web app).
ML_PER_WATER_UNIT = {"ml": 1.0, "l": 1000.0, "cup": 240.0, "fl_oz": 29.5735}

WATER_UNIT_ALIASES = {
    "ml": "ml",
    "mls": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "cup": "cup",
    "cups": "cup",
    "floz": "fl_oz",
    "oz": "fl_oz",
    "ounce": "fl_oz",
    "ounces": "fl_oz",
    "fluidounce": "fl_oz",
    "fluidounces": "fl_oz",
}


def get_note(client, day: date) -> str | None:
    """Reads the day's free-text diary note (the 'Notes' box at the bottom of
    the food diary). MFP stores the body double-HTML-encoded; returns the
    decoded text, or None when the day has no note."""
    url = (
        parse.urljoin(client.BASE_URL_SECURE, "food/note") + f"?date={day.isoformat()}"
    )
    resp = client.session.get(
        url, headers=api_headers(client, {"Accept": "application/json"})
    )
    resp.raise_for_status()
    item = (resp.json() or {}).get("item") or {}
    body = item.get("body")
    if not body:
        return None
    return unescape(unescape(body)) or None


def get_exercise(client, day: date) -> dict:
    sections = {}
    for section in client._get_exercises(day):
        sections[section.name.lower()] = section.get_as_list()
    return {"day": day.isoformat(), "exercise": sections}


def exercise_page(client, day: date):
    url = parse.urljoin(
        client.BASE_URL_SECURE,
        f"exercise/diary/{client.effective_username}?date={day.isoformat()}",
    )
    resp = client.session.get(url, headers=api_headers(client))
    resp.raise_for_status()
    doc = lh.fromstring(resp.text)
    tokens = doc.xpath("//meta[@name='csrf-token']/@content")
    if not tokens:
        raise RuntimeError("couldn't read the MyFitnessPal csrf token")
    return doc, tokens[0]


def _field_key(heading: str) -> str:
    words = "".join(c if c.isalnum() else " " for c in heading.lower()).split()
    return "_".join(words)


def _cell_number(cell) -> float | None:
    try:
        return float(cell.text_content().strip().replace(",", ""))
    except ValueError:
        return None


def _exercise_name(cell) -> str:
    for anchor in cell.xpath(".//a"):
        name = anchor.text_content().strip()
        if name:
            return name
    return cell.text_content().strip()


def exercise_entries(doc) -> list[dict]:
    """Deletable rows from every exercise section table. Each entry carries
    the section ("cardiovascular", "strength training") plus that section's
    own columns, e.g. minutes/calories_burned or sets/reps_set/weight_set."""
    entries = []
    for table in doc.xpath("//table[contains(@class, 'table0')]"):
        headings = table.xpath("./thead/tr[1]/td")
        if not headings:
            continue
        section = headings[0].text_content().strip().lower()
        field_keys = [_field_key(h.text_content()) for h in headings[1:]]
        for tr in table.xpath("./tbody/tr[not(@class)]"):
            delete_links = tr.xpath("./td[contains(@class, 'delete')]//a/@href")
            if not delete_links:
                continue
            cells = tr.xpath("./td")
            entry = {
                "entry_id": delete_links[0].split("?")[0].rstrip("/").split("/")[-1],
                "section": section,
                "name": _exercise_name(cells[0]),
            }
            for key, cell in zip(field_keys, cells[1:], strict=False):
                if key:
                    entry[key] = _cell_number(cell)
            entries.append(entry)
    return entries


