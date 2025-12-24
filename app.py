import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import os
import html
import copy

# ==========================================
# 1. IMAGE SCRAPING LOGIC (Shared)
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
                        if "DOcAAOSw8NplLtwK" in src:
                            print("⏭️ Skipping video placeholder image." )
                            continue

                        high_res = src.replace("s-l140", "s-l1600")
                        high_res = re.sub(r's-l\d+', 's-l1600', high_res)
                        image_urls.append(high_res)
                        
        return image_urls[:6]

    except Exception as e:
        st.error(f"Error scraping images: {e}")
        return []

# ==========================================
# 2. TEXT/DATA LOGIC
# ==========================================

# --- A. XTREME SPECIFIC CLEANER (STRICT - UNCHANGED) ---
def clean_description_xtreme(data_desc_tag):
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

# --- B. CARPARTS SPECIFIC CLEANER (UPDATED FROM TEST CODE) ---
def clean_description_carparts(soup):
    """
    Refined logic for Carparts:
    1. Unpacks DIVs/Blocks recursively (prevents flattening).
    2. Preserves UL/LI structures.
    3. STRIPS styles/classes.
    4. Converts short text (< 40 chars) to H3.
    5. Converts long text to P.
    """
    out_soup = BeautifulSoup("", "html.parser")
    out_children = []

    # 1. Locate the container
    container = soup.find(id="content__right")
    if not container:
        container = soup.find("section", id="content__right") or soup
    
    # 2. Find Start Node
    start_node = None
    for h in container.find_all(["h2", "h1", "h3"]):
        if "Description" in h.get_text(strip=True):
            start_node = h
            break
    
    if not start_node:
        return []

    # --- Helper Function ---
    def process_node(node):
        if node.name is None:
            return []
        
        if node.name == 'section':
            return ["STOP"]

        # 1. Skip Useless Tags
        if ('desc__list' in node.get('class', []) or "Terms of Use" in node.get_text()):
            return []
        
        # 2. Check for nested Block Elements (Recursion Fix)
        # If a tag contains block elements, we must unpack it, not treat it as text.
        has_block_children = node.find(['ul', 'div', 'p', 'table', 'h3'])
        
        if node.name == 'div' or has_block_children:
            unpacked_children = []
            for child in node.children:
                res = process_node(child)
                if "STOP" in res: return ["STOP"]
                unpacked_children.extend(res)
            return unpacked_children

        # 3. Clean List Items (Preserve Structure)
        if node.name == 'ul':
            new_ul = out_soup.new_tag("ul")
            for li in node.find_all('li'):
                li_text = li.get_text(" ", strip=True)
                if li_text:
                    new_li = out_soup.new_tag("li")
                    new_li.string = li_text
                    new_ul.append(new_li)
            if new_ul.contents:
                return [new_ul]
            return []

        # 4. Text Blocks -> Apply Length Logic
        if node.name in ['p', 'h3', 'h4', 'strong', 'span']:
            # A. Remove Hidden Spans
            if hasattr(node, "find_all"):
                for hidden in node.find_all("span"):
                    style = hidden.get("style", "").lower()
                    if "color:#fff" in style or "color: #fff" in style or "#ffffff" in style:
                        hidden.decompose()

            full_text = node.get_text(" ", strip=True)
            if not full_text:
                return []

            # B. STRICT LENGTH LOGIC (< 40 chars -> H3, else P)
            if len(full_text) < 40:
                new_h3 = out_soup.new_tag("h3")
                new_h3.string = full_text
                return [new_h3]
            else:
                new_p = out_soup.new_tag("p")
                new_p.string = full_text
                return [new_p]

        return []

    # 3. Iterate Siblings
    for tag in start_node.next_siblings:
        results = process_node(tag)
        if "STOP" in results:
            break
        for res in results:
            out_children.append(res)

    return out_children

# --- COMPATIBILITY EXTRACTORS ---

def extract_compatibility_xtreme(compat_section, template):
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

def extract_compatibility_carparts(soup, template):
    inner_div = template.new_tag("div")
    
    container = soup.find("div", class_="item__list")
    if not container:
        return None

    for content_block in container.find_all("div", class_="items__list--content"):
        brand_p = content_block.find("p")
        if brand_p:
            new_p = template.new_tag("p")
            new_strong = template.new_tag("strong")
            new_strong.string = brand_p.get_text(strip=True)
            new_p.append(new_strong)
            inner_div.append(new_p)

        source_ul = content_block.find("ul")
        if source_ul:
            new_ul = template.new_tag("ul")
            for li in source_ul.find_all("li"):
                new_li = template.new_tag("li")
                new_li.string = li.get_text(" ", strip=True)
                new_ul.append(new_li)
            inner_div.append(new_ul)
            
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
# 3. MERGE LOGIC
# ==========================================

