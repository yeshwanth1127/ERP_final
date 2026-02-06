# Data Flow and Test Case

## 1. Data Flow

All data is **simulated in-process**. There is no database or n8n; everything is driven by `simulated_data.py` and in-memory state in `app.py`.

### 1.1 Single source of truth

```
simulated_data.py
├── SCHEMA_DDL          (hardcoded ERP DDL text)
├── TABLE_SCHEMAS        (table names → column list)
├── _SIMULATED_ROWS      (dict: table_name → list of row dicts)
│   ├── customers        (~30 rows)
│   ├── products         (~20 rows)
│   ├── orders           (~80 rows)
│   ├── order_items      (~80–320 rows)
│   ├── sales            (~120 rows)
│   └── inventory        (~20 rows)
└── Helpers
    ├── get_schema_text()      → full DDL string
    ├── get_schema_snippet(t)   → one table’s schema
    ├── query_simulated_data(sql, seed) → list of result rows (with variance)
    └── compute_analytics(period, metric, seed) → { summary, series }
```

Variance is applied via `seed` (or hash of query/period/metric) so the same “logical” request can return slightly different numbers (e.g. total revenue ±10%).

### 1.2 Request → response flow by feature

| User action | Frontend call | Backend route | Data flow |
|-------------|---------------|---------------|-----------|
| Open app | `GET /` | `index()` | Renders `index.html` (no data). |
| Reload check (debug) | `GET /api/reload-check` | `reload_check()` | Returns `{ started }` (server start time). |
| List documents | `GET /api/documents` | `list_documents()` | Reads `_simulated_documents` (in-memory list in app.py). |
| Delete document | `DELETE /api/documents/<id>` | `delete_document()` | Removes from `_simulated_documents`. |
| Upload files | `POST /api/upload-schema` (FormData) | `upload_schema()` | Ignores file content; appends one fake doc to `_simulated_documents`; returns success + `document_id`. |
| Query schema | `POST /api/query-schema` `{ query }` | `query_schema()` | Uses `get_schema_text()` / `get_schema_snippet()` from simulated_data; returns `{ data: { results: [{ content, score }], count } }`. |
| NL → SQL | `POST /api/nl2sql` `{ query, schema_hint? }` | `nl2sql()` | Uses `_simulated_nl2sql(query)` in app.py; returns `{ data: { sql, status, can_execute } }`. |
| Run SQL | `POST /api/execute-sql` `{ sql }` | `execute_sql()` | Calls `query_simulated_data(sql, seed=hash(sql))`; returns `{ success, data: { rows, summary } }`. |
| Run workflow | `POST /api/workflow` (FormData + json_data) | `sequential_workflow()` | Step 1: same as upload (add fake doc). Step 2: same as query-schema. Step 3: same as nl2sql. No external calls. |
| Clear vector store | `POST /api/clear-vector-store` | `clear_vector_store()` | No-op; returns success. |
| Open Dashboard | (tab click) | — | Frontend calls `/api/analytics` twice (revenue + orders). |
| Dashboard data | `GET /api/analytics?period=&metric=` | `analytics()` | Calls `compute_analytics(period, metric, seed)`; returns `{ summary: { totalRevenue, totalOrders, topRegion }, series: [{ date, value }, ...] }`. |

### 1.3 Flow diagram (high level)

```
Browser                    Flask (app.py)                 simulated_data.py
   |                             |                                |
   |-- GET / ------------------> | --> render index.html          |
   |                             |                                |
   |-- GET /api/documents -----> | --> _simulated_documents        |
   |<-- { documents } ----------- |                                |
   |                             |                                |
   |-- POST /api/upload-schema ->| --> append fake doc             |
   |<-- success, document_id --- |                                |
   |                             |                                |
   |-- POST /api/query-schema -->| --> get_schema_text() --------->| SCHEMA_DDL / TABLE_SCHEMAS
   |<-- { results } ------------- |<-- content, score               |
   |                             |                                |
   |-- POST /api/nl2sql -------->| --> _simulated_nl2sql(query)    |
   |<-- { sql, status } ---------|                                |
   |                             |                                |
   |-- POST /api/execute-sql --->| --> query_simulated_data(sql) ->| _SIMULATED_ROWS + variance
   |<-- { rows, summary } -------|<-- list of row dicts            |
   |                             |                                |
   |-- GET /api/analytics?period=| --> compute_analytics() ------->| _SIMULATED_ROWS, by_date
   |<-- { summary, series } ----- |<-- summary + time series       |
```

---

## 2. Whole Test Case (end-to-end)

Use this as a **manual test scenario** to verify the app and data flow.

### Prerequisites

- Flask app running: `python app.py` (or your run script) so the app is at `http://localhost:5000` (or your host/port).
- Browser; optional: DevTools Network tab to see API calls.

