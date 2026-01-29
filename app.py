import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import os
import html
import copy

# ==========================================
# 1. SHARED NETWORKING & HELPERS
# ==========================================

def fetch_url_standard(url):
    """
    Standard fetcher with explicit UTF-8 encoding handling.
    """
    try:
        if not isinstance(url, str): url = str(url)
        headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
        }
        response = requests.get(url.strip(), headers=headers, timeout=15)
        if response.status_code == 200:
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
                    src = src.replace("s-l140", "s-l1600")
                    src = re.sub(r's-l\d+', 's-l1600', src)
                    urls.append(src)
    return urls

def extract_iframe_url(html_content):
    if not html_content: return None
    soup = BeautifulSoup(html_content, "html.parser")
    iframe = soup.find("iframe", id="desc_ifr")
    if iframe and iframe.get("src"):
        return iframe.get("src")
    return None

@st.cache_data(show_spinner=False)
def get_ebay_images(item_id):
    """ 
    Scrapes images from eBay. Uses standard fetch (No ScrapingAnt).
    """
    # print(f"   📸 Scraping images for {item_id}...")
    url = f"https://www.ebay.com/itm/{item_id}"
    html_content = fetch_url_standard(url)
    images = parse_images_from_html(html_content)
    return images[:6]

@st.cache_data(show_spinner=False)
def fetch_iframe_html(product_url):
    # print("   📄 Scraping description data...")
    main_html = fetch_url_standard(product_url)
    iframe_url = extract_iframe_url(main_html)
    
    if not iframe_url:
        st.error("Could not find description iframe (id='desc_ifr').")
        return None
    
    # print("   Testing Iframe content...")
    iframe_content = fetch_url_standard(iframe_url)
    return iframe_content

def inject_compact_table_css(template_soup, mode="Xtreme"):
    style_tag = template_soup.find("style")
    if not style_tag:
        style_tag = template_soup.new_tag("style")
        if template_soup.head:
            template_soup.head.append(style_tag)
        else:
            template_soup.body.insert(0, style_tag)

    css_code = ""
    
    # Base CSS
    css_code += """
        .table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        .table td { 
            width: 25%; 
            padding: 8px; 
            border: 1px solid #eee; 
            font-size: 14px; 
        }
    """
    
    # Extra Styling for Carparts (Zebra striping + Bold Headers)
    if mode == "Carparts":
        css_code += """
        /* HEADERS (Columns 1 & 3): Always bold/darker text */
        .table tr td:nth-child(1), .table tr td:nth-child(3) {
            font-weight: bold; color: #333;
        }
        
        /* VALUES (Columns 2 & 4): Normal gray text */
        .table tr td:nth-child(2), .table tr td:nth-child(4) {
            color: #555;
        }

        /* --- ZEBRA STRIPING LOGIC --- */
        /* ODD ROWS (1, 3, 5...): White Background */
        .table tr:nth-child(odd) td {
            background-color: #fff;
        }
        
        /* EVEN ROWS (2, 4, 6...): Light Gray Background */
        .table tr:nth-child(even) td {
            background-color: #f2f2f2; 
        }
        """

    if style_tag.string:
        style_tag.string += css_code
    else:
        style_tag.string = css_code

# ==========================================
# 2. XTREME SPECIFIC LOGIC
# ==========================================

def clean_description_xtreme(data_desc_tag):
    out_soup = BeautifulSoup("", "html.parser")
    seen_texts = set()
    out_children = []
    
    # --- [NEW] REMOVE UNWANTED HIDDEN SPANS BEFORE PROCESSING ---
    for bad_span in data_desc_tag.find_all("span"):
        style = bad_span.get("style", "").lower()
        if "color: rgb(255, 255, 255)" in style or "color: #ffffff" in style or "color: white" in style:
            if "font-size: 10px" in style or "font-size: 1px" in style:
                bad_span.decompose()

    # [FLAG] Track if we have already used the one allowed H3
    first_header_used = False

    for tag in data_desc_tag.find_all(["h3", "p", "span", "div"], recursive=True):
        text = tag.get_text(" ", strip=True)
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)

        # Determine if this element "wants" to be a header
        is_header_candidate = False
        
        # 1. Check explicit H3 tag (Must NOT have span)
        if tag.name == "h3" and not tag.find("span"):
            is_header_candidate = True
        
        # 2. Check nested H3
        elif tag.find("h3"):
             inner_h3 = tag.find("h3")
             inner_text = inner_h3.get_text(" ", strip=True)
             if inner_text and inner_text not in seen_texts:
                 seen_texts.add(inner_text)
                 text = inner_text 
                 is_header_candidate = True
        
        # 3. Check length threshold (< 30) AND ensure NO span inside
        elif len(text) < 30 and not tag.find("span"):
            is_header_candidate = True

        # --- LOGIC TO APPLY TAG TYPE ---
        if is_header_candidate:
            if not first_header_used:
                # FIRST ONE -> H3
                h = out_soup.new_tag("h3")
                h.string = text
                out_children.append(h)
                first_header_used = True
            else:
                # SUBSEQUENT ONES -> P (Bold)
                p = out_soup.new_tag("p")
                p.string = text
                p['style'] = "font-weight: bold;"
                out_children.append(p)
        else:
            # PLAIN TEXT -> P
            p = out_soup.new_tag("p")
            p.string = text
            out_children.append(p)

    return out_children

