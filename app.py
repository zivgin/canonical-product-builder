import streamlit as st
import pymongo
import pandas as pd
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
sub_chains_collection = db["sub_chains"]

# Global chain and sub-chain mappings
chain_dict = {}
sub_chain_dict = {}

def get_chain_names():
    global chain_dict
    chains = list(chains_collection.find({}, {"_id": 0, "id": 1, "chain_name": 1}))
    chain_dict = {str(chain["id"]): chain["chain_name"] for chain in chains}

def get_sub_chain_names():
    global sub_chain_dict
    sub_chains = list(sub_chains_collection.find({}, {"_id": 0, "chain_id": 1, "id": 1, "sub_chain_name": 1}))
    sub_chain_dict = {}
    for sub_chain in sub_chains:
        chain_id = str(sub_chain['chain_id'])
        sub_chain_id = str(sub_chain['id'])
        key = f"{chain_id}-{sub_chain_id}"
        sub_chain_name = sub_chain.get('sub_chain_name', '')
        sub_chain_name = str(sub_chain_name or '').strip()
        if sub_chain_name == '1' or not sub_chain_name:
            sub_chain_name = chain_dict.get(chain_id, 'Unknown Chain')
        sub_chain_dict[key] = sub_chain_name
    return sub_chain_dict

def generate_canonical_barcode():
    last_product = canonical_products_collection.find_one(sort=[("canonical_barcode", -1)])
    if last_product:
        return last_product["canonical_barcode"] + 1
    else:
        return 100001  # Starting point

def extract_chain_and_sub_chain_id(file_name):
    match = re.search(r'PriceFull(\d+)-(\d+)-', file_name)
    if match:
        chain_id = match.group(1)
        sub_chain_id = match.group(2).lstrip('0') or '0'  # Remove leading zeros
        return chain_id, sub_chain_id
    else:
        return None, None

