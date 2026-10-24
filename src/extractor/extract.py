import os, sqlite3, clang.cindex, subprocess

SQLITE_DIR = "sqlite-src"
DB_PATH = "src/graphs/graph_ct_v1.db"
TARGET_FILES = [("src/tokenize.c", "tokenize.c"), ("parse.c", "parse.c"), ("src/vdbe.c", "vdbe.c"), ("src/vdbeapi.c", "vdbeapi.c"), ("src/vdbemem.c", "vdbemem.c"), ("src/prepare.c", "prepare.c")]

def parse_code():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    index = clang.cindex.Index.create()
    res_dir = subprocess.check_output(["clang", "-print-resource-dir"]).decode("utf-8").strip()
    args = [f"-I{SQLITE_DIR}", f"-I{SQLITE_DIR}/src", f"-isystem{res_dir}/include"]

    usr_to_id = {}
    
    for row in cursor.execute("SELECT usr, id FROM nodes"):
        usr_to_id[row[0]] = row[1]

    for rel_path, display_name in TARGET_FILES:
        filepath = os.path.join(SQLITE_DIR, rel_path)
        if not os.path.exists(filepath): continue
            
        print(f"Extracting edges from: {display_name}...")
        tu = index.parse(filepath, args=args)
        
        def walk(node, current_caller_usr=None):
            if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.is_definition():
                current_caller_usr = node.get_usr()
            
            if node.kind == clang.cindex.CursorKind.CALL_EXPR and current_caller_usr:
                callee = node.referenced
                if callee and callee.get_usr():
                    callee_usr = callee.get_usr()
                    if current_caller_usr in usr_to_id and callee_usr in usr_to_id:
                        cursor.execute("""
                        INSERT INTO edges (src_id, dst_id, kind, meta)
                        VALUES (?, ?, 'calls', '{}')
                        """, (usr_to_id[current_caller_usr], usr_to_id[callee_usr]))

            for child in node.get_children():
                walk(child, current_caller_usr)

        walk(tu.cursor)
        conn.commit()
        
    conn.close()
    print("Edge extraction complete.")

if __name__ == "__main__":
    parse_code()
