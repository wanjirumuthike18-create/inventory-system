"""
Tests for the API, the external API calls and the CLI.
Run with:  pytest -v
Tests are like a checklist a shop owner runs before opening: "if I ask for
item 1, do I get item 1? If I ask for item 999, do I get a polite 'not found'?"
Every function starting with test_ is one check. pytest finds and runs them all.

MOCKING: I can't depend on the real internet in tests (it could be slow or down).
So I use unittest.mock to put a "rehearsal actor" in place of the real
OpenFoodFacts that always says the lines I give it.
"""
from unittest.mock import patch, MagicMock

import pytest
import requests

import app as inventory_app
import cli


# A fixture is setup code that pytest runs before each test that asks for it.
@pytest.fixture
def client():
    # reset the mock database before every test so tests don't affect each other
    # (otherwise a delete in one test would break the next one)
    inventory_app.inventory[:] = inventory_app.starting_data()
    inventory_app.app.config["TESTING"] = True
    # test_client is a fake browser that talks to my Flask app without a real server
    with inventory_app.app.test_client() as test_client:
        yield test_client


def fake_response(json_data, status_code=200):
    """Makes a fake response object like the one requests gives us."""
    fake = MagicMock()
    fake.status_code = status_code
    # whenever the code calls .json(), hand back the data I chose
    fake.json.return_value = json_data
    return fake


# ---------- API: GET ----------
# Pattern in every test: ARRANGE (set up) -> ACT (call it) -> ASSERT (check result)

def test_get_all_items(client):
    response = client.get("/inventory")
    assert response.status_code == 200
    # we start with 3 items from starting_data()
    assert len(response.get_json()) == 3


def test_get_one_item(client):
    response = client.get("/inventory/1")
    assert response.status_code == 200
    assert response.get_json()["product_name"] == "Organic Almond Milk"


def test_get_item_not_found(client):
    # Testing the unhappy path matters too: a missing item should give 404
    response = client.get("/inventory/999")
    assert response.status_code == 404


# ---------- API: POST ----------

def test_add_item(client):
    new_item = {"product_name": "Peanut Butter", "brands": "Skippy", "price": 5.5, "stock": 8}
    response = client.post("/inventory", json=new_item)
    assert response.status_code == 201
    # the server should give the next id, which is 4 (we had 1, 2, 3)
    assert response.get_json()["id"] == 4
    assert len(inventory_app.inventory) == 4


def test_add_item_missing_name(client):
    # no product_name, so it must be rejected with 400
    response = client.post("/inventory", json={"price": 5})
    assert response.status_code == 400


def test_add_item_bad_price(client):
    # price must be a number, so the text "free" must be rejected
    response = client.post("/inventory", json={"product_name": "Test", "price": "free"})
    assert response.status_code == 400


# ---------- API: PATCH ----------

def test_update_item(client):
    response = client.patch("/inventory/1", json={"price": 6.0, "stock": 50})
    assert response.status_code == 200
    assert response.get_json()["price"] == 6.0
    # also check the stored data really changed, not just the reply
    assert inventory_app.find_item(1)["stock"] == 50


def test_update_item_not_found(client):
    response = client.patch("/inventory/999", json={"price": 1})
    assert response.status_code == 404


def test_update_cannot_change_id(client):
    # tries to change the id; the "allowed" list in app.py should ignore it
    client.patch("/inventory/1", json={"id": 500})
    assert inventory_app.find_item(1) is not None


# ---------- API: DELETE ----------

def test_delete_item(client):
    response = client.delete("/inventory/2")
    assert response.status_code == 200
    # find_item should now return None because item 2 is gone
    assert inventory_app.find_item(2) is None


def test_delete_item_not_found(client):
    response = client.delete("/inventory/999")
    assert response.status_code == 404


# ---------- External API (mocked) ----------

# Pretend this is what OpenFoodFacts sends back for a barcode lookup
barcode_result = {
    "status": 1,
    "product": {
        "code": "123456",
        "product_name": "Test Cereal",
        "brands": "Kellogg's",
        "ingredients_text": "Corn, sugar, salt",
    },
}


