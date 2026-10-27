-- Graph schema (CONTRACT with Pakhi: a change here is a CONTRACT CHANGE). Same two tables for graph_ct and graph_syn.
-- edges.kind: 'calls' (one row PER CALL SITE; meta {"file","line","args":[[ident,...],...]})
--             'has_field_of_type' (type -> field, and field -> type when the field's type is a known struct)
--             'taint_reaches' (added later by the taint pass)
CREATE TABLE nodes (
  id INTEGER PRIMARY KEY,
  kind TEXT,        -- 'function' | 'type' | 'field'
  name TEXT,
  file TEXT,        -- path relative to sqlite-src (NULL for external/boundary functions)
  line INTEGER,
  signature TEXT,
  end_line INTEGER,
  usr TEXT UNIQUE,  -- Clang unique symbol id: keeps two static functions with the same name apart
  in_scope INTEGER, -- 1 = defined in one of the five core files, 0 = ring-1 / header / external
  meta TEXT         -- JSON: params, is_external, graph_source, assigns, indirect_calls
);
CREATE TABLE edges (
  src_id INTEGER, dst_id INTEGER,
  kind TEXT,
  meta TEXT,
  FOREIGN KEY(src_id) REFERENCES nodes(id),
  FOREIGN KEY(dst_id) REFERENCES nodes(id)
);
CREATE INDEX idx_edges_src ON edges(src_id, kind);
CREATE INDEX idx_edges_dst ON edges(dst_id, kind);
CREATE INDEX idx_nodes_name ON nodes(name);
