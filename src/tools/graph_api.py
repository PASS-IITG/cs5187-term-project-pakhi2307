import sqlite3
import os

DB_PATH = "src/graphs/graph_ct_v1.db"

def get_db_connection():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    return sqlite3.connect(DB_PATH)

def get_callers(target_function):
    """Returns a list of functions that call the target_function."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT DISTINCT src.name, src.file 
    FROM nodes dst 
    JOIN edges e ON dst.id = e.dst_id 
    JOIN nodes src ON e.src_id = src.id 
    WHERE dst.name = ? AND e.kind = 'calls'
    """
    cursor.execute(query, (target_function,))
    results = cursor.fetchall()
    conn.close()
    return [{"caller": row[0], "file": row[1]} for row in results]

def get_callees(source_function):
    """Returns a list of functions called by the source_function."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT DISTINCT dst.name, dst.file 
    FROM nodes src 
    JOIN edges e ON src.id = e.src_id 
    JOIN nodes dst ON e.dst_id = dst.id 
    WHERE src.name = ? AND e.kind = 'calls'
    """
    cursor.execute(query, (source_function,))
    results = cursor.fetchall()
    conn.close()
    return [{"callee": row[0], "file": row[1]} for row in results]

if __name__ == "__main__":
    # Quick test on a known SQLite function like sqlite3_prepare_v2
    print("Testing API on 'sqlite3_prepare_v2'...")
    callers = get_callers("sqlite3_prepare_v2")
    callees = get_callees("sqlite3_prepare_v2")
    
    print(f"Functions calling sqlite3_prepare_v2: {len(callers)}")
    print(f"Functions sqlite3_prepare_v2 calls: {len(callees)}")
    if callees:
        print("Sample callee:", callees[0])
