import fitz  # PyMuPDF
import json
import os
from collections import Counter, defaultdict

INPUT_DIR = "input"
OUTPUT_DIR = "output"

def extract_outline(pdf_path):
    doc = fitz.open(pdf_path)
    spans_data = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Use sort=True for better reading order, crucial for vertical spacing and block analysis
        blocks = page.get_text("dict", sort=True)["blocks"] 
        for block_idx, block in enumerate(blocks):
            if "lines" not in block:
                continue
            for line_idx, line in enumerate(block["lines"]):
                for span_idx, span in enumerate(line["spans"]):
                    text = span["text"].strip()
                    if not text:
                        continue

                    spans_data.append({
                        "text": text,
                        "size": round(span["size"], 1),
                        "flags": span["flags"],
                        "font": span["font"],
                        "color": span["color"],
                        "page": page_num,
                        "block_lines": len(block["lines"]),
                        "line_spans": len(line["spans"]),
                        "bbox": span["bbox"],
                        "block_idx": block_idx, 
                        "line_idx": line_idx,   
                        "span_idx": span_idx,   
                        "is_first_span_in_block": (span_idx == 0 and line_idx == 0) 
                    })

    if not spans_data:
        return {"title": "Untitled Document", "outline": []}

    # --- Refined Title Detection ---
    title = "Untitled Document"
    first_page_spans = [s for s in spans_data if s["page"] == 0]
    
    # Identify unique font sizes on the first page
    first_page_sizes = sorted(list(set([s["size"] for s in first_page_spans])), reverse=True)

    # Attempt to find the largest text on the first page, near the top, as the title
    if first_page_sizes:
        for target_size in first_page_sizes:
            # Filter spans by current target size and those near the top third of the page
            potential_titles = [s for s in first_page_spans 
                                if s["size"] == target_size and s["bbox"][1] < doc[0].rect.height / 3] 
            
            # Sort by y-coordinate (top-most first) and then x-coordinate
            potential_titles.sort(key=lambda s: (s["bbox"][1], s["bbox"][0]))

            for s in potential_titles:
                word_count = len(s["text"].split())
                is_bold = (s["flags"] & 2) != 0

                # Heuristics for a good title: reasonable length, generally bold, and a minimum size (relaxed from 18 to 12)
                if 3 <= word_count <= 15 and is_bold and s["size"] >= 12.0: 
                    title = s["text"]
                    # Remove all spans associated with this title to prevent re-detection as heading
                    spans_data = [sd for sd in spans_data if not (
                        sd["page"] == s["page"] and sd["bbox"] == s["bbox"]
                    )]
                    break 
            if title != "Untitled Document":
                break 

    # --- Determine Common Font Size and Properties for Body Text ---
    # Filter out potential headings/noise (bold, short lines) to get a better common_size for true body text
    body_text_spans = [
        s for s in spans_data
        if not ((s["flags"] & 2) != 0) and # Not bold
           (len(s["text"].split()) > 5) and # Not too short (likely a heading)
           s["size"] < (first_page_sizes[0] if first_page_sizes else float('inf')) # Smaller than largest font on page 1 (potential title size)
    ]

    common_font = Counter([s["font"] for s in body_text_spans]).most_common(1)[0][0] if body_text_spans else ""
    common_size = Counter([s["size"] for s in body_text_spans]).most_common(1)[0][0] if body_text_spans else 9.0 

    # --- Heading Detection and Classification ---
    candidate_headings = []
    # Store text from previously identified candidate headings to avoid duplicates or partial captures
    identified_heading_texts = set() 

    for i, span in enumerate(spans_data):
        text = span["text"]
        
        # Skip if this specific span's text has already been identified as part of a heading
        if text in identified_heading_texts:
            continue

        score = 0
        flags = span["flags"]

        is_bold = (flags & 2) != 0
        
        font_diff = span["font"] != common_font
        
        # Relative size comparison: now checks if it's more than 1.1 times larger than common_size
        is_significantly_larger = (span["size"] > common_size * 1.1)

        is_isolated_block = span["block_lines"] == 1 
        is_short_line = len(text.split()) <= 10 

        vertical_gap = 0
        if i > 0 and span["page"] == spans_data[i-1]["page"]:
            previous_span_y1 = spans_data[i-1]["bbox"][3]
            current_span_y0 = span["bbox"][1]
            vertical_gap = current_span_y0 - previous_span_y1
            if vertical_gap > (span["size"] * 1.5) and vertical_gap < 50: # Cap large gaps to avoid misinterpreting page breaks etc.
                score += 1.5 

        # Heuristics scoring
        if is_bold:
            score += 2.5 # Increased weight for bold, crucial for forms
        if is_significantly_larger:
            score += 1.5 
        if is_isolated_block:
            score += 1.0
        if is_short_line:
            score += 0.8
        if font_diff:
            score += 0.5
        
        # Specific heuristic for numbered form labels (e.g., "1. Name...")
        is_numbered_label = False
        if text.split(' ')[0].replace('.', '').isdigit() and len(text.split()) > 1:
            score += 2.0 # Higher boost for numbered descriptive labels
            is_numbered_label = True
            # Penalize if it's just a standalone number (e.g., "3.")
            if len(text.split()) == 1 and text.endswith('.'): 
                 score -= 3.0 # Stronger penalty

        # --- Refined Final Filtering Condition ---
        # A heading candidate must satisfy *one* of these stronger conditions:
        # 1. Be bold AND a numbered descriptive label (very common for forms)
        # 2. Be bold AND significantly larger (typical headings)
        # 3. Be bold AND isolated (common for single-line bold headings)
        # 4. Have a very high score indicating multiple strong non-bold features

        is_a_heading = False
        if is_bold and (is_numbered_label or is_significantly_larger or is_isolated_block):
            is_a_heading = True
        elif score >= 3.5: # A higher general score to catch other complex cases
            is_a_heading = True

        if is_a_heading:
            # Exclude common boilerplate or non-heading text found in forms
            # Expanded exclusion list for form-specific noise
            if not (("declare that" in text.lower()) or \
                    ("undertake to" in text.lower()) or \
                    ("lump sum" in text.lower()) or \
                    (text.lower().strip() == "date") or \
                    (text.lower().strip() == "rs.") or \
                    (text.lower().strip() == "name") or # Exclude table headers as primary outline elements
                    (text.lower().strip() == "s.no") or
                    (text.lower().strip() == "age") or
                    (text.lower().strip() == "relationship")):

                # Combine contiguous spans that form a single logical heading line
                full_heading_text = text
                j = i + 1
                while j < len(spans_data) and \
                      spans_data[j]["page"] == span["page"] and \
                      abs(spans_data[j]["bbox"][1] - span["bbox"][1]) < span["size"] / 2 and \
                      spans_data[j]["bbox"][0] > span["bbox"][0]: # Check for x-position to be to the right

                    next_span = spans_data[j]
                    # Ensure continuity in formatting for combining
                    if next_span["size"] == span["size"] and \
                       next_span["font"] == span["font"] and \
                       next_span["color"] == span["color"] and \
                       len(next_span["text"].split()) <= 10: # Don't combine long paragraphs
                        full_heading_text += " " + next_span["text"]
                        identified_heading_texts.add(next_span["text"]) 
                    else:
                        break 
                    j += 1
                
                # Double-check to skip single numerical items that might have slipped through
                if full_heading_text.replace('.', '').strip().isdigit() and len(full_heading_text.split()) == 1:
                    continue 

                candidate_headings.append({
                    "text": full_heading_text,
                    "size": span["size"],
                    "page": span["page"],
                    "y0": span["bbox"][1]
                })
                identified_heading_texts.add(text) 

    # Sort candidates by page and then by y-coordinate to maintain document order
    candidate_headings.sort(key=lambda s: (s["page"], s["y0"]))

    # Rank sizes for heading levels from the identified candidates
    heading_sizes = [s["size"] for s in candidate_headings]
    size_counts = Counter(heading_sizes)
    # Sort by size (descending) primarily, then by frequency (descending)
    ranked_sizes = sorted(size_counts.items(), key=lambda x: (-x[0], -x[1]))

    size_to_level = defaultdict(str) 
    if len(ranked_sizes) > 0:
        size_to_level[ranked_sizes[0][0]] = "H1"
    if len(ranked_sizes) > 1:
        size_to_level[ranked_sizes[1][0]] = "H2"
    if len(ranked_sizes) > 2:
        size_to_level[ranked_sizes[2][0]] = "H3"
    
    # Fallback: if only one type of heading is detected, make it H1
    if len(set(size_to_level.values())) == 0 and candidate_headings:
        size_to_level[candidate_headings[0]["size"]] = "H1"

    outline = []
    for span in candidate_headings:
        level = size_to_level.get(span["size"])
        
        # If no specific level assigned (e.g., more than 3 distinct heading sizes),
        # assign based on size relative to other assigned levels. Defaults to H1.
        if not level:
            # Find closest smaller assigned size and assign next level
            # This logic needs to be careful not to create H2 from H1 if only one true level exists
            assigned_levels_present = {size_to_level[s] for s in size_to_level if size_to_level[s]}
            if "H1" in assigned_levels_present:
                level = "H2" # Default to H2 if H1 exists
            else:
                level = "H1" # Default to H1 if no levels assigned yet or no H1

        outline.append({
            "level": level,
            "text": span["text"],
            "page": span["page"] + 1 # Page numbers are 0-indexed in fitz, 1-indexed for output
        })

    return {
        "title": title,
        "outline": outline
    }

def process_all_pdfs():
    # Ensure output directory exists
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

   


    # Process all PDF files in the input directory
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".pdf"):
            input_path = os.path.join(INPUT_DIR, filename)
            output_filename = os.path.splitext(filename)[0] + ".json"
            output_path = os.path.join(OUTPUT_DIR, output_filename)

            print(f"🔍 Processing: {filename}")
            try:
                result = extract_outline(input_path)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"✅ Saved outline to: {output_filename}")
            except Exception as e:
                print(f"❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    process_all_pdfs()