def search_products(search_term, excluded_sub_chains):
    query = {"item_name": {"$regex": search_term, "$options": "i"}}
    projection = {
        "_id": 0,
        "item_code": 1,
        "item_name": 1,
        "manufacturer_name": 1,
        "file_name": 1
    }
    products_cursor = products_collection.find(query, projection).limit(500)
    products = []
    for product in products_cursor:
        file_name = product.get('file_name', '')
        chain_id, sub_chain_id = extract_chain_and_sub_chain_id(file_name)
        if chain_id and sub_chain_id:
            sub_chain_key = f"{chain_id}-{sub_chain_id}"
            if sub_chain_key not in excluded_sub_chains:
                product['sub_chain_id'] = sub_chain_key
                products.append(product)
    return products

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

    # Initialize chain and sub-chain names
    get_chain_names()
    get_sub_chain_names()

    # Initialize session state variables
    if 'canonical_barcode' not in st.session_state:
        st.session_state['canonical_barcode'] = generate_canonical_barcode()
    if 'selected_sub_chains' not in st.session_state:
        st.session_state['selected_sub_chains'] = set()
    if 'selected_items' not in st.session_state:
        st.session_state['selected_items'] = {}
    if 'excluded_sub_chains' not in st.session_state:
        st.session_state['excluded_sub_chains'] = set()

    # Section 1: Create Canonical Product
    st.header("1. Create Canonical Product")

    # Generate or input canonical barcode
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

    # Section 2: Auto-Suggestion for Matching Products
    st.header("2. Auto-Suggestion for Matching Products")
    if name:
        auto_products = search_products(name, st.session_state['excluded_sub_chains'])
        if auto_products:
            df_auto = pd.DataFrame(auto_products)
            df_auto["sub_chain_name"] = df_auto["sub_chain_id"].apply(
                lambda x: sub_chain_dict.get(x, chain_dict.get(x.split('-')[0], 'Unknown Chain'))
            )
            df_auto = df_auto[["item_code", "item_name", "sub_chain_name", "manufacturer_name"]]
            df_auto["item_display"] = df_auto.apply(lambda x: f"{x['item_name']} ({x['item_code']})", axis=1)
            st.write("Auto-Suggested Products:")
            selected_auto_products = st.multiselect(
                "Select products to assign from suggestions",
                options=df_auto.index,
                format_func=lambda x: f"{df_auto.loc[x, 'item_display']} - {df_auto.loc[x, 'sub_chain_name']}"
            )
            # Update selections
            for idx in selected_auto_products:
                item = auto_products[idx]
                sub_chain_id = item['sub_chain_id']
                if sub_chain_id not in st.session_state['selected_sub_chains']:
                    st.session_state['selected_sub_chains'].add(sub_chain_id)
                    st.session_state['excluded_sub_chains'].add(sub_chain_id)
                    st.session_state['selected_items'][sub_chain_id] = item
        else:
            st.write("No auto-suggestions available.")

    # Section 3: Search for Products
    st.header("3. Search for Products")

    search_term = st.text_input("Search for products", value=name)
    if search_term:
        products = search_products(search_term, st.session_state['excluded_sub_chains'])
        if products:
            df_products = pd.DataFrame(products)
            df_products["sub_chain_name"] = df_products["sub_chain_id"].apply(
                lambda x: sub_chain_dict.get(x, chain_dict.get(x.split('-')[0], 'Unknown Chain'))
            )
            df_products = df_products[["item_code", "item_name", "sub_chain_name", "manufacturer_name"]]
            df_products["item_display"] = df_products.apply(lambda x: f"{x['item_name']} ({x['item_code']})", axis=1)
            st.write("Search Results:")
            selected_products = st.multiselect(
                "Select products to assign",
                options=df_products.index,
                format_func=lambda x: f"{df_products.loc[x, 'item_display']} - {df_products.loc[x, 'sub_chain_name']}"
            )
            # Update selections
            for idx in selected_products:
                item = products[idx]
                sub_chain_id = item['sub_chain_id']
                if sub_chain_id not in st.session_state['selected_sub_chains']:
                    st.session_state['selected_sub_chains'].add(sub_chain_id)
                    st.session_state['excluded_sub_chains'].add(sub_chain_id)
                    st.session_state['selected_items'][sub_chain_id] = item
        else:
            st.write("No products found.")
    else:
        products = []

    # Section 4: Sub-Chains Status (Moved to Sidebar)
    st.sidebar.header("Sub-Chains Status")
    all_sub_chains = set(sub_chain_dict.keys())
    remaining_sub_chains = all_sub_chains - st.session_state['selected_sub_chains']
    st.sidebar.write("Sub-Chains without selected products:")
    for sub_chain_id in sorted(remaining_sub_chains):
        sub_chain_name = sub_chain_dict.get(sub_chain_id, chain_dict.get(sub_chain_id.split('-')[0], 'Unknown Chain'))
        st.sidebar.markdown(f"<span style='color:red'>❌ {sub_chain_name}</span>", unsafe_allow_html=True)
    st.sidebar.write("Sub-Chains with selected products:")
    for sub_chain_id in sorted(st.session_state['selected_sub_chains']):
        sub_chain_name = sub_chain_dict.get(sub_chain_id, chain_dict.get(sub_chain_id.split('-')[0], 'Unknown Chain'))
        st.sidebar.markdown(f"<span style='color:green'>✔️ {sub_chain_name}</span>", unsafe_allow_html=True)

    # Section 5: Assign Sub-Chain-Specific Barcodes
    st.header("4. Assign Sub-Chain-Specific Barcodes")
    chain_barcodes = {}
    for sub_chain_id, item in st.session_state['selected_items'].items():
        sub_chain_name = sub_chain_dict.get(sub_chain_id, chain_dict.get(sub_chain_id.split('-')[0], 'Unknown Chain'))
        chain_barcodes[sub_chain_name] = item["item_code"]
        st.write(f"{sub_chain_name}:")
        col1, col2 = st.columns(2)
        with col1:
            name_input = st.text_input(f"Item Name ({sub_chain_name})", value=item['item_name'], key=f"name_{sub_chain_id}")
        with col2:
            barcode_input = st.text_input(f"Item Barcode ({sub_chain_name})", value=str(item['item_code']), key=f"barcode_{sub_chain_id}")
        # Copy buttons
        col3, col4 = st.columns(2)
        with col3:
            st.button(f"Copy Name ({sub_chain_name})", key=f"copy_name_{sub_chain_id}", on_click=lambda txt=name_input: st.write(f"Copied: {txt}"))
        with col4:
            st.button(f"Copy Barcode ({sub_chain_name})", key=f"copy_barcode_{sub_chain_id}", on_click=lambda txt=barcode_input: st.write(f"Copied: {txt}"))

    # Section 6: Category Selection
    st.header("5. Category Selection")
    # Already handled in Section 1

    # Section 7: Preview and Save
    st.header("6. Preview and Save")

    if st.button("Preview Canonical Product"):
        if not name or not category or not chain_barcodes:
            st.error("Please ensure that Name, Category, and Sub-Chain-Specific Barcodes are provided.")
        else:
            created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            canonical_product = {
                "canonical_barcode": st.session_state["canonical_barcode"],
                "name": name,
                "category": category,
                "chains": chain_barcodes,
                "created_at": created_at
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
                    st.session_state['selected_sub_chains'] = set()
                    st.session_state['selected_items'] = {}
                    st.session_state['excluded_sub_chains'] = set()
                    st.experimental_rerun()

if __name__ == "__main__":
    main()
