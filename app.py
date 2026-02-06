from flask import Flask, render_template, request, jsonify
import os
import json
import time
import uuid
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from simulated_data import (
    get_schema_text,
    get_schema_snippet,
    get_simulated_rows,
    query_simulated_data,
    compute_analytics,
    TABLE_SCHEMAS,
)

# Used by /api/reload-check so the frontend can detect server restarts (debug mode)
_APP_STARTED = time.time()

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# In-memory simulated document list (for UI consistency)
_simulated_documents = [
    {'id': 'sim-1', 'name': 'Sample ERP schema', 'created_at': '2025-01-15T10:00:00'},
    {'id': 'sim-2', 'name': 'Demo schema', 'created_at': '2025-02-01T09:00:00'},
]


@app.route('/')
def index():
    """Render the main UI page"""
    return render_template('index.html')


@app.route('/api/reload-check', methods=['GET'])
def reload_check():
    """Return server start time so debug frontend can reload when server restarts."""
    return jsonify({'started': _APP_STARTED})


@app.route('/api/upload-schema', methods=['POST'])
def upload_schema():
    """Simulated: always succeed and optionally add a fake document."""
    try:
        files = request.files.getlist('files[]') if 'files[]' in request.files else []
        if not files or (files and files[0].filename == ''):
            return jsonify({'success': False, 'error': 'No files selected'}), 400
        n = len([f for f in files if f and f.filename])
        doc_id = 'sim-' + str(uuid.uuid4())[:8]
        _simulated_documents.append({
            'id': doc_id,
            'name': f'Uploaded {n} file(s)',
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        })
        return jsonify({
            'success': True,
            'message': f'Successfully uploaded {n} file(s) to vector database',
            'data': {'status': 'processed', 'document_id': doc_id},
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/query-schema', methods=['POST'])
def query_schema():
    """Simulated: return schema snippets based on query keywords."""
    try:
        data = request.get_json() or {}
        query = (data.get('query') or data.get('sql') or data.get('text') or '').strip().lower()
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        content = get_schema_text()
        score = 0.95
        for table in TABLE_SCHEMAS:
            if table in query:
                content = get_schema_snippet(table)
                score = 0.92 + (hash(query) % 9) / 100
                break
        if 'table' in query and 'what' in query:
            content = '\n'.join(f'- {t}' for t in TABLE_SCHEMAS)
        return jsonify({
            'success': True,
            'data': {
                'results': [{'content': content, 'score': score}],
                'count': 1,
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _simulated_nl2sql(query):
    """Return simulated SQL and metadata based on query text (vary by hash)."""
    q = (query or '').strip().lower()
    h = hash(q) % 1000
    if 'total' in q or 'revenue' in q or 'sales' in q or 'sum' in q:
        return f"SELECT SUM(amount) AS total FROM sales WHERE sale_date >= CURRENT_DATE - INTERVAL '30 days';"
    if 'count' in q and ('order' in q or 'orders' in q):
        return "SELECT COUNT(*) AS order_count FROM orders WHERE status != 'cancelled';"
    if 'region' in q or 'by region' in q:
        return "SELECT region, SUM(amount) AS total FROM sales GROUP BY region ORDER BY total DESC;"
    if 'category' in q or 'by category' in q:
        return "SELECT p.category, SUM(oi.amount) AS total FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY p.category;"
    if 'customer' in q:
        return "SELECT c.name, c.region, COUNT(o.id) AS orders FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name, c.region;"
    if 'inventory' in q or 'stock' in q:
        return "SELECT p.name, i.quantity, i.warehouse FROM inventory i JOIN products p ON i.product_id = p.id WHERE i.quantity > 0;"
    return f"SELECT * FROM sales ORDER BY sale_date DESC LIMIT {10 + (h % 5)};"


@app.route('/api/nl2sql', methods=['POST'])
def nl2sql():
    """Simulated: return SQL and execution hint based on natural language query."""
    try:
        data = request.get_json() or {}
        query = data.get('query') or data.get('question') or data.get('text')
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        sql = _simulated_nl2sql(query)
        return jsonify({
            'success': True,
            'data': {
                'sql': sql,
                'status': 'OK',
                'can_execute': True,
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflow', methods=['POST'])
def sequential_workflow():
    """Simulated: run upload (optional), query schema, and nl2sql in sequence without n8n."""
    try:
        json_data_str = request.form.get('json_data')
        data = json.loads(json_data_str) if json_data_str else (request.get_json() if request.is_json else {})
        files = request.files.getlist('files[]') if 'files[]' in request.files else []
        results = {'step1_upload': None, 'step2_query': None, 'step3_nl2sql': None, 'success': False, 'errors': []}

        if files and files[0].filename:
            n = len([f for f in files if f and f.filename])
            doc_id = 'sim-' + str(uuid.uuid4())[:8]
            _simulated_documents.append({'id': doc_id, 'name': f'Uploaded {n} file(s)', 'created_at': time.strftime('%Y-%m-%dT%H:%M:%S')})
            results['step1_upload'] = {'success': True, 'message': f'Successfully uploaded {n} file(s)', 'data': {'document_id': doc_id}}

        query = data.get('query')
        if query:
            content = get_schema_text()
            for table in TABLE_SCHEMAS:
                if table in (query or '').lower():
                    content = get_schema_snippet(table)
                    break
            results['step2_query'] = {'success': True, 'data': {'results': [{'content': content, 'score': 0.95}], 'count': 1}}

        nl2sql_query = data.get('nl2sql_query')
        if nl2sql_query:
            sql = _simulated_nl2sql(nl2sql_query)
            results['step3_nl2sql'] = {'success': True, 'data': {'sql': sql, 'status': 'OK', 'can_execute': True}}

        results['success'] = bool(results['step1_upload'] or results['step2_query'] or results['step3_nl2sql'])
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'errors': [str(e)]}), 500


@app.route('/api/documents', methods=['GET'])
def list_documents():
    """Simulated: return in-memory document list."""
    return jsonify({'documents': _simulated_documents})


@app.route('/api/documents/<doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """Simulated: remove document from list (or no-op)."""
    global _simulated_documents
    _simulated_documents = [d for d in _simulated_documents if d.get('id') != doc_id]
    return jsonify({'success': True})


@app.route('/api/clear-vector-store', methods=['POST'])
def clear_vector_store():
    """Simulated: no-op, always success."""
    return jsonify({'success': True, 'message': 'Vector store cleared.'})


@app.route('/api/execute-sql', methods=['POST'])
def execute_sql():
    """Simulated: run SQL intent against in-memory data and return rows."""
    try:
        body = request.get_json() or {}
        sql = (body.get('sql') or '').strip()
        if not sql:
            return jsonify({'success': False, 'error': 'No SQL provided'}), 400
        seed = hash(sql) % 10000
        rows = query_simulated_data(sql, seed=seed)
        if not isinstance(rows, list):
            rows = [rows]
        return jsonify({'success': True, 'data': {'rows': rows, 'summary': f'{len(rows)} row(s)'}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analytics', methods=['GET'])
def analytics():
    """Simulated: return dashboard KPIs and time series with variance by period/metric."""
    period = request.args.get('period', 'month')
    metric = request.args.get('metric', 'revenue')
    seed = hash(period + metric) % 10000
    out = compute_analytics(period=period, metric=metric, seed=seed)
    return jsonify(out)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

