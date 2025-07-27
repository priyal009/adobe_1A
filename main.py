import fitz  # PyMuPDF
import json
import os
from collections import Counter

INPUT_DIR = "input"
OUTPUT_DIR = "output"

def extract_outline(pdf_path):
    doc = fitz.open(pdf_path)
    spans_data = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text or len(text.split()) > 8:  # Skip long paragraph lines
                        continue

                    spans_data.append({
                        "text": text,
                        "size": round(span["size"], 1),
                        "flags": span["flags"],
                        "font": span["font"],
                        "color": span["color"],
                        "page": page_num,
                        "block_lines": len(block["lines"]),
                        "line_spans": len(line["spans"])
                    })

    if not spans_data:
        return {"title": "Untitled Document", "outline": []}

    # Extract visual stats
    fonts = [s["font"] for s in spans_data]
    sizes = [s["size"] for s in spans_data]
    colors = [s["color"] for s in spans_data]

    common_font = Counter(fonts).most_common(1)[0][0]
    common_size = Counter(sizes).most_common(1)[0][0]
    common_color = Counter(colors).most_common(1)[0][0]

    candidate_headings = []

    for span in spans_data:
        score = 0
        flags = span["flags"]

        is_bold = (flags & 2) != 0
        is_italic = (flags & 1) != 0
        is_underlined = (flags & 8) != 0
        font_diff = span["font"] != common_font
        color_diff = span["color"] != common_color
        size_larger = span["size"] > common_size
        is_isolated = span["block_lines"] == 1 and span["line_spans"] == 1

        score += is_bold
        score += is_italic
        score += is_underlined
        score += font_diff
        score += color_diff
        score += size_larger
        score += is_isolated

        if score >= 2:
            candidate_headings.append({
                "text": span["text"],
                "size": span["size"],
                "page": span["page"]
            })

    # Fallback: if not enough candidates, include all visible spans
    if len(candidate_headings) <= 1:
        candidate_headings = [
            {
                "text": s["text"],
                "size": s["size"],
                "page": s["page"]
            } for s in spans_data if len(s["text"].split()) <= 8
        ]

    # Rank sizes for heading levels
    heading_sizes = [s["size"] for s in candidate_headings]
    size_counts = Counter(heading_sizes)
    ranked = sorted(size_counts.items(), key=lambda x: (-x[0], -x[1]))

    size_to_level = {}
    if ranked:
        size_to_level[ranked[0][0]] = "Title"
    if len(ranked) > 1:
        size_to_level[ranked[1][0]] = "H1"
    if len(ranked) > 2:
        size_to_level[ranked[2][0]] = "H2"
    if len(ranked) > 3:
        size_to_level[ranked[3][0]] = "H3"

    outline = []
    title = None

    for span in candidate_headings:
        level = size_to_level.get(span["size"])
        if level:
            if level == "Title" and not title:
                title = span["text"]
            else:
                outline.append({
                    "level": level,
                    "text": span["text"],
                    "page": span["page"]
                })

    return {
        "title": title if title else "Untitled Document",
        "outline": outline
    }

def process_all_pdfs():
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".pdf"):
            input_path = os.path.join(INPUT_DIR, filename)
            output_filename = os.path.splitext(filename)[0] + ".json"
            output_path = os.path.join(OUTPUT_DIR, output_filename)

            print(f"🔍 Processing: {filename}")
            result = extract_outline(input_path)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            print(f"✅ Saved outline to: {output_filename}")

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    process_all_pdfs()
