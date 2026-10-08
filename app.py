"""
Inventory Management System - Flask REST API
This file is the "back office" of a shop. It keeps a list of products and
answers requests like "show me everything", "add this product" or
"delete product 2". Other programs (my CLI, Postman, the tests) talk to it
over HTTP, the same way a browser talks to a website.

Routes:
    GET    /inventory            -> all items
    GET    /inventory/<id>       -> one item
    POST   /inventory            -> add an item
    PATCH  /inventory/<id>       -> update an item
    DELETE /inventory/<id>       -> delete an item
    GET    /external/product     -> look up a product on OpenFoodFacts
    POST   /inventory/import     -> look up a product and add it to inventory
"""
# Flask builds the web server. jsonify turns Python data into JSON replies.
# request lets me read what the client sent me.
from flask import Flask, jsonify, request
# requests lets MY code call OTHER websites (here: OpenFoodFacts)
import requests

# This creates the app. Think of it as opening the shop.
app = Flask(__name__)

# Web addresses for the OpenFoodFacts API. {} is filled in with a barcode later.
OFF_BARCODE_URL = "https://world.openfoodfacts.org/api/v0/product/{}.json"
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"


def starting_data():
    # The assignment says to use an array (list) as a fake database.
    # Each product is a dictionary, shaped like what OpenFoodFacts returns.
    # It's a function so the tests can get a fresh copy every time.
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


# This list is our "database". It lives in memory, like a notebook on a desk:
# when the server stops, the notebook is wiped and we start fresh.
inventory = starting_data()


# ---------- helper functions ----------
# Small tools the routes below use, so I don't repeat the same code.

def find_item(item_id):
    """Loop through the inventory and return the item with this id (or None)."""
    for item in inventory:
        if item["id"] == item_id:
            return item
    # We only get here if the loop finished without finding a match
    return None


def get_next_id():
    """Give a new item an id one higher than the biggest id we have."""
    # If the list is empty, the first item gets id 1
    if len(inventory) == 0:
        return 1
    biggest = 0
    for item in inventory:
        if item["id"] > biggest:
            biggest = item["id"]
    # Using "biggest + 1" means ids never repeat, even after deleting items
    return biggest + 1


def check_numbers(data):
    """Make sure price and stock (if given) are valid. Returns an error message or None."""
    # Input validation: never trust what the user sends.
    # Price can be a whole number or decimal, but not negative.
    if "price" in data:
        if not isinstance(data["price"], (int, float)) or data["price"] < 0:
            return "price must be a number that is 0 or more"
    # Stock is "how many we have", so it must be a whole number, not negative.
    if "stock" in data:
        if not isinstance(data["stock"], int) or data["stock"] < 0:
            return "stock must be a whole number that is 0 or more"
    # None means "no problems found"
    return None


def fetch_from_openfoodfacts(barcode=None, name=None):
    """
    Ask the OpenFoodFacts API for a product, using a barcode or a name.
    Returns the product dictionary, or None if nothing was found.
    Raises requests exceptions if the API can't be reached.
    """
    # OpenFoodFacts asks apps to say who they are with a User-Agent
    headers = {"User-Agent": "InventoryApp/1.0 (student project)"}

    # Option 1: search by barcode (exact match, so it gives one product)
    if barcode:
        # timeout=10 means "give up after 10 seconds" so we never hang forever
        response = requests.get(
            OFF_BARCODE_URL.format(barcode), headers=headers, timeout=10
        )
        # raise_for_status turns bad replies (like 500 errors) into exceptions
        response.raise_for_status()
        data = response.json()
        # OpenFoodFacts sets status to 1 when it found the product
        if data.get("status") != 1:
            return None
        return data.get("product")

    # Option 2: search by name (could match many, so we take the first one)
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

    # Neither barcode nor name was given
    return None


def clean_product(product, barcode=None):
    """Pick out only the fields we care about from the API product."""
    # The API returns HUGE dictionaries. We keep only four fields.
    # .get(key, default) avoids a crash when a field is missing.
    return {
        "product_name": product.get("product_name", ""),
        "brands": product.get("brands", ""),
        "barcode": product.get("code", barcode or ""),
        "ingredients_text": product.get("ingredients_text", ""),
    }


# ---------- CRUD routes ----------
# CRUD = Create, Read, Update, Delete: the four things you do with data.
# Status codes are like short answers from a shop assistant:
#   200 = OK, 201 = created, 400 = you asked wrongly, 404 = can't find it

# READ (all): the "show me everything on the shelf" route
@app.route("/inventory", methods=["GET"])
def get_all_items():
    return jsonify(inventory), 200


# READ (one): "show me item number 2". <int:item_id> grabs the number from the URL.
@app.route("/inventory/<int:item_id>", methods=["GET"])
def get_one_item(item_id):
    item = find_item(item_id)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item), 200


# CREATE: add a new product to the list
@app.route("/inventory", methods=["POST"])
def add_item():
    # silent=True means "give me None instead of crashing if the JSON is bad"
    data = request.get_json(silent=True)
    # Every product must at least have a name
    if not data or not data.get("product_name"):
        return jsonify({"error": "product_name is required"}), 400

    error = check_numbers(data)
    if error:
        return jsonify({"error": error}), 400

    # Build the new item. The server picks the id, NOT the user.
    # data.get("x", default) fills in blanks for anything not sent.
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


# UPDATE: PATCH changes only the fields sent (PUT would replace the whole item)
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
    # This is a safety list: even if someone sends "id": 500, it's ignored.
    allowed = ["product_name", "brands", "barcode", "ingredients_text", "price", "stock"]
    for field in allowed:
        if field in data:
            item[field] = data[field]

    return jsonify(item), 200


# DELETE: remove a product from the list
@app.route("/inventory/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    item = find_item(item_id)
    if item is None:
        return jsonify({"error": "Item not found"}), 404

    inventory.remove(item)
    return jsonify({"message": "Item deleted"}), 200


# ---------- external API routes ----------
# These routes make my server act like a customer of ANOTHER server.

# Look up a product on OpenFoodFacts WITHOUT saving it
@app.route("/external/product", methods=["GET"])
def lookup_external():
    # request.args reads the part after the ? in the URL, e.g. ?barcode=123
    barcode = request.args.get("barcode")
    name = request.args.get("name")

    if not barcode and not name:
        return jsonify({"error": "Give a barcode or a name"}), 400

    # try/except = "try this, and if the internet or API fails, don't crash"
    try:
        product = fetch_from_openfoodfacts(barcode=barcode, name=name)
    except requests.exceptions.RequestException:
        # 502 means "the other server I depend on didn't answer properly"
        return jsonify({"error": "Could not reach OpenFoodFacts"}), 502

    if product is None:
        return jsonify({"error": "Product not found"}), 404

    return jsonify(clean_product(product, barcode)), 200


# Look up a product on OpenFoodFacts AND save it into my inventory.
# This is the "enhance stored inventory with data from the API" requirement.
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

    # Name, brand, barcode and ingredients come from the API.
    # Price and stock come from the user, because the API doesn't know my shop's prices.
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


# This only runs when I start the file directly (python app.py),
# not when the tests import it. debug=True shows helpful errors while developing.
if __name__ == "__main__":
    app.run(debug=True)