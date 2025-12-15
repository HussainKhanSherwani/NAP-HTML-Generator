import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import os
import html

# ==========================================
# 1. IMAGE SCRAPING LOGIC (From NAP Item)
# ==========================================

def get_ebay_images(item_id):
    """ 
    Scrapes images from eBay using the NAP Item Number.
    Filters out the specific video placeholder 'DOcAAOSw8NplLtwK'.
    """
    if not item_id:
        return []

    url = f"https://www.ebay.com/itm/{item_id}"
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        grid_container = soup.find("div", {"class": "ux-image-grid"})
        
        image_urls = []
        if grid_container:
            buttons = grid_container.find_all("button", {"class": "ux-image-grid-item"})
            for btn in buttons:
                img = btn.find("img")
                if img:
                    src = img.get("src")
                    if not src or "data:image" in src:
                        src = img.get("data-src")
                    
                    if src:
                        # FILTER: Skip the specific video placeholder image
                        print(f"Found image src: {src}")
                        if "DOcAAOSw8NplLtwK" in src:
                            print("⏭️ Skipping video placeholder image." )
                            continue

                        # Force 1600 resolution
                        high_res = src.replace("s-l140", "s-l1600")
                        high_res = re.sub(r's-l\d+', 's-l1600', high_res)
                        image_urls.append(high_res)
                        
        return image_urls[:7] # Limit to first 7 images

    except Exception as e:
        st.error(f"Error scraping images: {e}")
        return []
# ==========================================
# 2. TEXT/DATA LOGIC (From Source URL)
# ==========================================

def clean_description_from_data(data_desc_tag):
    out_soup = BeautifulSoup("", "html.parser")
    seen_texts = set()
    out_children = []

    for tag in data_desc_tag.find_all(["h3", "p", "span", "div"], recursive=True):
        text = tag.get_text(" ", strip=True)
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)

        if tag.name == "h3" and not tag.find("span"):
            h = out_soup.new_tag("h3")
            h.string = text
            out_children.append(h)
            continue

        if tag.find("h3"):
            inner_h3 = tag.find("h3")
            inner_text = inner_h3.get_text(" ", strip=True)
            if inner_text and inner_text not in seen_texts:
                seen_texts.add(inner_text)
                h = out_soup.new_tag("h3")
                h.string = inner_text
                out_children.append(h)
            continue

        if len(text) < 40:
            h = out_soup.new_tag("h3")
            h.string = text
            out_children.append(h)
        else:
            p = out_soup.new_tag("p")
            p.string = text
            out_children.append(p)

    return out_children

def extract_compatibility_data(compat_section, template):
    inner_div = template.new_tag("div")
    current_ul = None

    for child in compat_section.find_all(recursive=False):
        text = child.get_text(" ", strip=True)
        if not text:
            continue

        is_brand = False
        if child.name == "h6" and not child.find(True):
            is_brand = True
        elif (child.name == "div" and child.find("font") and child.find("span") and child.find("b")):
            is_brand = True
        elif len(text) < 12:
            is_brand = True

        if is_brand:
            p = template.new_tag("p")
            strong = template.new_tag("strong")
            strong.string = text
            p.append(strong)
            inner_div.append(p)
            current_ul = template.new_tag("ul")
            inner_div.append(current_ul)
        else:
            if current_ul is None:
                current_ul = template.new_tag("ul")
                inner_div.append(current_ul)
            li = template.new_tag("li")
            li.string = text
            current_ul.append(li)

    return inner_div

