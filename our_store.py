import streamlit as st
from bs4 import BeautifulSoup
import requests
import re
import os
import html
import pandas as pd

# ==========================================
# 1. SHARED IMAGE SCRAPING
# ==========================================

def fetch_url_standard(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url.strip(), headers=headers, timeout=15)
        if response.status_code == 200:
            # Force UTF-8 encoding to prevent characters like â€™
            response.encoding = "utf-8" 
            return response.text
    except:
        pass
    return None

def parse_images_from_html(html_content):
    if not html_content: return []
    soup = BeautifulSoup(html_content, "html.parser")
    grid = soup.find("div", {"class": "ux-image-grid"})
    urls = []
    if grid:
        for btn in grid.find_all("button", {"class": "ux-image-grid-item"}):
            img = btn.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src and "DOcAAOSw8NplLtwK" not in src:
                    # Upgrade to high-resolution 1600px images
                    src = re.sub(r's-l\d+', 's-l1600', src)
                    urls.append(src)
    return urls

def get_ebay_images(item_id):
    url = f"https://www.ebay.com/itm/{item_id}"
    html_content = fetch_url_standard(url)
    images = parse_images_from_html(html_content)
    return images[:6]

# ==========================================
# 2. STRUCTURED CONTENT FORMATTERS
# ==========================================

def format_pasted_text_to_html(raw_text):
    if not raw_text: return ""
    if "<p>" in raw_text or "<ul>" in raw_text: return raw_text

    # Fix encoding artifacts manually just in case
    raw_text = raw_text.replace("â€™", "'").replace("â€“", "-").replace("â€œ", '"').replace("â€\x9d", '"')
    
    soup = BeautifulSoup("", "html.parser")

    # --- NEW: STATIC LINKS INSERTION ---
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
    soup.append(BeautifulSoup(STATIC_LINKS_HTML, "html.parser"))
    # -----------------------------------

    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    current_ul = None

    for i, line in enumerate(lines):
        # 1. FIRST LINE HEADING RULE (Strip Numbers, Hyphens, Special Chars - Allow only Alpha and Spaces)
        if i == 0 and len(line) < 50:
            # Updated Regex: remove everything except alphabets and spaces
            clean_title = re.sub(r'[^a-zA-Z\s]', '', line).strip()
            h3 = soup.new_tag("h3")
            h3.string = clean_title
            soup.append(h3)
            continue

        # 2. LIST DETECTION LOGIC
        # Detects explicit bullets OR lines that appear to be part of a list block
        is_explicit_bullet = re.match(r'^(\d+x|[-•*])', line)
        
        # Lookahead: Is the line after this a list item?
        next_is_list = False
        if i + 1 < len(lines):
            next_is_list = re.match(r'^(\d+x|[-•*])', lines[i+1])
        
        # Lookahead: Is this a short line followed by a block of sentences?
        # (This handles "Easy to Install" being followed by description sentences)
        is_heading_for_list = len(line) < 60 and i + 1 < len(lines) and len(lines[i+1]) > 40

        if is_explicit_bullet:
            if not current_ul:
                current_ul = soup.new_tag("ul")
                soup.append(current_ul)
            li = soup.new_tag("li")
            li.string = re.sub(r'^(\d+x|[-•*])\s*', '', line)
            current_ul.append(li)
            continue
        
        # If we are currently inside a list block and the line is descriptive
        if current_ul and len(line) > 55:
            li = soup.new_tag("li")
            li.string = line
            current_ul.append(li)
            continue

        # 3. HEADER & STRONG PARAGRAPH DETECTION
        current_ul = None 

        # Priority: Keywords like Features/Benefits always h3
        if "Features" in line or "Benefits" in line:
            h3 = soup.new_tag("h3")
            h3.string = line.replace(':', '')
            soup.append(h3)
            
        # Priority: Sub-headers that introduce a list
        elif is_heading_for_list:
            # We treat the next lines as a list
            p = soup.new_tag("p")
            strong = soup.new_tag("strong")
            strong.string = line
            p.append(strong)
            soup.append(p)
            # Flag that we are starting a list block
            current_ul = soup.new_tag("ul")
            soup.append(current_ul)
            
        # Priority: Standard Headers (All Caps or ending in :)
        elif len(line) < 50 and (line.isupper() or line.endswith(':')):
            h3 = soup.new_tag("h3")
            h3.string = line.replace(':', '')
            soup.append(h3)
            
        # Fallback: Normal Paragraph
        else:
            p = soup.new_tag("p")
            p.string = line
            soup.append(p)
            
    return str(soup)