def extract_compatibility_xtreme(compat_section, template):
    inner_div = template.new_tag("div")
    inner_div['class'] = "compat-grid" 
    current_ul = None

    for child in compat_section.find_all(recursive=False):
        text = child.get_text(" ", strip=True)
        if not text: continue
        
        if "compatible with the following vehicles" in text.lower():
            continue

        # --- 1. NESTED LIST CHECK (e.g. <h6><ul>...</ul></h6>) ---
        internal_list_items = child.find_all("li")
        if internal_list_items:
            if current_ul is None:
                current_ul = template.new_tag("ul")
                inner_div.append(current_ul)
            
            for item in internal_list_items:
                li_text = item.get_text(" ", strip=True)
                if li_text:
                    new_li = template.new_tag("li")
                    new_li.string = li_text
                    current_ul.append(new_li)
            continue

        # --- 2. NESTED PARAGRAPH CHECK (e.g. <h6><p>...</p></h6>) ---
        internal_paragraphs = child.find_all("p", recursive=False)
        if internal_paragraphs:
             if current_ul is None:
                current_ul = template.new_tag("ul")
                inner_div.append(current_ul)
             for p in internal_paragraphs:
                p_text = p.get_text(" ", strip=True)
                if p_text:
                    new_li = template.new_tag("li")
                    new_li.string = p_text
                    current_ul.append(new_li)
             continue

        # --- 3. BRAND DETECTION (Refined) ---
        is_brand = False
        
        # Case 1: H6
        if child.name == "h6":
            # If it has NO children tags, it's a Brand (e.g. <h6>Chevrolet</h6>)
            if not child.find(True):
                is_brand = True
            # If it DOES have children (e.g. <h6><font>...</font></h6>)
            elif len(text) < 30: 
                is_brand = True
            else:
                is_brand = False
        
        # Case 2: Specific DIV structure
        elif (child.name == "div" and child.find("font") and child.find("span") and child.find("b")): 
            is_brand = True
        
        # Case 3: Fallback length check
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

def extract_notes_xtreme(soup):
    notes = []
    # Select ALL .table-details blocks
    all_details = soup.select(".tableinfo .table-details")
    
    # Only process the FIRST block ([0]) if it exists
    if all_details:
        first_details = all_details[0]
        for child in first_details.find_all(["p", "div", "span"], recursive=False):
            child_text = child.get_text(" ", strip=True)
            if not child_text: continue
            
            t_lower = child_text.lower()
            if "brand new in the box" in t_lower or "quality guaranteed" in t_lower:
                continue
            if "compatible with the following vehicles" in t_lower:
                continue

            notes.append(child_text)
            
    return notes

# ==========================================
# 3. CARPARTS SPECIFIC LOGIC
# ==========================================