def merge_all_data(template_str, source_data_html, image_urls, mode="Xtreme"):
    template = BeautifulSoup(template_str, "html.parser")
    data = BeautifulSoup(source_data_html, "html.parser")

    # --- A. IMAGE INJECTION ---
    if image_urls:
        img_box = template.find("div", class_="product-image-box")
        
        if img_box:
            img_box.clear()
            
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

            thumb_box = template.new_tag("div", attrs={"class": "thumbnails-box"})
            
            for i, url in enumerate(image_urls):
                idx = i + 1
                thumb_url = url.replace("s-l1600", "s-l140")
                
                label = template.new_tag("label", attrs={"for": f"gal{idx}", "class": "thumb-label"})
                t_img = template.new_tag("img", attrs={"src": thumb_url, "alt": f"Thumb {idx}"})
                label.append(t_img)
                thumb_box.append(label)
            
            img_box.append(thumb_box)

    # --- B. TITLE INJECTION ---
    source_title = None
    if mode == "Xtreme":
        title_tag = data.select_one(".title-name h2")
        if title_tag: source_title = title_tag.get_text(strip=True)
    else: # Carparts
        title_tag = data.select_one(".eb_title")
        if title_tag: source_title = title_tag.get_text(strip=True)

    if source_title:
        template_title = template.select_one(".title h1")
        if template_title:
            template_title.string = source_title

    # --- C. DESCRIPTION INJECTION ---
    template_desc = template.select_one('.middle-right .description-details')
    cleaned_children = []

    if mode == "Xtreme":
        data_desc = data.select_one('.desc-box')
        if data_desc:
            cleaned_children = clean_description_xtreme(data_desc)
    else: # Carparts
        # We pass the WHOLE soup to carparts logic because it needs to find #content__right
        cleaned_children = clean_description_carparts(data)
            
    if template_desc and cleaned_children:
        template_desc.clear()
        for child in cleaned_children:
            template_desc.append(child)

    # --- D. TABLE INJECTION ---
    template_table = template.select_one("table.table")
    source_tbody = None

    if mode == "Xtreme":
        data_table = data.select_one(".tableinfo table")
        if data_table: source_tbody = data_table.find("tbody") or data_table
    else: # Carparts
        content_bottom = data.find(id="content__bottom")
        if content_bottom:
            data_table = content_bottom.find("table")
            if data_table: source_tbody = data_table.find("tbody") or data_table

    if template_table and source_tbody:
        target_tbody = template_table.find("tbody")
        if target_tbody:
            target_tbody.clear()
            for row in source_tbody.find_all("tr", recursive=False):
                target_tbody.append(row)
        else:
            template_table.clear()
            for elem in source_tbody.find_all("tr", recursive=False):
                template_table.append(elem)

    # --- E. COMPATIBILITY INJECTION ---
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
            compat_div = None
            
            if mode == "Xtreme":
                table_details = data.select(".table-details")
                compat_section = table_details[-1] if table_details else None
                if compat_section:
                    compat_div = extract_compatibility_xtreme(compat_section, template)
            
            else: # Carparts
                compat_div = extract_compatibility_carparts(data, template)

            if compat_div:
                details_target.clear()
                details_target.append(compat_div)

    return html.unescape(str(template))

# ==========================================
# 4. STREAMLIT UI
# ==========================================

st.set_page_config(page_title="eBay HTML Generator", layout="wide")
st.title("🛍️ eBay to HTML Template Generator")

st.sidebar.header("Configuration")

mode = st.sidebar.radio("Select Processing Mode:", ["Xtreme", "Carparts"], 
                        help="Select the source format to apply correct extraction logic.")

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
        with st.status(f"Processing in {mode} Mode...", expanded=True) as status:
            st.write("📝 Fetching Description & Data...")
            data_html = fetch_iframe_html(source_url)
            
            st.write(f"🖼️ Fetching Images for item {nap_item_number}...")
            ebay_images = get_ebay_images(nap_item_number)
            
            if data_html:
                st.write("✨ Injecting data into existing template structure...")
                try:
                    final_html = merge_all_data(template_content, data_html, ebay_images, mode=mode)
                    
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