### Test steps

1. **Start and home**
   - Open `http://localhost:5000`.
   - **Expect:** Page loads with sidebar (Dashboard, Documents, Upload, Workflow, Query, NL → SQL) and Documents tab content (document dropdown, list, Clear vector store).

2. **Documents**
   - **Expect:** Document dropdown and list show at least “Sample ERP schema” and “Demo schema”.
   - Select a document (optional).
   - Click **Clear vector store**.
   - **Expect:** Success message; no errors. (Backend does nothing; it’s a no-op.)

3. **Upload (simulated)**
   - Go to **Upload** tab.
   - Choose one or more files (any type).
   - Click **Convert to Schema**.
   - **Expect:** Success message like “Successfully uploaded N file(s) to vector database”; document list refreshes and includes a new “Uploaded N file(s)” entry.

4. **Query schema**
   - Go to **Query** tab.
   - Enter: `What tables do I have?`
   - Click **Search**.
   - **Expect:** “Query Results” with schema content (e.g. list of tables or full DDL), relevance score.
   - Try: `orders` or `sales`.
   - **Expect:** Snippet for that table.

5. **NL → SQL**
   - Go to **NL → SQL** tab.
   - Enter: `Total sales` or `Show revenue by region`.
   - Click **Generate SQL**.
   - **Expect:** Generated SQL (e.g. `SELECT SUM(amount) FROM sales ...` or `SELECT region, SUM(amount) ...`), status OK, can execute.
   - Click **Run SQL** (if shown).
   - **Expect:** Execution result with rows/summary (e.g. `total` or `region`/`total`), no 404/500.

6. **Workflow**
   - Go to **Workflow** tab.
   - Optionally select a document and/or add files.
   - In **Query** put: `What tables exist?`
   - In **NL → SQL** put: `Count of orders`.
   - Click **Run workflow**.
   - **Expect:** Step 1 (Upload) optional success if files were added; Step 2 (Schema Query) success with schema; Step 3 (NL2SQL) success with SQL. No n8n/network errors.

7. **Dashboard**
   - Go to **Dashboard** tab.
   - **Expect:** KPI cards show Total Revenue (e.g. ₹XX,XXX), Total Orders (number), Top Region (e.g. North/South). Two charts: “Revenue over time” (line), “Orders over time” (bar).
   - Change **Period** to Week or Quarter; **Expect:** Data refreshes, numbers/series can change (variance).
   - Change **Metric** and/or click **Refresh**; **Expect:** Data refreshes again.

8. **Delete document**
   - Go back to **Documents**.
   - Click **Delete** on one of the uploaded documents.
   - **Expect:** Document disappears from list; no error.

### Expected data behavior (summary)

- **Schema / query:** Always from `simulated_data` (DDL + table snippets); no real vector DB.
- **Upload / documents / clear:** Only in-memory list in `app.py`; upload adds a fake doc, clear is no-op.
- **NL2SQL:** SQL is generated in app from query keywords; execution uses `query_simulated_data()` over simulated rows.
- **Dashboard:** Numbers and series come from `compute_analytics()` over the same simulated rows; different `period`/`metric` (and seed) give different values.

### Negative / edge checks (optional)

- **Query schema** with empty body → 400 “Query is required”.
- **NL2SQL** with empty query → 400 “Query is required”.
- **Execute SQL** with empty `sql` → 400 “No SQL provided”.
- **Upload** with no files selected → 400 “No files selected”.

---

## 3. Quick reference: API contract

| Endpoint | Method | Request | Success response (key fields) |
|----------|--------|---------|--------------------------------|
| `/api/reload-check` | GET | — | `{ started: number }` |
| `/api/documents` | GET | — | `{ documents: [{ id, name, created_at }] }` |
| `/api/documents/<id>` | DELETE | — | `{ success: true }` |
| `/api/upload-schema` | POST | FormData `files[]` | `{ success, message, data: { document_id } }` |
| `/api/query-schema` | POST | JSON `{ query }` | `{ success, data: { results: [{ content, score }], count } }` |
| `/api/nl2sql` | POST | JSON `{ query, schema_hint? }` | `{ success, data: { sql, status, can_execute } }` |
| `/api/execute-sql` | POST | JSON `{ sql }` | `{ success, data: { rows, summary } }` |
| `/api/workflow` | POST | FormData + `json_data` (query, nl2sql_query, schema_hint?, document_id?) | `{ success, step1_upload?, step2_query?, step3_nl2sql?, errors }` |
| `/api/clear-vector-store` | POST | — | `{ success, message }` |
| `/api/analytics` | GET | Query `period`, `metric` | `{ summary: { totalRevenue, totalOrders, topRegion }, series: [{ date, value }] }` |

This document describes the **data flow** and the **full manual test case** for the simulated ERP app.
