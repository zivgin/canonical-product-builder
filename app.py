import streamlit as st
import pymongo
import pandas as pd
from bson.objectid import ObjectId
from datetime import datetime
import re

# MongoDB connection
def get_mongo_client():
    MONGO_USERNAME = st.secrets["mongo"]["MONGO_USERNAME"]
    MONGO_PASSWORD = st.secrets["mongo"]["MONGO_PASSWORD"]
    MONGO_CLUSTER = st.secrets["mongo"]["MONGO_CLUSTER"]

    MONGO_URI = f"mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_CLUSTER}/?retryWrites=true&w=majority"

    client = pymongo.MongoClient(MONGO_URI)
    return client

client = get_mongo_client()
db = client["supermarkets"]

products_collection = db["products"]
canonical_products_collection = db["canonical_products"]
chains_collection = db["chains"]

def generate_canonical_barcode():
    last_product = canonical_products_collection.find_one(sort=[("canonical_barcode", -1)])
    if last_product:
        return last_product["canonical_barcode"] + 1
    else:
        return 100001  # Starting point

def extract_chain_id(file_name):
    # Extracts the chain_id from the file_name
    match = re.search(r'PriceFull(\d+)-', file_name)
    if match:
        return match.group(1)
    else:
        return None

def search_products(search_term, selected_chains):
    query = {"item_name": {"$regex": search_term, "$options": "i"}}
    projection = {
        "_id": 0,
        "item_code": 1,
        "item_name": 1,
        "manufacturer_name": 1,
        "file_name": 1
    }
    products_cursor = products_collection.find(query, projection).limit(100)
    products = []
    for product in products_cursor:
        file_name = product.get('file_name', '')
        chain_id = extract_chain_id(file_name)
        if chain_id:
            product['chain_id'] = chain_id
            products.append(product)
    if selected_chains:
        products = [p for p in products if p['chain_id'] in selected_chains]
    return products

def get_chain_names():
    chains = list(chains_collection.find({}, {"_id": 0, "id": 1, "chain_name": 1}))
    chain_dict = {str(chain["id"]): chain["chain_name"] for chain in chains}
    return chain_dict

def get_categories():
    categories = canonical_products_collection.distinct("category")
    return categories

def save_canonical_product(data):
    try:
        canonical_products_collection.insert_one(data)
        st.success("Canonical product saved successfully!")
    except pymongo.errors.DuplicateKeyError:
        st.error("Canonical barcode already exists.")

def main():
    st.title("Canonical Product Builder")

    # Section 1: Create Canonical Product
    st.header("1. Create Canonical Product")

    # Generate or input canonical barcode
    if "canonical_barcode" not in st.session_state:
        st.session_state["canonical_barcode"] = generate_canonical_barcode()
    barcode_input = st.text_input("Canonical Barcode", value=str(st.session_state["canonical_barcode"]))
    if barcode_input.isdigit():
        st.session_state["canonical_barcode"] = int(barcode_input)
    else:
        st.error("Canonical Barcode must be a number.")

    # Input name and category
    name = st.text_input("Product Name")
    categories = get_categories()
    category = st.selectbox("Category", options=["Add new category"] + categories)
    if category == "Add new category":
        category = st.text_input("New Category")

    # Section 2: Search for Products
    st.header("2. Search for Products")

    search_term = st.text_input("Search for products", value=name)
    chain_names = get_chain_names()
    selected_chains = st.multiselect("Filter by Chains", options=chain_names.keys(), format_func=lambda x: chain_names[x])

    if search_term:
        products = search_products(search_term, selected_chains)
        if products:
            df_products = pd.DataFrame(products)
            df_products["chain_name"] = df_products["chain_id"].astype(str).map(chain_names)
            df_products = df_products[["item_code", "item_name", "chain_name", "manufacturer_name"]]
            st.write("Search Results:")
            selected_products = st.multiselect(
                "Select products to assign",
                options=df_products.index,
                format_func=lambda x: f"{df_products.loc[x, 'item_name']} - {df_products.loc[x, 'chain_name']}"
            )
        else:
            st.write("No products found.")
    else:
        products = []
        selected_products = []

    # Section 3: Auto-Suggestion for Matching Products
    st.header("3. Auto-Suggestion for Matching Products")
    if name and not search_term:
        auto_products = search_products(name, selected_chains)
        if auto_products:
            st.write("Auto-Suggested Products:")
            df_auto = pd.DataFrame(auto_products)
            df_auto["chain_name"] = df_auto["chain_id"].astype(str).map(chain_names)
            df_auto = df_auto[["item_code", "item_name", "chain_name", "manufacturer_name"]]
            st.dataframe(df_auto)
        else:
            st.write("No auto-suggestions available.")

    # Section 4: Assign Chain-Specific Barcodes
    st.header("4. Assign Chain-Specific Barcodes")

    if products and selected_products:
        selected_items = [products[i] for i in selected_products]
        chain_barcodes = {}
        for item in selected_items:
            chain_id = item["chain_id"]
            if chain_id in chain_names:
                chain_name = chain_names[chain_id]
                chain_barcodes[chain_name] = item["item_code"]
        st.write("Assigned Barcodes:")
        st.write(chain_barcodes)
    else:
        chain_barcodes = {}

    # Section 5: Category Selection
    st.header("5. Category Selection")
    # Already handled in Section 1

    # Section 6: Preview and Save
    st.header("6. Preview and Save")

    if st.button("Preview Canonical Product"):
        if not name or not category or not chain_barcodes:
            st.error("Please ensure that Name, Category, and Chain-Specific Barcodes are provided.")
        else:
            canonical_product = {
                "canonical_barcode": st.session_state["canonical_barcode"],
                "name": name,
                "category": category,
                "chains": chain_barcodes,
                "created_at": datetime.utcnow()
            }
            st.write("Canonical Product Preview:")
            st.json(canonical_product)

            if st.button("Save Canonical Product"):
                # Validation
                existing = canonical_products_collection.find_one({"canonical_barcode": st.session_state["canonical_barcode"]})
                if existing:
                    st.error("Canonical barcode already exists.")
                else:
                    save_canonical_product(canonical_product)
                    # Reset session state
                    st.session_state["canonical_barcode"] += 1
                    st.experimental_rerun()

if __name__ == "__main__":
    main()
