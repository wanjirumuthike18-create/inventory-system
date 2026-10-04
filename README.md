# Inventory Management System

A Flask REST API for managing a small retail inventory, with a command line interface (CLI) and an integration with the [OpenFoodFacts API](https://world.openfoodfacts.org/data) to pull in real product details.

Inventory is stored in a Python list (a mock database), so data resets every time the server restarts.

## Installation and Setup

1. Clone the repo and go into the folder:
   ```
   git clone <your-repo-url>
   cd inventory-system
   ```
2. (Optional) create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # Mac / Linux
   ```
3. Install the requirements:
   ```
   pip install -r requirements.txt
   ```
4. Start the API:
   ```
   python app.py
   ```
   The server runs at `http://127.0.0.1:5000`.
5. In a second terminal, start the CLI:
   ```
   python cli.py
   ```

## API Endpoints

| Method | Endpoint | What it does |
|--------|----------|--------------|
| GET | `/inventory` | Get all items |
| GET | `/inventory/<id>` | Get a single item |
| POST | `/inventory` | Add a new item |
| PATCH | `/inventory/<id>` | Update an item (price, stock, etc.) |
| DELETE | `/inventory/<id>` | Delete an item |
| GET | `/external/product?barcode=...` or `?name=...` | Look up a product on OpenFoodFacts |
| POST | `/inventory/import` | Look up a product on OpenFoodFacts and add it to inventory |

### Example item

```json
{
  "id": 1,
  "product_name": "Organic Almond Milk",
  "brands": "Silk",
  "barcode": "025293600164",
  "ingredients_text": "Filtered water, almonds, cane sugar",
  "price": 4.99,
  "stock": 20
}
```

### Example requests

Add an item:
```
POST /inventory
{"product_name": "Peanut Butter", "brands": "Skippy", "price": 5.5, "stock": 8}
```

Update stock:
```
PATCH /inventory/1
{"stock": 50}
```

Import from OpenFoodFacts:
```
POST /inventory/import
{"barcode": "3017620422003", "price": 6.0, "stock": 15}
```

### Errors

| Code | Meaning |
|------|---------|
| 400 | Bad or missing input |
| 404 | Item or product not found |
| 502 | OpenFoodFacts could not be reached |

## Using the CLI

Run `python cli.py` and pick an option from the menu:

```
===== Inventory Manager =====
1. View all items
2. View one item
3. Add new item
4. Update price / stock
5. Delete item
6. Find item on OpenFoodFacts
7. Quit
```

Example: choose `6`, type `b`, enter a barcode, and the CLI will show the product it found and ask if you want to add it to your inventory.

## Running the Tests

```
pytest -v
```

The tests cover the API endpoints, the CLI commands and the OpenFoodFacts calls. The external API is mocked with `unittest.mock`, so the tests don't need internet.

## Project Structure

```
inventory-system/
├── app.py               # Flask API
├── cli.py               # command line interface
├── test_inventory.py    # pytest tests
├── requirements.txt
└── README.md
```