def fetch_iframe_html(product_url):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}
    try:
        resp = requests.get(product_url, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        iframe = soup.find("iframe", id="desc_ifr")
        if iframe and iframe.get("src"):
            iframe_src = iframe.get("src")
            iframe_resp = requests.get(iframe_src, headers=headers)
            iframe_resp.raise_for_status()
            return iframe_resp.text
        else:
            st.error("Could not find description iframe (id='desc_ifr').")
            return None
    except Exception as e:
        st.error(f"Error fetching URL: {e}")
        return None

# ==========================================
# 3. MERGE LOGIC (FIXED)
# ==========================================

def merge_all_data(template_str, source_data_html, image_urls):
    template = BeautifulSoup(template_str, "html.parser")
    data = BeautifulSoup(source_data_html, "html.parser")

    # --- A. IMAGE INJECTION ---
    if image_urls:
        img_box = template.find("div", class_="product-image-box")
        
        if img_box:
            img_box.clear()
            
            # 1. Inject Inputs and Main Images
            for i, url in enumerate(image_urls):
                idx = i + 1
                inp_attrs = {"type": "radio", "name": "gal", "id": f"gal{idx}"}
                if i == 0:
                    inp_attrs["checked"] = ""
                
                inp = template.new_tag("input", attrs=inp_attrs)
                img_box.append(inp)
                
                content_div = template.new_tag("div", attrs={"id": f"content{idx}", "class": "product-image-container"})
                img_tag = template.new_tag("img", attrs={"src": url, "alt": f"Image {idx}"})
                content_div.append(img_tag)
                img_box.append(content_div)

            # 2. Inject Thumbnails (NOW INSIDE img_box)
            thumb_box = template.new_tag("div", attrs={"class": "thumbnails-box"})
            
            for i, url in enumerate(image_urls):
                idx = i + 1
                thumb_url = url.replace("s-l1600", "s-l140")
                
                label = template.new_tag("label", attrs={"for": f"gal{idx}", "class": "thumb-label"})
                t_img = template.new_tag("img", attrs={"src": thumb_url, "alt": f"Thumb {idx}"})
                label.append(t_img)
                thumb_box.append(label)
            
            # Append thumbnails at the bottom of the main image box
            img_box.append(thumb_box)

    # --- B. TEXT DATA INJECTION (Unchanged) ---
    title_tag = data.select_one(".title-name h2")
    if title_tag:
        template_title = template.select_one(".title h1")
        if template_title:
            template_title.string = title_tag.get_text(strip=True)

    data_desc = data.select_one('.desc-box')
    template_desc = template.select_one('.middle-right .description-details')
    if data_desc and template_desc:
        cleaned_children = clean_description_from_data(data_desc)
        template_desc.clear()
        for child in cleaned_children:
            template_desc.append(child)

    data_table = data.select_one(".tableinfo table")
    template_table = template.select_one("table.table")
    if data_table and template_table:
        target_tbody = template_table.find("tbody")
        source_tbody = data_table.find("tbody") or data_table
        if target_tbody:
            target_tbody.clear()
            for row in source_tbody.find_all("tr", recursive=False):
                target_tbody.append(row)
        else:
            template_table.clear()
            for elem in source_tbody.find_all("tr", recursive=False):
                template_table.append(elem)

    table_details = data.select(".table-details")
    compat_section = table_details[-1] if table_details else None
    if compat_section:
        compat_target = None
        all_descs = template.find_all("div", class_="description")
        for desc in all_descs:
            heading = desc.find("h4")
            if heading and "Compatible with the following vehicles" in heading.text:
                compat_target = desc
                break
        if compat_target:
            details_target = compat_target.find("div", class_="description-details")
            if details_target:
                details_target.clear()
                compat_div = extract_compatibility_data(compat_section, template)
                details_target.append(compat_div)

    return html.unescape(str(template))
# ==========================================
# 4. STREAMLIT UI
# ==========================================

st.set_page_config(page_title="eBay HTML Generator", layout="wide")
st.title("🛍️ eBay to HTML Template Generator")

st.sidebar.header("Template Settings")
template_content = ""
if os.path.exists("template.html"):
    with open("template.html", "r", encoding="utf-8") as f:
        template_content = f.read()
    st.sidebar.success("✅ Local `template.html` loaded.")
else:
    st.sidebar.warning("⚠️ `template.html` not found.")
    uploaded_template = st.sidebar.file_uploader("Upload template.html", type=["html"])
    if uploaded_template:
        template_content = uploaded_template.read().decode("utf-8")

col1, col2 = st.columns(2)
with col1:
    source_url = st.text_input("1. Source URL (Text/Data):", placeholder="https://www.ebay.com/itm/item-number")
with col2:
    nap_item_number = st.text_input("2. NAP Item Number (Images):", placeholder="e.g. 394857204958")

if st.button("Generate HTML"):
    if not template_content:
        st.error("Please ensure `template.html` is available.")
    elif not source_url or not nap_item_number:
        st.warning("Please fill in both fields.")
    else:
        with st.status("Processing...", expanded=True) as status:
            st.write("📝 Fetching Description & Data...")
            data_html = fetch_iframe_html(source_url)
            
            st.write(f"🖼️ Fetching Images for item {nap_item_number}...")
            ebay_images = get_ebay_images(nap_item_number)
            
            if data_html:
                st.write("✨ Injecting data into existing template structure...")
                try:
                    final_html = merge_all_data(template_content, data_html, ebay_images)
                    
                    status.update(label="Complete!", state="complete", expanded=False)
                    st.success("Success!")
                    
                    d_col1, d_col2 = st.columns(2)
                    with d_col1:
                        st.download_button("📥 Download HTML", data=final_html, file_name=f"{nap_item_number}.html", mime="text/html")
                    with d_col2:
                         with st.expander("View Source Code"):
                            st.code(final_html, language='html')
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                status.update(label="Failed", state="error")