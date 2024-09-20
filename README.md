# Canonical Product Aggregation Tool

This tool helps aggregate product information from various supermarket chains and assign canonical barcodes to products like fruits, vegetables, and other items that lack a universal barcode. The app allows you to create canonical products and map different chain-specific product barcodes under one unified identifier, making it easier to compare products and prices across chains.

## Features

- **Canonical Barcode Generation**: Automatically generates a 6-digit barcode for new products starting at `100001`.
- **Product Search**: Allows users to search for products from different chains and assign them to a canonical product.
- **Chain-Specific Barcodes**: Supports assigning chain-specific product barcodes for canonical products.
- **Category Management**: Users can select categories from an existing list or create their own categories dynamically.
- **Data Preview & Save**: Preview canonical product information before saving it to the MongoDB database.

## Project Structure

- **`products` Collection**: Stores all supermarket products with fields like `item_code`, `item_name`, `chain_id`, and more.
- **`canonical_products` Collection**: Newly created collection to store canonical product data, including assigned chain-specific barcodes.
- **`chains` Collection**: Stores supermarket chain data, such as `chain_id` and `chain_name`.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.7+**
- **MongoDB**
- **Streamlit**
- **Pandas**

## Installation

1. **Clone the repository:**

    ```bash
    git clone https://github.com/yourusername/canonical-products-aggregation.git
    ```

2. **Install the required Python libraries:**

    ```bash
    pip install -r requirements.txt
    ```

3. **Set up MongoDB:**

    Make sure MongoDB is running, and set up your MongoDB URI in the `secrets.toml` file:

    ```toml
    [mongo]
    MONGO_USERNAME = "your_username"
    MONGO_PASSWORD = "your_password"
    MONGO_CLUSTER = "your_cluster"
    ```

4. **Run the Streamlit app:**

    ```bash
    streamlit run app.py
    ```

## Usage

- **Step 1**: Open the app using Streamlit.
- **Step 2**: Create a new canonical product by searching for relevant items from the supermarket chains.
- **Step 3**: Assign a 6-digit canonical barcode and add products from different chains to the canonical product.
- **Step 4**: Select or create a category for the product.
- **Step 5**: Preview the canonical product data and save it to the MongoDB database.

## Example Canonical Product Document

```json
{
    "canonical_barcode": 100001,
    "name": "Cucumbers",
    "category": "Vegetables",
    "chains": {
        "ChainX": 888888,
        "ChainY": 999999
    },
    "created_at": "2024-09-20T12:34:56Z"
}
