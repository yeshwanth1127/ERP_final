from flask import Flask, render_template, request, jsonify
import requests
import os
import json
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# n8n webhook URLs - Load from .env file
N8N_BASE_URL = os.getenv('N8N_BASE_URL', 'http://localhost:5678/webhook')
FILES_TO_SCHEMA_WEBHOOK = f"{N8N_BASE_URL}/files-to-schema"
SCHEMA_QUERY_WEBHOOK = f"{N8N_BASE_URL}/schema-query"
NL2SQL_WEBHOOK = f"{N8N_BASE_URL}/nl2sql"


@app.route('/')
def index():
    """Render the main UI page"""
    return render_template('index.html')


@app.route('/api/upload-schema', methods=['POST'])
def upload_schema():
    """
    Handle schema file uploads and forward to n8n webhook
    """
    try:
        if 'files[]' not in request.files:
            return jsonify({'success': False, 'error': 'No files provided'}), 400
        
        files = request.files.getlist('files[]')
        
        if not files or files[0].filename == '':
            return jsonify({'success': False, 'error': 'No files selected'}), 400
        
        # Prepare files for n8n webhook
        files_data = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                files_data.append(
                    (file.filename, (file.filename, file.stream.read(), file.content_type))
                )
        
        # Forward to n8n webhook
        try:
            response = requests.post(
                FILES_TO_SCHEMA_WEBHOOK,
                files=files_data,
                timeout=120  # n8n processing might take time
            )
            response.raise_for_status()
            
            return jsonify({
                'success': True,
                'message': f'Successfully uploaded {len(files)} file(s) to vector database',
                'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else {'status': 'processed'}
            })
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'Failed to process files: {str(e)}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


@app.route('/api/query-schema', methods=['POST'])
def query_schema():
    """
    Handle schema queries and forward to n8n webhook
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query') or data.get('sql') or data.get('text')
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        # Forward to n8n schema query webhook
        try:
            response = requests.post(
                SCHEMA_QUERY_WEBHOOK,
                json={'query': query, 'sql': query, 'text': query},
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'data': response.text}
            
            return jsonify({
                'success': True,
                'data': result
            })
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'Failed to query schema: {str(e)}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


@app.route('/api/nl2sql', methods=['POST'])
def nl2sql():
    """
    Handle NL2SQL queries and forward to n8n webhook
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query') or data.get('question') or data.get('text')
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        # Prepare request body
        request_body = {
            'query': query,
            'question': query,
            'text': query
        }
        
        # Add optional schema hint if provided
        if 'schema_hint' in data:
            request_body['schema_hint'] = data['schema_hint']
        
        # Forward to n8n NL2SQL webhook
        try:
            response = requests.post(
                NL2SQL_WEBHOOK,
                json=request_body,
                timeout=120  # LLM processing might take time
            )
            response.raise_for_status()
            
            result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'data': response.text}
            
            return jsonify({
                'success': True,
                'data': result
            })
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'Failed to process NL2SQL query: {str(e)}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


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
        
        # Step 1: Upload files to schema (if files provided)
        if files and files[0].filename:
            try:
                files_data = []
                for file in files:
                    if file and file.filename:
                        filename = secure_filename(file.filename)
                        # Reset file stream position
                        file.stream.seek(0)
                        files_data.append(
                            (file.filename, (file.filename, file.stream.read(), file.content_type))
                        )
                
                if files_data:
                    response = requests.post(
                        FILES_TO_SCHEMA_WEBHOOK,
                        files=files_data,
                        timeout=120
                    )
                    response.raise_for_status()
                    results['step1_upload'] = {
                        'success': True,
                        'message': f'Successfully uploaded {len(files_data)} file(s)',
                        'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else {'status': 'processed'}
                    }
            except Exception as e:
                error_msg = f'Step 1 (Upload) failed: {str(e)}'
                results['errors'].append(error_msg)
                results['step1_upload'] = {'success': False, 'error': error_msg}
        
        # Step 2: Query schema (if query provided)
        query = data.get('query') if data else None
        if query:
            try:
                response = requests.post(
                    SCHEMA_QUERY_WEBHOOK,
                    json={'query': query, 'sql': query, 'text': query},
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
                
                # Add optional schema hint if provided
                if data and 'schema_hint' in data:
                    request_body['schema_hint'] = data['schema_hint']
                
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