def format_compatibility_to_grid(raw_text, template_soup):
    """Builds the <div class="compat-grid"> structure."""
    grid_div = template_soup.new_tag("div", attrs={"class": "compat-grid"})
    if not raw_text: return grid_div

    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    current_ul = None

    for line in lines:
        if "compatible with" in line.lower():
            continue

        # Sanitization: Ignore colons and check only alphabets for Brand detection
        brand_check_line = line.replace(':', '').strip()
        clean_name_check = brand_check_line.replace(" ", "")
        
        is_short = len(brand_check_line) < 12
        one_space_max = brand_check_line.count(" ") <= 1
        # Rule: Only include alphabets for the brand title detection
        is_alpha = clean_name_check.isalpha()
        
        if is_short and one_space_max and is_alpha:
            p_brand = template_soup.new_tag("p")
            strong = template_soup.new_tag("strong")
            strong.string = brand_check_line # Use sanitized string without colon
            p_brand.append(strong)
            grid_div.append(p_brand)
            current_ul = template_soup.new_tag("ul")
            grid_div.append(current_ul)
        else:
            if current_ul is None:
                current_ul = template_soup.new_tag("ul")
                grid_div.append(current_ul)
            
            li = template_soup.new_tag("li")
            li.string = re.sub(r'^[-•*]\s*', '', line)
            current_ul.append(li)

    return grid_div

def inject_compact_table_css(template_soup):
    style_tag = template_soup.find("style")
    if not style_tag:
        style_tag = template_soup.new_tag("style")
        if template_soup.head:
            template_soup.head.append(style_tag)
        else:
            template_soup.body.insert(0, style_tag)

    css_code = """
        .table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        .table td { width: 25%; padding: 8px; border: 1px solid #eee; font-size: 14px; }
        .table tr td:nth-child(1), .table tr td:nth-child(3) { font-weight: bold; color: #333; }
        .table tr td:nth-child(2), .table tr td:nth-child(4) { color: #555; }
        .table tr:nth-child(odd) td { background-color: #fff; }
        .table tr:nth-child(even) td { background-color: #f2f2f2; }
    """
    style_tag.string = (style_tag.string or "") + css_code

# ==========================================
# 3. MERGE LOGIC
# ==========================================

