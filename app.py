from flask import Flask, render_template, request, jsonify, session
import requests
import os
import json
import time
import uuid
import sqlite3
import csv
import io
from datetime import timedelta
from glob import glob
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')
# Keep session so user sees their uploads as long as they use the same browser (effectively "forever")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=3650)  # ~10 years
app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema_erp.db')
# For auto-reload check in browser (changes when server restarts)
app.config['STARTED_AT'] = time.time()

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS document_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        ''')
        conn.commit()


def get_user_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        session.permanent = True
    return session['user_id']


def get_document_schema_text(doc_id, user_id):
    """Read all files for a document and return concatenated text (UTF-8)."""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT file_path FROM document_files WHERE document_id = ?',
            (doc_id,)
        ).fetchall()
    if not rows:
        return ''
    base = app.config['UPLOAD_FOLDER']
    parts = []
    for row in rows:
        path = row['file_path']
        full = os.path.join(base, path) if not os.path.isabs(path) else path
        if not os.path.normpath(full).startswith(os.path.normpath(base)):
            continue
        if not os.path.isfile(full):
            continue
        try:
            with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            name = os.path.basename(path)
            parts.append(f'-- from file: {name}\n{content}\n')
        except Exception:
            continue
    return '\n\n'.join(parts) if parts else ''


def convert_upload_to_schema_txt(files_with_content):
    """
    Convert uploaded file(s) to a single schema.txt content string.
    - CSV/XLSX: derive "Table: name. Columns: col1, col2, ..."
    - Other (e.g. .sql, .txt, .md, .json): use file content as-is (UTF-8).
    Returns one string to send to the webhook for embedding and storage.
    """
    parts = []
    for filename, content in files_with_content:
        if not content or not filename:
            continue
        fn_lower = filename.lower()
        try:
            if fn_lower.endswith('.csv'):
                text = content.decode('utf-8', errors='ignore')
                reader = csv.reader(io.StringIO(text))
                first_row = next(reader, None)
                table_name = os.path.splitext(os.path.basename(filename))[0].replace(' ', '_')
                if first_row:
                    columns = ', '.join(c.strip() for c in first_row if c and str(c).strip())
                    parts.append(f'-- from file: {filename}\nTable: {table_name}. Columns: {columns}.')
                else:
                    parts.append(f'-- from file: {filename}\n{text[:2000]}')
            elif fn_lower.endswith('.xlsx'):
                try:
                    import openpyxl
                except ImportError:
                    parts.append(f'-- from file: {filename}\n(Excel file: install openpyxl to derive schema)')
                    continue
                table_name = os.path.splitext(os.path.basename(filename))[0].replace(' ', '_')
                book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
                sheet = book.active
                first_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
                book.close()
                if first_row:
                    columns = ', '.join(str(c).strip() for c in first_row if c is not None and str(c).strip())
                    parts.append(f'-- from file: {filename}\nTable: {table_name}. Columns: {columns}.')
                else:
                    parts.append(f'-- from file: {filename}\nTable: {table_name}.')
            else:
                text = content.decode('utf-8', errors='ignore')
                parts.append(f'-- from file: {filename}\n{text}')
        except Exception:
            try:
                text = content.decode('utf-8', errors='ignore')
                parts.append(f'-- from file: {filename}\n{text[:5000]}')
            except Exception:
                continue
    return '\n\n'.join(parts) if parts else ''


# n8n webhook URLs - Load from .env file; ensure base ends with /webhook
_n8n_base = (os.getenv('N8N_BASE_URL') or 'http://localhost:5678/webhook').rstrip('/')
if not _n8n_base.endswith('/webhook'):
    _n8n_base = f"{_n8n_base}/webhook"
N8N_BASE_URL = _n8n_base
FILES_TO_SCHEMA_WEBHOOK = f"{N8N_BASE_URL}/files-to-schema"
SCHEMA_QUERY_WEBHOOK = f"{N8N_BASE_URL}/schema-query"
NL2SQL_WEBHOOK = f"{N8N_BASE_URL}/nl2sql"
EXECUTE_SQL_WEBHOOK = os.getenv('N8N_EXECUTE_SQL_WEBHOOK', '').strip() or None
CLEAR_VECTOR_WEBHOOK = os.getenv('N8N_CLEAR_VECTOR_WEBHOOK', '').strip() or None


# Ensure DB exists on first request
with app.app_context():
    init_db()


@app.route('/')
def index():
    """Render the main UI page"""
    return render_template('index.html', debug=app.debug)


@app.route('/api/clear-vector-store', methods=['POST'])
def clear_vector_store():
    """
    Clear the vector store (e.g. rag_schema_docs). Calls n8n webhook if N8N_CLEAR_VECTOR_WEBHOOK is set.
    The n8n workflow should run TRUNCATE TABLE rag_schema_docs (or equivalent).
    """
    if not CLEAR_VECTOR_WEBHOOK:
        return jsonify({
            'success': False,
            'error': 'Clear vector store is not configured. Set N8N_CLEAR_VECTOR_WEBHOOK in .env to an n8n webhook that runs TRUNCATE on rag_schema_docs.'
        }), 501
    try:
        response = requests.post(CLEAR_VECTOR_WEBHOOK, json={}, timeout=30)
        response.raise_for_status()
        result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'status': 'ok'}
        return jsonify({'success': True, 'message': 'Vector store cleared', 'data': result})
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/documents', methods=['GET'])
def list_documents():
    """List documents for the current user."""
    try:
        user_id = get_user_id()
        with get_db() as conn:
            rows = conn.execute(
                'SELECT id, name, created_at FROM documents WHERE user_id = ? ORDER BY created_at DESC',
                (user_id,)
            ).fetchall()
        documents = [{'id': r['id'], 'name': r['name'], 'created_at': r['created_at']} for r in rows]
        return jsonify({'success': True, 'documents': documents})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/documents/<document_id>', methods=['DELETE'])
def delete_document(document_id):
    """Delete a document and its files. Document must belong to current user."""
    try:
        user_id = get_user_id()
        with get_db() as conn:
            row = conn.execute(
                'SELECT id FROM documents WHERE id = ? AND user_id = ?',
                (document_id, user_id)
            ).fetchone()
            if not row:
                return jsonify({'success': False, 'error': 'Document not found'}), 404
            paths = conn.execute(
                'SELECT file_path FROM document_files WHERE document_id = ?',
                (document_id,)
            ).fetchall()
            for p in paths:
                full = os.path.join(app.config['UPLOAD_FOLDER'], p['file_path'])
                if os.path.isfile(full):
                    try:
                        os.remove(full)
                    except Exception:
                        pass
            doc_dir = os.path.join(app.config['UPLOAD_FOLDER'], user_id, document_id)
            if os.path.isdir(doc_dir):
                try:
                    for f in os.listdir(doc_dir):
                        os.remove(os.path.join(doc_dir, f))
                    os.rmdir(doc_dir)
                except Exception:
                    pass
            conn.execute('DELETE FROM document_files WHERE document_id = ?', (document_id,))
            conn.execute('DELETE FROM documents WHERE id = ?', (document_id,))
            conn.commit()
        return jsonify({'success': True, 'message': 'Document deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reload-check')
def reload_check():
    """In debug mode, returns server start time so the frontend can auto-refresh after restart."""
    if not app.debug:
        return jsonify({})
    return jsonify({'started': app.config.get('STARTED_AT', 0)})


@app.route('/api/upload-schema', methods=['POST'])
def upload_schema():
    """
    Save uploaded files for the current user, then forward to n8n webhook.
    Returns the new document id and name so the client can list/select it.
    """
    try:
        if 'files[]' not in request.files:
            return jsonify({'success': False, 'error': 'No files provided'}), 400
        
        files = request.files.getlist('files[]')
        if not files or not files[0].filename:
            return jsonify({'success': False, 'error': 'No files selected'}), 400
        
        user_id = get_user_id()
        doc_id = str(uuid.uuid4())
        upload_base = os.path.join(app.config['UPLOAD_FOLDER'], user_id, doc_id)
        os.makedirs(upload_base, exist_ok=True)
        
        # Build display name from first file
        first_name = secure_filename(files[0].filename) or 'Document'
        doc_name = os.path.splitext(first_name)[0]
        if len(files) > 1:
            doc_name = f'{doc_name} +{len(files) - 1} more'
        
        files_with_content = []
        with get_db() as conn:
            conn.execute(
                'INSERT INTO documents (id, user_id, name, created_at) VALUES (?, ?, ?, datetime("now"))',
                (doc_id, user_id, doc_name)
            )
            for file in files:
                if not file or not file.filename:
                    continue
                filename = secure_filename(file.filename)
                content = file.stream.read()
                files_with_content.append((file.filename, content))
                rel_path = os.path.join(user_id, doc_id, filename)
                abs_path = os.path.join(app.config['UPLOAD_FOLDER'], rel_path)
                with open(abs_path, 'wb') as out:
                    out.write(content)
                conn.execute(
                    'INSERT INTO document_files (document_id, filename, file_path) VALUES (?, ?, ?)',
                    (doc_id, filename, rel_path)
                )
            conn.commit()
        
        # Convert uploads to a single schema string and send as JSON (avoids multipart being stored as-is)
        schema_txt = convert_upload_to_schema_txt(files_with_content)
        if not schema_txt.strip():
            return jsonify({'success': False, 'error': 'Could not convert files to schema text'}), 400
        
        # Send schema as JSON so n8n stores only the text, not raw request body
        try:
            response = requests.post(
                FILES_TO_SCHEMA_WEBHOOK,
                json={'schema_txt': schema_txt},
                headers={'Content-Type': 'application/json'},
                timeout=120
            )
            response.raise_for_status()
            n8n_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'status': 'processed'}
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'Stored locally but n8n failed: {str(e)}'
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'Uploaded {len(files)} file(s) and added to vector database',
            'data': {'document_id': doc_id, 'name': doc_name, 'n8n': n8n_data}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/query-schema', methods=['POST'])
def query_schema():
    """
    Handle schema queries and forward to n8n webhook.
    Optional document_id: use that document's schema text as context (schema_hint).
    """
    try:
        data = request.get_json() or {}
        query = data.get('query') or data.get('sql') or data.get('text')
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        user_id = get_user_id()
        payload = {'query': query, 'sql': query, 'text': query}
        doc_id = data.get('document_id')
        if doc_id:
            # Verify document belongs to user
            with get_db() as conn:
                row = conn.execute(
                    'SELECT id FROM documents WHERE id = ? AND user_id = ?',
                    (doc_id, user_id)
                ).fetchone()
            if row:
                schema_hint = get_document_schema_text(doc_id, user_id)
                if schema_hint:
                    payload['schema_hint'] = schema_hint
        
        try:
            response = requests.post(SCHEMA_QUERY_WEBHOOK, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'data': response.text}
            return jsonify({'success': True, 'data': result})
        except requests.exceptions.RequestException as e:
            return jsonify({'success': False, 'error': f'Failed to query schema: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/nl2sql', methods=['POST'])
def nl2sql():
    """
    Handle NL2SQL queries and forward to n8n webhook.
    Optional document_id: use that document's schema text as schema_hint for better SQL.
    """
    try:
        data = request.get_json() or {}
        query = data.get('query') or data.get('question') or data.get('text')
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        request_body = {'query': query, 'question': query, 'text': query}
        if data.get('schema_hint'):
            request_body['schema_hint'] = data['schema_hint']
        
        user_id = get_user_id()
        doc_id = data.get('document_id')
        if doc_id:
            with get_db() as conn:
                row = conn.execute(
                    'SELECT id FROM documents WHERE id = ? AND user_id = ?',
                    (doc_id, user_id)
                ).fetchone()
            if row:
                schema_hint = get_document_schema_text(doc_id, user_id)
                if schema_hint:
                    existing = (request_body.get('schema_hint') or '').strip()
                    request_body['schema_hint'] = (existing + '\n\n' + schema_hint) if existing else schema_hint
        
        try:
            response = requests.post(NL2SQL_WEBHOOK, json=request_body, timeout=120)
            response.raise_for_status()
            result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'data': response.text}
            return jsonify({'success': True, 'data': result})
        except requests.exceptions.RequestException as e:
            return jsonify({'success': False, 'error': f'Failed to process NL2SQL: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/execute-sql', methods=['POST'])
def execute_sql():
    """
    Run a SQL command. Forwards to n8n if N8N_EXECUTE_SQL_WEBHOOK is set.
    """
    try:
        data = request.get_json() or {}
        sql = data.get('sql', '').strip()
        if not sql:
            return jsonify({'success': False, 'error': 'SQL is required'}), 400
        if not EXECUTE_SQL_WEBHOOK:
            return jsonify({
                'success': False,
                'error': 'SQL execution not configured. Set N8N_EXECUTE_SQL_WEBHOOK in .env to run SQL via n8n.'
            }), 501
        response = requests.post(EXECUTE_SQL_WEBHOOK, json={'sql': sql}, timeout=60)
        response.raise_for_status()
        result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'data': response.text}
        return jsonify({'success': True, 'data': result})
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflow', methods=['POST'])
def sequential_workflow():
    """
    Execute the complete workflow in sequence:
    1. Upload files to schema (files-to-schema)
    2. Query schema (schema-query)
    3. Generate SQL from natural language (nl2sql)
    """
    try:
        # Get JSON data from form data if present, otherwise from request.json
        json_data_str = request.form.get('json_data')
        if json_data_str:
            try:
                data = json.loads(json_data_str)
            except:
                data = {}
        else:
            data = request.get_json() if request.is_json else {}
        
        files = request.files.getlist('files[]') if 'files[]' in request.files else []
        
        results = {
            'step1_upload': None,
            'step2_query': None,
            'step3_nl2sql': None,
            'success': False,
            'errors': []
        }
        
        # Step 1: Convert files to schema.txt and send to webhook (embed and store)
        if files and files[0].filename:
            try:
                files_with_content = []
                for file in files:
                    if file and file.filename:
                        file.stream.seek(0)
                        content = file.stream.read()
                        files_with_content.append((file.filename, content))
                schema_txt = convert_upload_to_schema_txt(files_with_content)
                if not schema_txt.strip():
                    results['step1_upload'] = {'success': False, 'error': 'Could not convert files to schema text'}
                else:
                    response = requests.post(
                        FILES_TO_SCHEMA_WEBHOOK,
                        json={'schema_txt': schema_txt},
                        headers={'Content-Type': 'application/json'},
                        timeout=120
                    )
                    response.raise_for_status()
                    results['step1_upload'] = {
                        'success': True,
                        'message': f'Successfully converted {len(files_with_content)} file(s) to schema and stored',
                        'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else {'status': 'processed'}
                    }
            except Exception as e:
                error_msg = f'Step 1 (Upload) failed: {str(e)}'
                results['errors'].append(error_msg)
                results['step1_upload'] = {'success': False, 'error': error_msg}
        
        # Step 2: Query schema (if query provided)
        query = data.get('query') if data else None
        user_id = get_user_id()
        doc_id = data.get('document_id') if data else None
        schema_hint_from_doc = ''
        if doc_id and user_id:
            with get_db() as conn:
                row = conn.execute('SELECT id FROM documents WHERE id = ? AND user_id = ?', (doc_id, user_id)).fetchone()
            if row:
                schema_hint_from_doc = get_document_schema_text(doc_id, user_id)
        if query:
            try:
                payload = {'query': query, 'sql': query, 'text': query}
                if schema_hint_from_doc:
                    payload['schema_hint'] = schema_hint_from_doc
                response = requests.post(
                    SCHEMA_QUERY_WEBHOOK,
                    json=payload,
                    timeout=60
                )
                response.raise_for_status()
                schema_result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'data': response.text}
                results['step2_query'] = {
                    'success': True,
                    'data': schema_result
                }
            except Exception as e:
                error_msg = f'Step 2 (Schema Query) failed: {str(e)}'
                results['errors'].append(error_msg)
                results['step2_query'] = {'success': False, 'error': error_msg}
        
        # Step 3: Generate SQL from natural language (if nl2sql_query provided)
        nl2sql_query = data.get('nl2sql_query') if data else None
        if nl2sql_query:
            try:
                request_body = {
                    'query': nl2sql_query,
                    'question': nl2sql_query,
                    'text': nl2sql_query
                }
                
                if data and data.get('schema_hint'):
                    request_body['schema_hint'] = data['schema_hint']
                if schema_hint_from_doc:
                    request_body['schema_hint'] = (request_body.get('schema_hint') or '') + '\n\n' + schema_hint_from_doc
                
                response = requests.post(
                    NL2SQL_WEBHOOK,
                    json=request_body,
                    timeout=120
                )
                response.raise_for_status()
                sql_result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'data': response.text}
                results['step3_nl2sql'] = {
                    'success': True,
                    'data': sql_result
                }
            except Exception as e:
                error_msg = f'Step 3 (NL2SQL) failed: {str(e)}'
                results['errors'].append(error_msg)
                results['step3_nl2sql'] = {'success': False, 'error': error_msg}
        
        # Determine overall success
        results['success'] = len(results['errors']) == 0 and (
            results['step1_upload'] or results['step2_query'] or results['step3_nl2sql']
        )
        
        status_code = 200 if results['success'] else 500
        return jsonify(results), status_code
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Workflow error: {str(e)}',
            'errors': [str(e)]
        }), 500


def _extra_files():
    """Files to watch for auto-restart (templates + static)."""
    root = os.path.dirname(os.path.abspath(__file__))
    extra = []
    for folder in ('templates', 'static'):
        path = os.path.join(root, folder)
        if os.path.isdir(path):
            for f in glob(os.path.join(path, '**/*'), recursive=True):
                if os.path.isfile(f):
                    extra.append(f)
    return extra


if __name__ == '__main__':
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000,
        use_reloader=True,
        extra_files=_extra_files(),
    )

