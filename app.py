import streamlit as st
import pandas as pd
import requests
import re
from PIL import Image
import io
import cv2
import numpy as np
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    st.warning("Tesseract OCR not installed → coupon scanning disabled. Install it for full features!")

st.set_page_config(page_title="AdSmart Grocer Example", layout="wide")

st.title("🛒 AdSmart Grocer – Local Deals Finder")
st.caption("Example prototype for Chesterfield / New Baltimore, MI (ZIP 48047)")

# Sidebar
with st.sidebar:
    st.header("Your Settings")
    zip_code = st.text_input("ZIP Code", value="48047")
    st.info("Uses public Flipp endpoint to find local flyers (Meijer, Walmart, ALDI, Kroger, etc.)")

# Fetch deals function
@st.cache_data(ttl=3600)  # Cache 1 hour
def fetch_local_deals(zip_code):
    url = f"https://backflipp.wishabi.com/flipp/items/search?locale=en-us&postal_code={zip_code}&q=grocery&limit=300"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return pd.DataFrame(), f"Error {response.status_code}: Could not fetch deals."
        data = response.json()
        items = data.get("items", [])
        if not items:
            return pd.DataFrame(), "No deals found for this ZIP."
        
        deals = []
        for item in items:
            deals.append({
                "item": item.get("title", "").lower().strip(),
                "store": item.get("merchant_name", "Unknown"),
                "price": item.get("current_price", None) or item.get("price", None),
                "original_price": item.get("pre_price_text", None) or item.get("price", None),
                "sale_text": item.get("sale_story", "") or item.get("description", ""),
                "valid_to": item.get("valid_to", "N/A"),
                "image": item.get("image_url", None)
            })
        df = pd.DataFrame(deals)
        df = df[df["price"].notna()]  # Keep only priced items
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        return df.sort_values("price"), None
    except Exception as e:
        return pd.DataFrame(), f"Fetch failed: {str(e)}"

# Load deals
if st.button("🔄 Load/Refresh Local Deals", use_container_width=True):
    with st.spinner("Scanning flyers for your area..."):
        deals_df, error = fetch_local_deals(zip_code)
        if error:
            st.error(error)
        else:
            st.session_state["deals_df"] = deals_df
            st.success(f"Loaded {len(deals_df)} current deals! (Meijer, Walmart, etc.)")

# Use cached deals if available
deals_df = st.session_state.get("deals_df", pd.DataFrame())

# Shopping list
st.subheader("Your Shopping List")
list_input = st.text_area("Enter items (one per line, e.g. milk 2 gallons\nbananas\nbread)", height=120)
items = [line.strip().lower() for line in list_input.split("\n") if line.strip()]

# Coupon scanner
st.subheader("💸 Scan a Coupon (optional)")
uploaded_file = st.file_uploader("Upload coupon photo", type=["jpg", "png", "jpeg"])
coupon_savings = {}
if uploaded_file and OCR_AVAILABLE:
    img_bytes = uploaded_file.read()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    text = pytesseract.image_to_string(thresh).lower()
    st.info("Extracted text preview: " + text[:200] + "...")
    
    # Simple regex parse for common coupon formats
    matches = re.findall(r'(?:save|\$|off)\s*(\d*\.?\d*)\s*(?:on|for)?\s*([\w\s]+)', text)
    for amount, prod in matches:
        try:
            amt = float(amount)
            key = prod.strip().lower()
            coupon_savings[key] = amt
            st.success(f"Detected: ${amt:.2f} off {prod}")
        except:
            pass

# Build smart list
if st.button("Build Smart Shopping Plan", type="primary", use_container_width=True) and not deals_df.empty and items:
    st.subheader("Your Cost-Saving Plan")
    
    results = []
    total_est = 0
    total_savings = 0
    
    for item in items:
        matches = deals_df[deals_df["item"].str.contains(item, na=False)]
        if not matches.empty:
            best = matches.loc[matches["price"].idxmin()]
            coupon_off = 0
            for key, val in coupon_savings.items():
                if key in item or key in best["item"]:
                    coupon_off = val
                    break
            final_price = best["price"] - coupon_off
            savings = (best["original_price"] if pd.notna(best["original_price"]) else best["price"]) - final_price
            results.append({
                "Item": item.title(),
                "Best Store": best["store"],
                "Deal Price": f"${final_price:.2f}",
                "Savings": f"${savings:.2f}",
                "Valid Until": best["valid_to"][:10],
                "Deal Text": best["sale_text"][:60] + "..." if len(best["sale_text"]) > 60 else best["sale_text"]
            })
            total_est += final_price
            total_savings += savings
        else:
            results.append({"Item": item.title(), "Best Store": "No deal found", "Deal Price": "—", "Savings": "—", "Valid Until": "—", "Deal Text": ""})
    
    if results:
        st.dataframe(pd.DataFrame(results), use_container_width=True)
        col1, col2 = st.columns(2)
        col1.metric("Estimated Total (with deals)", f"${total_est:.2f}")
        col2.metric("Potential Savings This Trip", f"${total_savings:.2f}", delta_color="normal")
else:
    if deals_df.empty:
        st.info("Click 'Load/Refresh Local Deals' first to see your area's flyers.")
    elif not items:
        st.info("Add some items to your list!")

st.caption("This is a starter example — deals refresh from Flipp (public endpoint). For production, add error handling, more parsing, multi-store optimization, etc.")
st.caption("Want upgrades? Receipt scanning, recipe suggestions, Flutter mobile version — just say the word!")
