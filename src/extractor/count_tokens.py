import tiktoken
import os

# Core files + ring-1 (prepare.c) + generated parse.c
target_files = [
    "sqlite-src/tokenize.c",
    "sqlite-src/parse.c",
    "sqlite-src/vdbe.c",
    "sqlite-src/vdbeapi.c",
    "sqlite-src/vdbemem.c",
    "sqlite-src/prepare.c"
]

enc = tiktoken.encoding_for_model("gpt-4o")
total_tokens = 0

print("--- Token Count Breakdown ---")
for filepath in target_files:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            tokens = len(enc.encode(content))
            total_tokens += tokens
            print(f"{filepath}: {tokens:,} tokens")
    else:
        print(f"Warning: {filepath} not found. Did the build finish?")

print(f"\nTotal Context Size: {total_tokens:,} tokens")
