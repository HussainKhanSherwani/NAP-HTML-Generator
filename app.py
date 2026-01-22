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

@st.cache_data(show_spinner=False)
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

# --- B. CARPARTS SPECIFIC CLEANER (UNCHANGED) ---
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

# --- C. OUR STORE SPECIFIC LOGIC (UPDATED) ---

def extract_specs_ourstore(soup):
    """
    Extracts structured data for the table.
    Includes a HARDCODED fallback for Prop 65 if extraction fails.
    """
    specs = {}
    
    # --- 1. LIST BASED SPECS (Top of HTML) ---
    list_mappings = {
        "Part Link Number": "Part Link Number",
        "OE / OEM Number": "OE / OEM Number",
        "Parts Includes": "Components"
    }

    for p in soup.find_all(['p', 'span']):
        text = p.get_text(strip=True)
        matched_key = next((k for k in list_mappings if k in text), None)
        
        if matched_key:
            header_node = p if p.name == 'p' else p.find_parent('p')
            if not header_node: continue
            
            next_ul = header_node.find_next_sibling('ul')
            if next_ul:
                items = [li.get_text(" ", strip=True) for li in next_ul.find_all('li')]
                val = ", ".join(items)
                specs[list_mappings[matched_key]] = val

    # --- 2. LINE BASED SPECS (Bottom of HTML) ---
    target_keys = [
        "Certification", "Anticipated Ship Out Time", "Quantity Sold", 
        "Product Fit", "Replaces OE Number", "Finish", "Recommended Use", 
        "Parts link Number", "Vehicle Body Type", "Color"
    ]

    for p in soup.find_all('p'):
        text = p.get_text(" ", strip=True)
        
        # Check for Prop 65 (Dynamic Search)
        if "P65Warnings.ca.gov" in text:
            # Clean up the text if it has the header mashed in
            clean_text = text.replace("Prop 65 WarningWARNING", "WARNING")
            clean_text = clean_text.replace("Prop 65 Warning", "").strip()
            if clean_text.startswith(":"): clean_text = clean_text[1:].strip()
            
            specs["Prop 65 Warning"] = clean_text
            continue

        if ":" in text:
            parts = text.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            
            if key in target_keys and val: 
                specs[key] = val

    # --- 3. HARDCODED FALLBACK ---
    # If we didn't find the warning dynamically, force it in.
    if "Prop 65 Warning" not in specs:
        specs["Prop 65 Warning"] = "WARNING: This product can expose you to chemicals including Chromium, Lead and lead compounds, Nickel, which is known to the State of California to cause cancer and birth defects or other reproductive harm. For more information go to www.P65Warnings.ca.gov."

    return specs