# @patch swaps requests.get inside app.py for a fake for this one test.
# The fake arrives as the argument mock_get.
@patch("app.requests.get")
def test_lookup_by_barcode(mock_get, client):
    # tell the fake what to return when app.py calls requests.get(...)
    mock_get.return_value = fake_response(barcode_result)
    response = client.get("/external/product?barcode=123456")
    assert response.status_code == 200
    assert response.get_json()["product_name"] == "Test Cereal"


@patch("app.requests.get")
def test_lookup_by_name(mock_get, client):
    # name search returns a list called "products", so the fake does too
    mock_get.return_value = fake_response({"products": [barcode_result["product"]]})
    response = client.get("/external/product?name=cereal")
    assert response.status_code == 200
    assert response.get_json()["brands"] == "Kellogg's"


@patch("app.requests.get")
def test_lookup_not_found(mock_get, client):
    # status 0 is how OpenFoodFacts says "no such product"
    mock_get.return_value = fake_response({"status": 0})
    response = client.get("/external/product?barcode=000")
    assert response.status_code == 404


@patch("app.requests.get")
def test_lookup_api_down(mock_get, client):
    # side_effect makes the fake raise an error, simulating no internet
    mock_get.side_effect = requests.exceptions.ConnectionError()
    response = client.get("/external/product?barcode=123456")
    # our app should handle it gracefully with 502, not crash
    assert response.status_code == 502


def test_lookup_no_params(client):
    # neither barcode nor name given, so 400
    response = client.get("/external/product")
    assert response.status_code == 400


@patch("app.requests.get")
def test_import_adds_to_inventory(mock_get, client):
    mock_get.return_value = fake_response(barcode_result)
    response = client.post("/inventory/import", json={"barcode": "123456", "price": 3, "stock": 10})
    assert response.status_code == 201
    assert response.get_json()["product_name"] == "Test Cereal"
    # the imported product should now be in the list (3 + 1 = 4)
    assert len(inventory_app.inventory) == 4


# ---------- CLI (mocked) ----------
# For the CLI, we fake TWO things: the network (cli.requests.request)
# and the keyboard (builtins.input), so no real typing or server is needed.
# capsys is a pytest tool that captures what the code prints.

@patch("cli.requests.request")
def test_cli_view_all(mock_request, capsys):
    mock_request.return_value = fake_response(inventory_app.starting_data())
    cli.view_all()
    output = capsys.readouterr().out
    assert "Organic Almond Milk" in output


@patch("cli.requests.request")
def test_cli_server_down(mock_request, capsys):
    # simulate the Flask server being switched off
    mock_request.side_effect = requests.exceptions.ConnectionError()
    cli.view_all()
    output = capsys.readouterr().out
    assert "could not connect" in output


@patch("cli.requests.request")
@patch("builtins.input")
def test_cli_add_item(mock_input, mock_request, capsys):
    # side_effect with a list = each input() call gets the next answer, in order:
    # name, brand, barcode, price, stock
    mock_input.side_effect = ["Rice", "Pishori", "999", "2.5", "40"]
    mock_request.return_value = fake_response(
        {"id": 4, "product_name": "Rice", "brands": "Pishori", "barcode": "999",
         "ingredients_text": "", "price": 2.5, "stock": 40},
        201,
    )
    cli.add_item()
    assert "Item added" in capsys.readouterr().out


@patch("cli.requests.request")
@patch("builtins.input")
def test_cli_delete_not_found(mock_input, mock_request, capsys):
    mock_input.side_effect = ["999"]
    mock_request.return_value = fake_response({"error": "Item not found"}, 404)
    cli.delete_item()
    assert "Item not found" in capsys.readouterr().out


@patch("builtins.input")
def test_cli_ask_number_retries(mock_input, capsys):
    # the user types "abc" (invalid), "-5" (negative), then "10" (valid)
    # ask_number should reject the first two and finally return 10
    mock_input.side_effect = ["abc", "-5", "10"]
    result = cli.ask_number("Number: ", whole_number=True)
    assert result == 10