def merge_data_to_file(template_str, title, images, description, compatibility, table_df, notes_text):
    template = BeautifulSoup(template_str, "html.parser")
    inject_compact_table_css(template)

    # --- A. INJECT IMAGES ---
    if images:
        img_box = template.find("div", class_="product-image-box")
        if img_box:
            img_box.clear()
            for i, url in enumerate(images):
                idx = i + 1
                inp = template.new_tag("input", attrs={"type": "radio", "name": "gal", "id": f"gal{idx}"})
                if i == 0: inp.attrs["checked"] = ""
                img_box.append(inp)
                div = template.new_tag("div", attrs={"id": f"content{idx}", "class": "product-image-container"})
                div.append(template.new_tag("img", attrs={"src": url}))
                img_box.append(div)
            
            thumb_box = template.new_tag("div", attrs={"class": "thumbnails-box"})
            for i, url in enumerate(images):
                idx = i + 1
                lbl = template.new_tag("label", attrs={"for": f"gal{idx}", "class": "thumb-label"})
                lbl.append(template.new_tag("img", attrs={"src": url.replace("s-l1600", "s-l140")}))
                thumb_box.append(lbl)
            img_box.append(thumb_box)

    # --- B. INJECT TITLE ---
    title_h1 = template.select_one(".title h1")
    if title_h1:
        title_h1.string = title

    # --- C. INJECT DESCRIPTION ---
    desc_box = template.select_one('.middle-right .description-details')
    if desc_box:
        desc_box.clear()
        formatted_html = format_pasted_text_to_html(description)
        desc_box.append(BeautifulSoup(formatted_html, "html.parser"))

    # --- D. INJECT TABLE ---
    t_body = template.select_one("table.table tbody")
    if t_body:
        t_body.clear()
        all_pairs = []
        for _, row in table_df.iterrows():
            # Filter: Don't add pairs where Label or Value is empty or 'None' string
            lbl = str(row["Label"]).strip()
            val = str(row["Value"]).strip()
            if lbl and val and lbl.lower() != 'none' and val.lower() != 'none':
                all_pairs.append((lbl, val))

        for i in range(0, len(all_pairs), 2):
            new_row = template.new_tag("tr")
            for j in range(2):
                if i + j < len(all_pairs):
                    td_k = template.new_tag("td")
                    strong = template.new_tag("strong")
                    strong.string = str(all_pairs[i+j][0])
                    td_k.append(strong)
                    new_row.append(td_k)
                    td_v = template.new_tag("td")
                    td_v.string = str(all_pairs[i+j][1])
                    new_row.append(td_v)
                else:
                    new_row.append(template.new_tag("td"))
                    new_row.append(template.new_tag("td"))
            t_body.append(new_row)

    # --- E. INJECT NOTES ---
    if notes_text:
        # Filter out specific ignored text and empty lines
        ignored_phrase = "Brand New in the Box - Fit and Quality Guaranteed!"
        extracted_notes = [
            n.strip() for n in notes_text.split('\n') 
            if n.strip() and ignored_phrase not in n
        ]
        
        # Locate the paragraph with the red warning variable styling
        red_warning = template.find("p", style=lambda s: s and "var(--red)" in s)
        notes_container = red_warning.parent if red_warning else None
        
        if notes_container:
            for note in extracted_notes:
                new_p = template.new_tag("p")
                new_p.string = note
                notes_container.append(new_p)

    # --- F. INJECT COMPATIBILITY ---
    all_descriptions = template.find_all("div", class_="description")
    compat_section = None
    for d in all_descriptions:
        h4 = d.find("h4")
        if h4 and "Compatible" in h4.get_text():
            compat_section = d
            break

    if compat_section:
        det_container = compat_section.find("div", class_="description-details-1")
        if det_container:
            det_container.clear()
            grid_content = format_compatibility_to_grid(compatibility, template)
            det_container.append(grid_content)

    return html.unescape(str(template))

# ==========================================
# 4. STREAMLIT UI
# ==========================================

st.set_page_config(layout="wide", page_title="eBay Template Merger")

if os.path.exists("template.html"):
    with open("template.html", "r", encoding="utf-8") as f:
        master_template = f.read()
else:
    st.error("Missing 'template.html'")
    st.stop()

st.title("📦 eBay Structured Template Merger")

# --- Table Session State Management ---
if 'table_data' not in st.session_state:
    st.session_state.table_data = pd.DataFrame([{"Label": "", "Value": ""}] * 5)

def reset_table():
    st.session_state.table_data = pd.DataFrame([{"Label": "", "Value": ""}] * 5)

col_input, col_preview = st.columns([1, 1])

with col_input:
    st.header("Data Entry")
    item_id = st.text_input("eBay Item ID")
    
    scraped_imgs = []
    if item_id:
        scraped_imgs = get_ebay_images(item_id)
        if scraped_imgs:
            st.image(scraped_imgs, width=80)

    item_title = st.text_input("Item Title")
    pasted_desc = st.text_area("Description Text", height=200)
    pasted_compat = st.text_area("Compatibility (Brand, then Vehicles)", height=200)
    pasted_notes = st.text_area("Notes (Appends to section with var(--red) styling)", height=100)

    st.subheader("Specification Table")
    # Option to clear the table
    if st.button("🗑️ Clear Table"):
        reset_table()
        st.rerun()

    st.info("Directly paste your table data from Excel below. (Empty rows or 'None' values are ignored automatically)")
    
    # Edited Data Editor linked to Session State
    edited_df = st.data_editor(st.session_state.table_data, num_rows="dynamic", use_container_width=True)

    if st.button("Generate HTML"):
        final_html = merge_data_to_file(
            master_template, item_title, scraped_imgs, 
            pasted_desc, pasted_compat, edited_df, pasted_notes
        )
        st.success("Ready for Download!")
        st.download_button("📥 Download HTML", final_html, f"{item_id}.html", "text/html")