def clean_description_ourstore(soup_input):
    """
    Parses 'Our Store' format using START/STOP markers.
    START = 'Warranty Coverage Policy'
    STOP  = Specs, Prop 65, or Compatibility headers.
    """
    soup = soup_input # Read-only access is fine
    out_soup = BeautifulSoup("", "html.parser")
    out_children = []
    
    # --- 1. FIND START MARKER ---
    start_node = None
    all_paragraphs = soup.find_all('p')
    
    for p in all_paragraphs:
        if "Warranty Coverage Policy" in p.get_text():
            start_node = p
            break
            
    if not start_node:
        # Fallback: Look for "Description :"
        for p in all_paragraphs:
            if "Description" in p.get_text() and len(p.get_text()) < 20:
                start_node = p
                break
    
    if not start_node: return []

    # --- 2. COLLECT SIBLINGS UNTIL STOP MARKER ---
    stop_keys = [
        "Certification:", "Anticipated Ship Out Time:", "Quantity Sold:", 
        "Product Fit:", "Replaces OE Number:", "Finish:", "Recommended Use:", 
        "Parts link Number:", "Vehicle Body Type:", "Color:", 
        "Compatible with the Following Vehicles", "Return & Replacement Policy",
        "Prop 65 Warning", "P65Warnings.ca.gov" # <--- ADDED STOP KEYS
    ]
    
    raw_nodes = []
    
    for sibling in start_node.next_siblings:
        if sibling.name is None and not sibling.strip(): continue
            
        text = sibling.get_text(" ", strip=True)
        if not text: continue
        
        # CHECK STOP CONDITION
        if any(k in text for k in stop_keys):
            break
            
        raw_nodes.append(sibling)

    # --- 3. FORMAT OUTPUT ---
    for elem in raw_nodes:
        text = elem.get_text(" ", strip=True)
        
        is_heading = False
        if hasattr(elem, 'find'):
            span = elem.find("span", style=True)
            if span:
                style = span['style'].lower()
                if "font-weight: 700" in style or "font-weight: bold" in style:
                    is_heading = True
                elif "font-size" in style:
                    match = re.search(r'font-size:\s*(\d+)pt', style)
                    if match and int(match.group(1)) >= 13:
                        is_heading = True
        
        if is_heading:
            h3 = out_soup.new_tag("h3")
            h3.string = text
            out_children.append(h3)
        elif elem.name == 'ul':
            new_ul = out_soup.new_tag("ul")
            for li in elem.find_all('li'):
                new_li = out_soup.new_tag("li")
                new_li.string = li.get_text(" ", strip=True)
                new_ul.append(new_li)
            out_children.append(new_ul)
        else:
            p = out_soup.new_tag("p")
            p.string = text
            out_children.append(p)

    return out_children
# --- COMPATIBILITY EXTRACTORS ---

def extract_compatibility_xtreme(compat_section, template):
    inner_div = template.new_tag("div")
    current_ul = None

    for child in compat_section.find_all(recursive=False):
        text = child.get_text(" ", strip=True)
        if not text: continue

        is_brand = False
        if child.name == "h6" and not child.find(True): is_brand = True
        elif (child.name == "div" and child.find("font") and child.find("span") and child.find("b")): is_brand = True
        elif len(text) < 12: is_brand = True

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
    if not container: return None

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

def extract_compatibility_ourstore(soup, template):
    """
    Extracts 'Compatible with the Following Vehicles' section for Our Store format.
    """
    inner_div = template.new_tag("div")
    start_node = None
    for p in soup.find_all("p"):
        if "Compatible with the Following Vehicles" in p.get_text():
            start_node = p
            break
    if not start_node: return None

    current_ul = None
    for sibling in start_node.next_siblings:
        if sibling.name is None: continue 
        text = sibling.get_text(" ", strip=True)
        if not text: continue
        if "Return & Replacement Policy" in text: break
        
        # Check Brand Header (e.g. inside <li ... font-size: 13pt ...>Dodge:</li>)
        is_brand = False
        if sibling.name == 'ul':
             first_li = sibling.find("li")
             if first_li and "font-size: 13pt" in str(first_li):
                 is_brand = True
                 text = first_li.get_text(" ", strip=True).replace(":", "")

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

