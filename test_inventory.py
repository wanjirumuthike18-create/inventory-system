"""
Tests for the API, the external API calls and the CLI.
Run with:  pytest -v
"""
from unittest.mock import patch, MagicMock

import pytest
import requests

import app as inventory_app
import cli


@pytest.fixture
def client():
    # reset the mock database before every test so tests don't affect each other
    inventory_app.inventory[:] = inventory_app.starting_data()
    inventory_app.app.config["TESTING"] = True
    with inventory_app.app.test_client() as test_client:
        yield test_client


def fake_response(json_data, status_code=200):
    """Makes a fake response object like the one requests gives us."""
    fake = MagicMock()
    fake.status_code = status_code
    fake.json.return_value = json_data
    return fake


# ---------- API: GET ----------

def test_get_all_items(client):
    response = client.get("/inventory")
    assert response.status_code == 200
    assert len(response.get_json()) == 3


def test_get_one_item(client):
    response = client.get("/inventory/1")
    assert response.status_code == 200
    assert response.get_json()["product_name"] == "Organic Almond Milk"


def test_get_item_not_found(client):
    response = client.get("/inventory/999")
    assert response.status_code == 404


# ---------- API: POST ----------

def test_add_item(client):
    new_item = {"product_name": "Peanut Butter", "brands": "Skippy", "price": 5.5, "stock": 8}
    response = client.post("/inventory", json=new_item)
    assert response.status_code == 201
    assert response.get_json()["id"] == 4
    assert len(inventory_app.inventory) == 4


def test_add_item_missing_name(client):
    response = client.post("/inventory", json={"price": 5})
    assert response.status_code == 400


def test_add_item_bad_price(client):
    response = client.post("/inventory", json={"product_name": "Test", "price": "free"})
    assert response.status_code == 400


# ---------- API: PATCH ----------

def test_update_item(client):
    response = client.patch("/inventory/1", json={"price": 6.0, "stock": 50})
    assert response.status_code == 200
    assert response.get_json()["price"] == 6.0
    assert inventory_app.find_item(1)["stock"] == 50


def test_update_item_not_found(client):
    response = client.patch("/inventory/999", json={"price": 1})
    assert response.status_code == 404


def test_update_cannot_change_id(client):
    client.patch("/inventory/1", json={"id": 500})
    assert inventory_app.find_item(1) is not None


# ---------- API: DELETE ----------

def test_delete_item(client):
    response = client.delete("/inventory/2")
    assert response.status_code == 200
    assert inventory_app.find_item(2) is None


def test_delete_item_not_found(client):
    response = client.delete("/inventory/999")
    assert response.status_code == 404


# ---------- External API (mocked) ----------

barcode_result = {
    "status": 1,
    "product": {
        "code": "123456",
        "product_name": "Test Cereal",
        "brands": "Kellogg's",
        "ingredients_text": "Corn, sugar, salt",
    },
}


@patch("app.requests.get")
def test_lookup_by_barcode(mock_get, client):
    mock_get.return_value = fake_response(barcode_result)
    response = client.get("/external/product?barcode=123456")
    assert response.status_code == 200
    assert response.get_json()["product_name"] == "Test Cereal"


@patch("app.requests.get")
def test_lookup_by_name(mock_get, client):
    mock_get.return_value = fake_response({"products": [barcode_result["product"]]})
    response = client.get("/external/product?name=cereal")
    assert response.status_code == 200
    assert response.get_json()["brands"] == "Kellogg's"


@patch("app.requests.get")
def test_lookup_not_found(mock_get, client):
    mock_get.return_value = fake_response({"status": 0})
    response = client.get("/external/product?barcode=000")
    assert response.status_code == 404


@patch("app.requests.get")
def test_lookup_api_down(mock_get, client):
    mock_get.side_effect = requests.exceptions.ConnectionError()
    response = client.get("/external/product?barcode=123456")
    assert response.status_code == 502


def test_lookup_no_params(client):
    response = client.get("/external/product")
    assert response.status_code == 400


@patch("app.requests.get")
def test_import_adds_to_inventory(mock_get, client):
    mock_get.return_value = fake_response(barcode_result)
    response = client.post("/inventory/import", json={"barcode": "123456", "price": 3, "stock": 10})
    assert response.status_code == 201
    assert response.get_json()["product_name"] == "Test Cereal"
    assert len(inventory_app.inventory) == 4


# ---------- CLI (mocked) ----------

@patch("cli.requests.request")
def test_cli_view_all(mock_request, capsys):
    mock_request.return_value = fake_response(inventory_app.starting_data())
    cli.view_all()
    output = capsys.readouterr().out
    assert "Organic Almond Milk" in output


@patch("cli.requests.request")
def test_cli_server_down(mock_request, capsys):
    mock_request.side_effect = requests.exceptions.ConnectionError()
    cli.view_all()
    output = capsys.readouterr().out
    assert "could not connect" in output


@patch("cli.requests.request")
@patch("builtins.input")
def test_cli_add_item(mock_input, mock_request, capsys):
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
    mock_input.side_effect = ["abc", "-5", "10"]
    result = cli.ask_number("Number: ", whole_number=True)
    assert result == 10