def clean_description_carparts(soup):
    out_soup = BeautifulSoup("", "html.parser")
    raw_nodes = [] 
    
    container = soup.find(id="content__right") or soup.find("section", id="content__right") or soup
    
    start_node = None
    for h in container.find_all(["h2", "h1", "h3", "h4"]):
        if "Description" in h.get_text(strip=True):
            start_node = h; break
            
    if not start_node: return []

    # --- HELPER 1: SMART MOJIBAKE REPAIR (UTF-8 Fix) ---
    def fix_mojibake(text):
        if not text: return ""
        try:
            text = text.encode('cp1252').decode('utf-8')
        except:
            try:
                text = text.encode('latin1').decode('utf-8')
            except:
                pass 
        replacements = {
            "â€™": "'", "â€œ": '"', "â€": '"', "â€”": "-", "â€“": "-", "Â": " ", "â€¦": "...",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text.strip()


    def process_node(node):
        if node.name is None: return [] 
        if node.name == 'section': return ["STOP"]
        if ('desc__list' in node.get('class', []) or "Terms of Use" in node.get_text()): return []
        
        # [SAFEGUARD] Always Keep "CAPA CERTIFIED"
        raw_text_lower = node.get_text(" ", strip=True).lower()
        is_capa = "capa certified" in raw_text_lower
        
        if not is_capa:            
            # 2. IGNORE SPECIFIC WARNING TEXT
            if "use existing emblem" in raw_text_lower: return []

        # Flatten Divs
        if node.name == 'div' or node.find(['ul', 'div', 'p']):
            unpacked = []
            for child in node.children:
                res = process_node(child)
                if "STOP" in res: return ["STOP"]
                unpacked.extend(res)
            return unpacked
            
        # Lists
        if node.name == 'ul':
            new_ul = out_soup.new_tag("ul")
            for li in node.find_all('li'):
                
                if li.text.strip():
                    new_li = out_soup.new_tag("li")
                    new_li.string = fix_mojibake(li.text)
                    new_ul.append(new_li)
            return [new_ul] if new_ul.contents else []
            
        # Headers & Paragraphs
        if node.name in ['p', 'h3', 'h4', 'h5', 'h6']:
            
            # 4. Remove hidden spans (SKUs)
            for span in node.find_all("span"): span.decompose()
            
            txt = fix_mojibake(node.get_text(" ", strip=True))
            if not txt: return []
            
            # 5. Create Tags
            if node.name in ['h3', 'h4', 'h5', 'h6']:
                 tag = out_soup.new_tag("h3")
                 tag.string = txt
            else:
                 tag = out_soup.new_tag("p")
                 if node.find("strong") or node.find("b"):
                     strong = out_soup.new_tag("strong")
                     strong.string = txt
                     tag.append(strong)
                 else:
                     tag.string = txt
                     
            return [tag]
            
        return []

    # --- Step A: Collect Raw Nodes ---
    for tag in start_node.next_siblings:
        results = process_node(tag)
        if "STOP" in results: break
        raw_nodes.extend(results)

    # --- Step B: Deduplicate Headers ---
    deduped_nodes = []
    strong_texts = set()
    for node in raw_nodes:
        if node.name == 'p' and node.find('strong'):
            strong_texts.add(node.get_text(strip=True).lower())

    for node in raw_nodes:
        if node.name == 'h3':
            h3_text = node.get_text(strip=True).lower()
            # If duplicate exists, skip it UNLESS it is CAPA
            if h3_text in strong_texts and "capa certified" not in h3_text:
                continue 
        deduped_nodes.append(node)

    # --- Step C: Final Formatting ---
    final_nodes = []
    count = len(deduped_nodes)
    
    for i, node in enumerate(deduped_nodes):
        if node.name == 'p':
            strong_tag = node.find('strong')
            
            # 1. Convert Entirely Bold P -> H3
            if strong_tag and len(strong_tag.get_text(strip=True)) >= len(node.get_text(strip=True)) - 2:
                new_h3 = out_soup.new_tag("h3")
                new_h3.string = node.get_text(strip=True)
                final_nodes.append(new_h3)
                continue 
            
            # 2. Bold "Intro" Paragraphs before Lists
            if len(node.get_text(strip=True)) < 50:
                if i + 1 < count: 
                    next_node = deduped_nodes[i+1]
                    if next_node.name == 'ul':
                        node['style'] = "font-weight: bold;"
            
            final_nodes.append(node)
        else:
            final_nodes.append(node)

    return final_nodes

def extract_compatibility_carparts(soup, template):
    inner_div = template.new_tag("div")
    inner_div['class'] = "compat-grid" 
    
    container = soup.find("div", class_="item__list")
    if not container: return None
    
    for block in container.find_all("div", class_="items__list--content"):
        for child in block.find_all(["p", "ul"], recursive=False):
            if child.name == "p":
                new_p = template.new_tag("p")
                strong = template.new_tag("strong")
                strong.string = child.get_text(strip=True)
                new_p.append(strong)
                inner_div.append(new_p)
            elif child.name == "ul":
                new_ul = template.new_tag("ul")
                for li in child.find_all("li"):
                    new_li = template.new_tag("li")
                    new_li.string = li.get_text(" ", strip=True)
                    new_ul.append(new_li)
                inner_div.append(new_ul)
                
    return inner_div

# ==========================================
# 4. OUR STORE SPECIFIC LOGIC (UNCHANGED)
# ==========================================

def extract_specs_ourstore(soup):
    specs = {}
    list_mappings = {"Part Link Number": "Part Link Number", "OE / OEM Number": "OE / OEM Number", "Parts Includes": "Components"}

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

    target_keys = ["Certification", "Anticipated Ship Out Time", "Quantity Sold", "Product Fit", "Replaces OE Number", "Finish", "Recommended Use", "Parts link Number", "Vehicle Body Type", "Color"]

    for p in soup.find_all('p'):
        text = p.get_text(" ", strip=True)
        if "P65Warnings.ca.gov" in text:
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

    if "Prop 65 Warning" not in specs:
        specs["Prop 65 Warning"] = "WARNING: This product can expose you to chemicals including Chromium, Lead and lead compounds, Nickel, which is known to the State of California to cause cancer and birth defects or other reproductive harm. For more information go to www.P65Warnings.ca.gov."

    return specs

def clean_description_ourstore(soup_input):
    soup = soup_input
    out_soup = BeautifulSoup("", "html.parser")
    out_children = []
    
    start_node = None
    all_paragraphs = soup.find_all('p')
    for p in all_paragraphs:
        if "Warranty Coverage Policy" in p.get_text():
            start_node = p; break
    if not start_node:
        for p in all_paragraphs:
            if "Description" in p.get_text() and len(p.get_text()) < 20:
                start_node = p; break
    
    if not start_node: return []

    stop_keys = ["Certification:", "Anticipated Ship Out Time:", "Quantity Sold:", "Product Fit:", "Replaces OE Number:", "Finish:", "Recommended Use:", "Parts link Number:", "Vehicle Body Type:", "Color:", "Compatible with the Following Vehicles", "Return & Replacement Policy", "Prop 65 Warning", "P65Warnings.ca.gov"]
    
    raw_nodes = []
    for sibling in start_node.next_siblings:
        if sibling.name is None and not sibling.strip(): continue
        text = sibling.get_text(" ", strip=True)
        if not text: continue
        if any(k in text for k in stop_keys): break
        raw_nodes.append(sibling)

    for elem in raw_nodes:
        text = elem.get_text(" ", strip=True)
        is_heading = False
        if hasattr(elem, 'find'):
            span = elem.find("span", style=True)
            if span:
                style = span['style'].lower()
                if "font-weight: 700" in style or "font-weight: bold" in style: is_heading = True
                elif "font-size" in style:
                    match = re.search(r'font-size:\s*(\d+)pt', style)
                    if match and int(match.group(1)) >= 13: is_heading = True
        
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

def extract_compatibility_ourstore(soup, template):
    inner_div = template.new_tag("div")
    start_node = None
    for p in soup.find_all("p"):
        if "Compatible with the Following Vehicles" in p.get_text():
            start_node = p; break
    if not start_node: return None

    current_ul = None
    for sibling in start_node.next_siblings:
        if sibling.name is None: continue 
        text = sibling.get_text(" ", strip=True)
        if not text: continue
        if "Return & Replacement Policy" in text: break
        
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

# ==========================================
# 5. UNIFIED MERGE LOGIC
# ==========================================

def merge_all_data(template_str, source_data_html, image_urls, mode="Xtreme"):
    template = BeautifulSoup(template_str, "html.parser")
    data = BeautifulSoup(source_data_html, "html.parser")
    
    # [NEW] Inject CSS based on mode
    inject_compact_table_css(template, mode=mode)
    
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

    def strip_styles(tag):
        if hasattr(tag, 'attrs'): tag.attrs = {} 
        for child in tag.find_all(True): child.attrs = {}

    # --- A. IMAGES (Shared) ---
    if image_urls:
        img_box = template.find("div", class_="product-image-box")
        if img_box:
            img_box.clear()
            for i, url in enumerate(image_urls):
                idx = i + 1
                inp = template.new_tag("input", attrs={"type": "radio", "name": "gal", "id": f"gal{idx}"})
                if i == 0: inp.attrs["checked"] = ""
                img_box.append(inp)
                div = template.new_tag("div", attrs={"id": f"content{idx}", "class": "product-image-container"})
                div.append(template.new_tag("img", attrs={"src": url}))
                img_box.append(div)
            
            thumb_box = template.new_tag("div", attrs={"class": "thumbnails-box"})
            for i, url in enumerate(image_urls):
                idx = i + 1
                lbl = template.new_tag("label", attrs={"for": f"gal{idx}", "class": "thumb-label"})
                lbl.append(template.new_tag("img", attrs={"src": url.replace("s-l1600", "s-l140")}))
                thumb_box.append(lbl)
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

    if source_title and template.select_one(".title h1"):
        template.select_one(".title h1").string = source_title

    # --- C. DESCRIPTION ---
    desc_box = template.select_one('.middle-right .description-details')
    cleaned_children = []
    
    if mode == "Xtreme":
        data_desc = data.select_one('.desc-box')
        if data_desc: cleaned_children = clean_description_xtreme(data_desc)
    elif mode == "Carparts":
        cleaned_children = clean_description_carparts(data)
    elif mode == "Our Store":
        cleaned_children = clean_description_ourstore(data)

    if desc_box:
        desc_box.clear()
        desc_box.append(BeautifulSoup(STATIC_LINKS_HTML, "html.parser"))
        for child in cleaned_children: 
            desc_box.append(child)

    # --- D. TABLE LOGIC ---
    t_body = template.select_one("table.table tbody")
    if t_body:
        t_body.clear()
        
        if mode == "Xtreme":
            # Standard Copy
            source_table = data.select_one(".tableinfo table")
            if source_table:
                source_tbody = source_table.find("tbody") or source_table
                for row in source_tbody.find_all("tr", recursive=False):
                    t_body.append(row)
                    
        elif mode == "Carparts":
            # Double-Up Logic (4 Columns)
            s_table = data.find(id="content__bottom")
            if s_table and s_table.find("table"):
                 all_pairs = []
                 for row in s_table.find("table").find_all("tr"):
                     cells = row.find_all(['td', 'th'])
                     if len(cells) == 2:
                         strip_styles(cells[0])
                         strip_styles(cells[1])
                         all_pairs.append((cells[0], cells[1]))
                 
                 # Build NEW rows with 2 pairs per row
                 for i in range(0, len(all_pairs), 2):
                     new_row = template.new_tag("tr")
                     new_row.append(all_pairs[i][0])
                     new_row.append(all_pairs[i][1])
                     if i + 1 < len(all_pairs):
                         new_row.append(all_pairs[i+1][0])
                         new_row.append(all_pairs[i+1][1])
                     else:
                         new_row.append(template.new_tag("td"))
                         new_row.append(template.new_tag("td"))
                     t_body.append(new_row)

        elif mode == "Our Store":
            our_store_specs = extract_specs_ourstore(data)
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
                t_body.append(tr)

    # --- E. COMPATIBILITY ---
    compat_target = None
    all_d = template.find_all("div", class_="description")
    compat_target = next((d for d in all_d if d.find("h4") and "Compatible" in d.find("h4").text), None)
    
    if compat_target:
        det = compat_target.find("div", class_="description-details") or compat_target.find("div", class_="description-details-1")
        if det:
            c_div = None
            if mode == "Xtreme":
                table_details = data.select(".table-details")
                if table_details: c_div = extract_compatibility_xtreme(table_details[-1], template)
            elif mode == "Carparts":
                c_div = extract_compatibility_carparts(data, template)
            elif mode == "Our Store":
                c_div = extract_compatibility_ourstore(data, template)
            
            if c_div:
                det.clear()
                det.append(c_div)

    # --- F. NOTES EXTRACTION (NEW) ---
    notes_target_div = None
    red_warning = template.find("p", style=lambda s: s and "var(--red)" in s)
    if red_warning:
        notes_target_div = red_warning.parent

    if notes_target_div:
        extracted_notes = []
        
        if mode == "Xtreme":
            extracted_notes = extract_notes_xtreme(data)
        
        elif mode == "Carparts":
            # Find H2 "Notes" in source
            source_notes_header = data.find("h2", string=lambda t: t and "Notes" in t)
            if source_notes_header:
                curr = source_notes_header.next_sibling
                while curr:
                    if curr.name == 'div' and 'content__table-wrap' in curr.get('class', []): break
                    if curr.name in ['h2', 'h1', 'section']: break
                    
                    if curr.name == 'p':
                        note_text = curr.get_text(strip=True)
                        t_lower = note_text.lower()
                        if "brand new in the box" in t_lower and "quality guaranteed" in t_lower:
                            curr = curr.next_sibling; continue
                        if note_text:
                             extracted_notes.append(note_text)
                    curr = curr.next_sibling

        # Inject Notes
        for note in extracted_notes:
            new_p = template.new_tag("p")
            new_p.string = note
            notes_target_div.append(new_p)

    return html.unescape(str(template))

# ==========================================
# 6. STREAMLIT UI (Standard)
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