@st.cache_data(show_spinner=False)
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

    # --- STATIC LINKS ---
    STATIC_LINKS_HTML = """
    <div class="static-links" style="padding-bottom: 10px; font-weight: bold;">
        <a href="https://www.ebay.com/str/hiveofdeals?_tab=about" target="_blank" 
           style="font-size: 16px; font-weight: 300; color: var(--ef-blue-tint-100, #0053a0); text-decoration-line: underline; text-decoration-thickness: 0.8px; text-underline-offset: 5px;">
           Terms of Use
        </a>
        <span style="margin: 10px 12px; font-size: 18px">|</span>
        <a href="https://www.ebay.com/str/hiveofdeals?_tab=about" target="_blank" 
           style="font-size: 16px; font-weight: 300; color: var(--ef-blue-tint-100, #0053a0); text-decoration-line: underline; text-decoration-thickness: 0.8px; text-underline-offset: 5px;">
           Warranty Coverage Policy
        </a>
    </div>
    """

    # --- A. IMAGES ---
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

    # --- B. TITLE ---
    source_title = None
    if mode == "Xtreme":
        title_tag = data.select_one(".title-name h2")
        if title_tag: source_title = title_tag.get_text(strip=True)
    elif mode == "Carparts":
        title_tag = data.select_one(".eb_title")
        if title_tag: source_title = title_tag.get_text(strip=True)
    elif mode == "Our Store":
        title_tag = data.find("span", style=lambda v: v and "font-size: 28pt" in v)
        if title_tag: source_title = title_tag.get_text(strip=True)

    if source_title:
        template_title = template.select_one(".title h1")
        if template_title: template_title.string = source_title

    # --- C. DESCRIPTION ---
    template_desc = template.select_one('.middle-right .description-details')
    cleaned_children = []

    if mode == "Xtreme":
        data_desc = data.select_one('.desc-box')
        if data_desc: cleaned_children = clean_description_xtreme(data_desc)
    elif mode == "Carparts":
        cleaned_children = clean_description_carparts(data)
    elif mode == "Our Store":
        cleaned_children = clean_description_ourstore(data)
    
    if template_desc:
        template_desc.clear()
        links_soup = BeautifulSoup(STATIC_LINKS_HTML, "html.parser")
        template_desc.append(links_soup)
        if cleaned_children:
            for child in cleaned_children: 
                template_desc.append(child)

    # --- D. TABLE (UPDATED) ---
    template_table = template.select_one("table.table")
    source_tbody = None
    
    # 1. Fetch Existing Table Data based on mode
    if mode == "Xtreme":
        data_table = data.select_one(".tableinfo table")
        if data_table: source_tbody = data_table.find("tbody") or data_table
    elif mode == "Carparts":
        content_bottom = data.find(id="content__bottom")
        if content_bottom:
            data_table = content_bottom.find("table")
            if data_table: source_tbody = data_table.find("tbody") or data_table
    
    # 2. Extract Specifics for Our Store (Not in table format in source)
    our_store_specs = {}
    if mode == "Our Store":
        our_store_specs = extract_specs_ourstore(data)

    if template_table:
        target_tbody = template_table.find("tbody")
        if not target_tbody:
            target_tbody = template.new_tag("tbody")
            template_table.append(target_tbody)
        else:
            target_tbody.clear() # Clear placeholder data from template

        # Case 1: Source has a table (Xtreme/Carparts)
        if source_tbody:
            for row in source_tbody.find_all("tr", recursive=False):
                target_tbody.append(row)
        
        # Case 2: Our Store (Inject extracted specs as rows)
        if mode == "Our Store" and our_store_specs:
            for key, val in our_store_specs.items():
                tr = template.new_tag("tr")
                
                td_key = template.new_tag("td")
                strong = template.new_tag("strong")
                strong.string = key
                td_key.append(strong)
                
                td_val = template.new_tag("td")
                td_val.string = val
                
                tr.append(td_key)
                tr.append(td_val)
                target_tbody.append(tr)

    # --- E. COMPATIBILITY ---
    compat_target = None
    all_descs = template.find_all("div", class_="description")
    for desc in all_descs:
        heading = desc.find("h4")
        if heading and "Compatible with" in heading.text:
            compat_target = desc
            break
    
    if compat_target:
        details_target = compat_target.find("div", class_="description-details")
        if details_target:
            compat_div = None
            if mode == "Xtreme":
                table_details = data.select(".table-details")
                if table_details: compat_div = extract_compatibility_xtreme(table_details[-1], template)
            elif mode == "Carparts":
                compat_div = extract_compatibility_carparts(data, template)
            elif mode == "Our Store":
                compat_div = extract_compatibility_ourstore(data, template)

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

mode = st.sidebar.radio("Select Processing Mode:", ["Xtreme", "Carparts", "Our Store"], 
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