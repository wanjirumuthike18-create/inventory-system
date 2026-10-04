"""
Inventory Management System - Flask REST API

Routes:
    GET    /inventory            -> all items
    GET    /inventory/<id>       -> one item
    POST   /inventory            -> add an item
    PATCH  /inventory/<id>       -> update an item
    DELETE /inventory/<id>       -> delete an item
    GET    /external/product     -> look up a product on OpenFoodFacts
    POST   /inventory/import     -> look up a product and add it to inventory
"""
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

OFF_BARCODE_URL = "https://world.openfoodfacts.org/api/v0/product/{}.json"
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"


def starting_data():
    # Mock database, shaped like the data OpenFoodFacts gives back
    return [
        {
            "id": 1,
            "product_name": "Organic Almond Milk",
            "brands": "Silk",
            "barcode": "025293600164",
            "ingredients_text": "Filtered water, almonds, cane sugar",
            "price": 4.99,
            "stock": 20,
        },
        {
            "id": 2,
            "product_name": "Whole Wheat Bread",
            "brands": "Brookside",
            "barcode": "1112223334445",
            "ingredients_text": "Whole wheat flour, water, yeast, salt",
            "price": 2.50,
            "stock": 35,
        },
        {
            "id": 3,
            "product_name": "Orange Juice",
            "brands": "Tropicana",
            "barcode": "0048500001868",
            "ingredients_text": "Orange juice",
            "price": 3.75,
            "stock": 12,
        },
    ]


# This list acts as our database
inventory = starting_data()


# ---------- helper functions ----------

def find_item(item_id):
    """Loop through the inventory and return the item with this id (or None)."""
    for item in inventory:
        if item["id"] == item_id:
            return item
    return None


def get_next_id():
    """Give a new item an id one higher than the biggest id we have."""
    if len(inventory) == 0:
        return 1
    biggest = 0
    for item in inventory:
        if item["id"] > biggest:
            biggest = item["id"]
    return biggest + 1


def check_numbers(data):
    """Make sure price and stock (if given) are valid. Returns an error message or None."""
    if "price" in data:
        if not isinstance(data["price"], (int, float)) or data["price"] < 0:
            return "price must be a number that is 0 or more"
    if "stock" in data:
        if not isinstance(data["stock"], int) or data["stock"] < 0:
            return "stock must be a whole number that is 0 or more"
    return None


def fetch_from_openfoodfacts(barcode=None, name=None):
    """
    Ask the OpenFoodFacts API for a product, using a barcode or a name.
    Returns the product dictionary, or None if nothing was found.
    Raises requests exceptions if the API can't be reached.
    """
    headers = {"User-Agent": "InventoryApp/1.0 (student project)"}

    if barcode:
        response = requests.get(
            OFF_BARCODE_URL.format(barcode), headers=headers, timeout=10
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != 1:
            return None
        return data.get("product")

    if name:
        params = {
            "search_terms": name,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 1,
        }
        response = requests.get(
            OFF_SEARCH_URL, params=params, headers=headers, timeout=10
        )
        response.raise_for_status()
        products = response.json().get("products", [])
        if len(products) == 0:
            return None
        return products[0]

    return None


def clean_product(product, barcode=None):
    """Pick out only the fields we care about from the API product."""
    return {
        "product_name": product.get("product_name", ""),
        "brands": product.get("brands", ""),
        "barcode": product.get("code", barcode or ""),
        "ingredients_text": product.get("ingredients_text", ""),
    }


# ---------- CRUD routes ----------

@app.route("/inventory", methods=["GET"])
def get_all_items():
    return jsonify(inventory), 200


@app.route("/inventory/<int:item_id>", methods=["GET"])
def get_one_item(item_id):
    item = find_item(item_id)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item), 200


@app.route("/inventory", methods=["POST"])
def add_item():
    data = request.get_json(silent=True)
    if not data or not data.get("product_name"):
        return jsonify({"error": "product_name is required"}), 400

    error = check_numbers(data)
    if error:
        return jsonify({"error": error}), 400

    new_item = {
        "id": get_next_id(),
        "product_name": data["product_name"],
        "brands": data.get("brands", ""),
        "barcode": data.get("barcode", ""),
        "ingredients_text": data.get("ingredients_text", ""),
        "price": data.get("price", 0),
        "stock": data.get("stock", 0),
    }
    inventory.append(new_item)
    return jsonify(new_item), 201


@app.route("/inventory/<int:item_id>", methods=["PATCH"])
def update_item(item_id):
    item = find_item(item_id)
    if item is None:
        return jsonify({"error": "Item not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data sent"}), 400

    error = check_numbers(data)
    if error:
        return jsonify({"error": error}), 400

    # only these fields are allowed to change (not the id)
    allowed = ["product_name", "brands", "barcode", "ingredients_text", "price", "stock"]
    for field in allowed:
        if field in data:
            item[field] = data[field]

    return jsonify(item), 200


@app.route("/inventory/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    item = find_item(item_id)
    if item is None:
        return jsonify({"error": "Item not found"}), 404

    inventory.remove(item)
    return jsonify({"message": "Item deleted"}), 200


# ---------- external API routes ----------

@app.route("/external/product", methods=["GET"])
def lookup_external():
    barcode = request.args.get("barcode")
    name = request.args.get("name")

    if not barcode and not name:
        return jsonify({"error": "Give a barcode or a name"}), 400

    try:
        product = fetch_from_openfoodfacts(barcode=barcode, name=name)
    except requests.exceptions.RequestException:
        return jsonify({"error": "Could not reach OpenFoodFacts"}), 502

    if product is None:
        return jsonify({"error": "Product not found"}), 404

    return jsonify(clean_product(product, barcode)), 200


@app.route("/inventory/import", methods=["POST"])
def import_from_external():
    data = request.get_json(silent=True)
    if not data or (not data.get("barcode") and not data.get("name")):
        return jsonify({"error": "Give a barcode or a name"}), 400

    error = check_numbers(data)
    if error:
        return jsonify({"error": error}), 400

    try:
        product = fetch_from_openfoodfacts(
            barcode=data.get("barcode"), name=data.get("name")
        )
    except requests.exceptions.RequestException:
        return jsonify({"error": "Could not reach OpenFoodFacts"}), 502

    if product is None:
        return jsonify({"error": "Product not found"}), 404

    details = clean_product(product, data.get("barcode"))
    new_item = {
        "id": get_next_id(),
        "product_name": details["product_name"],
        "brands": details["brands"],
        "barcode": details["barcode"],
        "ingredients_text": details["ingredients_text"],
        "price": data.get("price", 0),
        "stock": data.get("stock", 0),
    }
    inventory.append(new_item)
    return jsonify(new_item), 201


if __name__ == "__main__":
    app.run(debug=True)