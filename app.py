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

def search_products(search_term, excluded_sub_chains, exclude_words=[]):
    # Build regex pattern for exclude words
    exclude_pattern = '|'.join([re.escape(word) for word in exclude_words])
    # Query to search products
    regex_query = {"$regex": search_term, "$options": "i"}
    if exclude_words:
        regex_query = {"$regex": f"^(?!.*({exclude_pattern})).*{search_term}.*$", "$options": "i"}
    query = {"item_name": regex_query}
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

def get_sub_categories():
    sub_categories = canonical_products_collection.distinct("sub_category")
    return sub_categories

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
    if 'exclude_words' not in st.session_state:
        st.session_state['exclude_words'] = []
    if 'exclude_words_list' not in st.session_state:
        st.session_state['exclude_words_list'] = []

    # Tabs
    tab1, tab2 = st.tabs(["Build Canonical Product", "View Canonical Products"])

    with tab1:
        # Upload Excel file
        uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])
        if uploaded_file:
            df_excel = pd.read_excel(uploaded_file)
            if not df_excel.empty:
                first_row = df_excel.iloc[0]
                # Populate barcode
                if 'Barcode' in df_excel.columns:
                    barcode = first_row['Barcode']
                    if pd.notnull(barcode):
                        st.session_state["canonical_barcode"] = int(barcode)
                # Populate name
                if 'Name' in df_excel.columns:
                    name = first_row['Name']
                else:
                    name = ''
                # Populate category and sub-category
                if 'Category' in df_excel.columns:
                    category_data = first_row['Category']
                    if pd.notnull(category_data):
                        if '-' in category_data:
                            category, sub_category = map(str.strip, category_data.split('-', 1))
                        else:
                            category = category_data.strip()
                            sub_category = ''
                    else:
                        category = ''
                        sub_category = ''
                else:
                    category = ''
                    sub_category = ''
            else:
                st.error("Uploaded Excel file is empty.")
        else:
            name = ''
            category = ''
            sub_category = ''

        # Section 1: Create Canonical Product
        st.header("1. Create Canonical Product")

        # Generate or input canonical barcode
        barcode_input = st.text_input("Canonical Barcode", value=str(st.session_state["canonical_barcode"]))
        if barcode_input.isdigit():
            st.session_state["canonical_barcode"] = int(barcode_input)
        else:
            st.error("Canonical Barcode must be a number.")

        # Input name, category, and sub-category
        name = st.text_input("Product Name", value=name)
        categories = get_categories()
        category = st.selectbox("Category", options=["Add new category"] + categories, index=0 if category == '' else categories.index(category)+1)
        if category == "Add new category":
            category = st.text_input("New Category", value='')
        sub_categories = get_sub_categories()
        sub_category = st.selectbox("Sub-Category", options=["Add new sub-category"] + sub_categories, index=0 if sub_category == '' else sub_categories.index(sub_category)+1)
        if sub_category == "Add new sub-category":
            sub_category = st.text_input("New Sub-Category", value='')

        # Section 2: Auto-Suggestion for Matching Products
        st.header("2. Auto-Suggestion for Matching Products")
        if name:
            auto_products = search_products(f"^{re.escape(name)}$", st.session_state['excluded_sub_chains'])
            if auto_products:
                exact_matches = {}
                for product in auto_products:
                    sub_chain_id = product['sub_chain_id']
                    st.session_state['selected_sub_chains'].add(sub_chain_id)
                    st.session_state['excluded_sub_chains'].add(sub_chain_id)
                    st.session_state['selected_items'][sub_chain_id] = product
                    exact_matches[sub_chain_id] = product
                if exact_matches:
                    st.write("Automatically assigned exact matches from other sub-chains.")
            else:
                st.write("No exact matches found for auto-assignment.")

        # Section 3: Search for Products
        st.header("3. Search for Products")

        search_term = st.text_input("Search for products", value=name)
        exclude_words_input = st.text_input("Exclude words from search (type word and press Enter)")
        if exclude_words_input:
            st.session_state['exclude_words_list'].append(exclude_words_input.strip())
        st.session_state['exclude_words_list'] = list(set(st.session_state['exclude_words_list']))
        exclude_words = st.session_state['exclude_words_list']
        if exclude_words:
            st.write("Excluding words:", exclude_words)
        if st.button("Clear Exclude Words"):
            st.session_state['exclude_words_list'] = []
            exclude_words = []

        if search_term:
            products = search_products(search_term, st.session_state['excluded_sub_chains'], exclude_words)
            if products:
                df_products = pd.DataFrame(products)
                df_products["sub_chain_name"] = df_products["sub_chain_id"].apply(
                    lambda x: sub_chain_dict.get(x, chain_dict.get(x.split('-')[0], 'Unknown Chain'))
                )
                df_products = df_products[["item_code", "item_name", "sub_chain_name", "manufacturer_name"]]
                df_products["item_display"] = df_products.apply(lambda x: f"{x['item_name']} ({x['item_code']})", axis=1)
                st.write("Search Results:")
                selected_index = st.selectbox(
                    "Select a product to assign",
                    options=df_products.index,
                    format_func=lambda x: f"{df_products.loc[x, 'item_display']} - {df_products.loc[x, 'sub_chain_name']}"
                )
                # Update selection
                item = products[selected_index]
                sub_chain_id = item['sub_chain_id']
                if sub_chain_id in st.session_state['selected_sub_chains']:
                    st.warning(f"You have already selected a product from {sub_chain_dict.get(sub_chain_id, 'Unknown Chain')}.")
                else:
                    st.session_state['selected_sub_chains'].add(sub_chain_id)
                    st.session_state['excluded_sub_chains'].add(sub_chain_id)
                    st.session_state['selected_items'][sub_chain_id] = item
                    st.success(f"Product from {sub_chain_dict.get(sub_chain_id, 'Unknown Chain')} added.")
            else:
                st.write("No products found.")
        else:
            products = []

        # Section 4: Sub-Chains Status and Remove Option
        st.header("4. Selected Products from Sub-Chains")
        chain_barcodes = {}
        sub_chains_to_remove = []
        for sub_chain_id, item in st.session_state['selected_items'].items():
            sub_chain_name = sub_chain_dict.get(sub_chain_id, chain_dict.get(sub_chain_id.split('-')[0], 'Unknown Chain'))
            chain_barcodes[sub_chain_name] = item["item_code"]
            st.write(f"**{sub_chain_name}:**")
            col1, col2, col3 = st.columns([4, 4, 1])
            with col1:
                name_input = st.text_input(f"Item Name ({sub_chain_name})", value=item['item_name'], key=f"name_{sub_chain_id}")
            with col2:
                barcode_input = st.text_input(f"Item Barcode ({sub_chain_name})", value=str(item['item_code']), key=f"barcode_{sub_chain_id}")
            with col3:
                if st.button("X", key=f"remove_{sub_chain_id}"):
                    sub_chains_to_remove.append(sub_chain_id)
        for sub_chain_id in sub_chains_to_remove:
            st.session_state['selected_sub_chains'].remove(sub_chain_id)
            st.session_state['excluded_sub_chains'].remove(sub_chain_id)
            del st.session_state['selected_items'][sub_chain_id]
            st.success(f"Removed selection from {sub_chain_dict.get(sub_chain_id, 'Unknown Chain')}")

        # Section 5: Preview and Save
        st.header("5. Preview and Save")

        if st.button("Preview Canonical Product"):
            if not name or not category or not chain_barcodes:
                st.error("Please ensure that Name, Category, and Sub-Chain-Specific Barcodes are provided.")
            else:
                created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                canonical_product = {
                    "canonical_barcode": st.session_state["canonical_barcode"],
                    "name": name,
                    "category": category,
                    "sub_category": sub_category,
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
                        st.session_state['exclude_words_list'] = []
                        st.experimental_rerun()

    with tab2:
        st.header("View Existing Canonical Products")
        canonical_products = list(canonical_products_collection.find({}, {"_id": 0, "canonical_barcode": 1, "name": 1}))
        if canonical_products:
            df_canonical = pd.DataFrame(canonical_products)
            df_canonical['display'] = df_canonical.apply(lambda x: f"{x['name']} ({x['canonical_barcode']})", axis=1)
            selected_product = st.selectbox("Select a canonical product", options=df_canonical.index, format_func=lambda x: df_canonical.loc[x, 'display'])
            product = canonical_products[selected_product]
            st.write(f"**Name:** {product['name']}")
            st.write(f"**Canonical Barcode:** {product['canonical_barcode']}")
            st.write(f"**Category:** {product.get('category', '')}")
            st.write(f"**Sub-Category:** {product.get('sub_category', '')}")
            st.write(f"**Created At:** {product.get('created_at', '')}")
            st.write("**Chains:**")
            chains = product.get('chains', {})
            for chain_name, item_code in chains.items():
                st.write(f"- {chain_name}: {item_code}")
        else:
            st.write("No canonical products found.")

if __name__ == "__main__":
    main()
