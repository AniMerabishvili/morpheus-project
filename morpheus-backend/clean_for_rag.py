import re
import os
import sys

def clean_book_text(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    if not text.strip():
        return

    # 1. ARTIFACT REPAIR (First-Person Missing Pronoun Fixes)
    # Safely restores dropped 'I' pronouns without breaking existing formatting
    text = re.sub(r'\.\s+(call|have|am|would|feel|can|must)\b', r'. I \1', text)
    text = re.sub(r'\n\s*(call|have|am|would|feel|can|must)\b', r'\nI \1', text)

    # 2. LINE-BY-LINE STREAM SANITIZATION
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        cleaned_line = line.strip()
        
        # Keep empty spacing intact for context splitting
        if not cleaned_line:
            cleaned_lines.append("")
            continue
            
        # Clean structural indicators like paragraph counters [1] or [14] inline
        # Instead of dropping the line, we just strip the tag so the prose stays preserved!
        cleaned_line = re.sub(r'^\[\d+\]\s*', '', cleaned_line)

        # Skip isolated layout lines that are purely standalone page numbers or index numbers
        if re.match(r'^\[?\d+\]?$', cleaned_line):
            continue

        # Skip explicit Table of Contents leader dots or design separators (e.g., "_____")
        if re.search(r'\.{4,}', cleaned_line) or re.search(r'_{3,}', cleaned_line):
            continue

        cleaned_lines.append(cleaned_line)

    # Re-assemble the stabilized line stream
    text = "\n".join(cleaned_lines)

    # 3. GLOBAL TEXT COMPACTION
    text = re.sub(r'[†‡*]', '', text)  # Wipe explicit footnote anchors
    text = re.sub(r'\b[IVXLCDM]+\b', '', text)  # Remove stray structural roman numerals
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)  # Join hyphen splits across text layout lines
    text = re.sub(r'\n{3,}', '\n\n', text)  # Collapse endless blank lines down to neat paragraph breaks
    text = re.sub(r' {2,}', ' ', text)  # Normalize multi-space layout indents

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text.strip())


def process_directory(directory_path):
    if not os.path.isdir(directory_path):
        print(f"Error: Target directory '{directory_path}' does not exist.")
        return

    output_dir = os.path.join(directory_path, "cleaned_output")
    os.makedirs(output_dir, exist_ok=True)

    txt_files = []
    for root, dirs, files in os.walk(directory_path):
        if "cleaned_output" in root:
            continue
        for file in files:
            if file.endswith('.txt') and not file.startswith('.'):
                txt_files.append(os.path.join(root, file))
    
    if not txt_files:
        print(f"❌ No valid target files found in '{directory_path}'.")
        return

    print(f"🔥 Found {len(txt_files)} file(s). Running safe-stream optimization...\n" + "-"*50)

    for file_path in txt_files:
        filename = os.path.basename(file_path)
        output_file_path = os.path.join(output_dir, f"cleaned_{filename}")
        try:
            clean_book_text(file_path, output_file_path)
            print(f"   Processed and saved safely -> {output_file_path}")
        except Exception as e:
            print(f"   ❌ Processing failed on {filename}. Error: {e}")


if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "books"
    process_directory(target_dir)