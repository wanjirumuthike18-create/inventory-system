"""
Command line interface for the Inventory Management System.
Make sure the Flask server is running first (python app.py).
app.py is the kitchen; this file is the waiter. It shows a menu, asks the
user questions, carries the order to the Flask server, and prints what
comes back. It never touches the inventory list directly: it ALWAYS goes
through the API.
"""
import requests

# Where my Flask server is running
BASE_URL = "http://127.0.0.1:5000"


def send_request(method, path, **kwargs):
    """
    Send a request to our Flask API.
    Returns the response, or None if the server can't be reached.
    """
    # Every menu option goes through this ONE function, so error handling
    # for "server is off" is written once instead of seven times.
    # **kwargs lets callers pass extras like json=... or params=...
    try:
        return requests.request(method, BASE_URL + path, timeout=15, **kwargs)
    except requests.exceptions.ConnectionError:
        print("Error: could not connect to the server. Is app.py running?")
    except requests.exceptions.Timeout:
        print("Error: the server took too long to respond.")
    except requests.exceptions.RequestException:
        print("Error: something went wrong with the request.")
    # None tells the caller "that failed, stop here"
    return None


def print_item(item):
    # Just formatting: prints one product nicely over three lines
    print(f"[{item['id']}] {item['product_name']} ({item['brands']})")
    print(f"     Price: {item['price']} | Stock: {item['stock']} | Barcode: {item['barcode']}")
    print(f"     Ingredients: {item['ingredients_text']}")


def ask_number(prompt, whole_number=False):
    """Keep asking until the user types a valid number that is not negative."""
    # This is input validation: the loop is like a bouncer who won't let you
    # through until you give a proper answer.
    while True:
        value = input(prompt).strip()
        try:
            # whole_number=True for stock/ids, False for price (decimals allowed)
            number = int(value) if whole_number else float(value)
            if number < 0:
                print("Please enter 0 or more.")
                continue
            return number
        except ValueError:
            # int("abc") raises ValueError, so we catch it and ask again
            print("That's not a valid number, try again.")


def show_error(response):
    """Print the error message that the API sent back."""
    # Our API sends errors like {"error": "Item not found"}, so we read that.
    try:
        message = response.json().get("error", "Unknown error")
    except ValueError:
        message = "Unknown error"
    print(f"Error ({response.status_code}): {message}")


# Each function below matches ONE menu option and ONE API route.

def view_all():
    # Menu 1 -> GET /inventory
    response = send_request("GET", "/inventory")
    # If the server was unreachable, send_request gave None, so stop
    if response is None:
        return
    if response.status_code != 200:
        show_error(response)
        return
    items = response.json()
    if len(items) == 0:
        print("Inventory is empty.")
    for item in items:
        print_item(item)


def view_one():
    # Menu 2 -> GET /inventory/<id>
    item_id = ask_number("Item ID: ", whole_number=True)
    response = send_request("GET", f"/inventory/{item_id}")
    if response is None:
        return
    if response.status_code == 200:
        print_item(response.json())
    else:
        show_error(response)


def add_item():
    # Menu 3 -> POST /inventory
    name = input("Product name: ").strip()
    if name == "":
        print("Product name can't be empty.")
        return
    brand = input("Brand: ").strip()
    barcode = input("Barcode: ").strip()
    price = ask_number("Price: ")
    stock = ask_number("Stock: ", whole_number=True)

    new_item = {
        "product_name": name,
        "brands": brand,
        "barcode": barcode,
        "price": price,
        "stock": stock,
    }
    # json=new_item sends the dictionary as the request body
    response = send_request("POST", "/inventory", json=new_item)
    if response is None:
        return
    # 201 means "created"
    if response.status_code == 201:
        print("Item added!")
        print_item(response.json())
    else:
        show_error(response)


def update_item():
    # Menu 4 -> PATCH /inventory/<id>
    item_id = ask_number("ID of item to update: ", whole_number=True)
    print("Leave a field blank to keep it the same.")
    price = input("New price: ").strip()
    stock = input("New stock: ").strip()

    # Only add to "changes" what the user actually typed. That's why PATCH fits:
    # we send just the changed fields.
    changes = {}
    try:
        if price != "":
            changes["price"] = float(price)
        if stock != "":
            changes["stock"] = int(stock)
    except ValueError:
        print("Price must be a number and stock must be a whole number.")
        return

    if len(changes) == 0:
        print("Nothing to update.")
        return

    response = send_request("PATCH", f"/inventory/{item_id}", json=changes)
    if response is None:
        return
    if response.status_code == 200:
        print("Item updated!")
        print_item(response.json())
    else:
        show_error(response)


def delete_item():
    # Menu 5 -> DELETE /inventory/<id>
    item_id = ask_number("ID of item to delete: ", whole_number=True)
    response = send_request("DELETE", f"/inventory/{item_id}")
    if response is None:
        return
    if response.status_code == 200:
        print("Item deleted.")
    else:
        show_error(response)


def find_on_api():
    # Menu 6 -> GET /external/product, then optionally POST /inventory/import
    choice = input("Search by (b)arcode or (n)ame? ").strip().lower()
    if choice == "b":
        params = {"barcode": input("Barcode: ").strip()}
    elif choice == "n":
        params = {"name": input("Product name: ").strip()}
    else:
        print("Please type b or n.")
        return

    # params=... puts the search in the URL after the ?
    response = send_request("GET", "/external/product", params=params)
    if response is None:
        return
    if response.status_code != 200:
        show_error(response)
        return

    product = response.json()
    print(f"Found: {product['product_name']} ({product['brands']})")
    print(f"Ingredients: {product['ingredients_text']}")

    # After showing the result, let the user save it to the inventory
    add_it = input("Add this to inventory? (y/n): ").strip().lower()
    if add_it == "y":
        body = {
            "price": ask_number("Price: "),
            "stock": ask_number("Stock: ", whole_number=True),
        }
        # use the barcode if we have one, otherwise fall back to the name
        if product["barcode"]:
            body["barcode"] = product["barcode"]
        else:
            body["name"] = product["product_name"]

        added = send_request("POST", "/inventory/import", json=body)
        if added is None:
            return
        if added.status_code == 201:
            print("Added to inventory!")
            print_item(added.json())
        else:
            show_error(added)


def show_menu():
    print("\n===== Inventory Manager =====")
    print("1. View all items")
    print("2. View one item")
    print("3. Add new item")
    print("4. Update price / stock")
    print("5. Delete item")
    print("6. Find item on OpenFoodFacts")
    print("7. Quit")


def main():
    # The main loop: show menu, read choice, run the matching function,
    # repeat until the user picks 7 (break ends the loop).
    while True:
        show_menu()
        choice = input("Choose an option: ").strip()

        if choice == "1":
            view_all()
        elif choice == "2":
            view_one()
        elif choice == "3":
            add_item()
        elif choice == "4":
            update_item()
        elif choice == "5":
            delete_item()
        elif choice == "6":
            find_on_api()
        elif choice == "7":
            print("Goodbye!")
            break
        else:
            print("Invalid option, please pick 1-7.")


# Run main() only when this file is started directly (python cli.py)
if __name__ == "__main__":
    main()