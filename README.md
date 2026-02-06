# Schema Vector Database Query Interface

A simple and intuitive web interface for uploading database schema files to a vector database and querying them using natural language.

## Features

- **📁 Upload Schema Files**: Upload multiple schema files (SQL, text, JSON, etc.) that get processed and stored in a vector database
- **🔍 Query Schema**: Search your schema using natural language queries
- **🤖 NL2SQL**: Generate SQL queries from natural language questions using AI
- **🚀 Sequential Workflow**: Run all three steps in sequence from a single interface - upload files, query schema, and generate SQL automatically

## Setup

### Prerequisites

- Python 3.7 or higher
- n8n workflow running (with webhooks configured)
- Flask and requests libraries

### Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the project root:
```bash
# Copy the example file
cp .env.example .env
```

3. Edit the `.env` file and set your n8n webhook URL:
```env
N8N_BASE_URL=http://your-n8n-instance:5678/webhook
```

   **Note**: Replace `http://your-n8n-instance:5678/webhook` with your actual n8n instance URL.
   
   For example:
   - Local n8n: `http://localhost:5678/webhook`
   - Cloud n8n: `https://your-instance.app.n8n.cloud/webhook`
   - Self-hosted: `http://your-domain.com/webhook`

4. Run the Flask application:
```bash
python app.py
```

5. Open your browser and navigate to:
```
http://localhost:5000
```

## Configuration

### Environment Variables

Create a `.env` file in the project root with:

- `N8N_BASE_URL`: Base URL for your n8n webhooks (default: `http://localhost:5678/webhook`)

The application uses `python-dotenv` to load these variables automatically from the `.env` file.

### n8n Webhook Endpoints

The application expects the following n8n webhook endpoints:

1. **Files to Schema**: `/webhook/files-to-schema` (POST)
   - Accepts multipart/form-data with files
   - Processes and stores schema files in vector database

2. **Schema Query**: `/webhook/schema-query` (POST)
   - Accepts JSON with `query`, `sql`, or `text` field
   - Returns relevant schema information from vector database

3. **NL2SQL**: `/webhook/nl2sql` (POST)
   - Accepts JSON with `query`, `question`, or `text` field
   - Optional: `schema_hint` for better context
   - Returns generated SQL query

## Usage

### Upload Schema Files

1. Click "Choose files" or drag and drop schema files
2. Select one or more files (SQL, text, JSON, CSV, etc.)
3. Click "Upload to Vector Database"
4. Wait for confirmation that files were processed

### Query Schema

1. Enter a natural language question about your schema
2. Examples:
   - "What tables are related to sales?"
   - "Show me the product schema"
   - "What columns does the users table have?"
3. Click "Search Schema"
4. View the relevant schema information returned

### Generate SQL from Natural Language

1. Enter a question that requires SQL
2. Examples:
   - "Show me the total sales amount for today"
   - "Count the total number of active products"
   - "Calculate weekly growth percentage"
3. (Optional) Add a schema hint for better context
4. Click "Generate SQL"
5. Review the generated SQL query and execution status

### Complete Sequential Workflow

1. Use the **"Complete Workflow (Sequential)"** section at the top
2. Fill in any or all of the three steps:
   - **Step 1**: Upload schema files (optional)
   - **Step 2**: Query schema (optional)
   - **Step 3**: Generate SQL (optional)
3. Click **"Run Complete Workflow"**
4. All provided steps will execute in sequence automatically
5. View results for each step as they complete

## Project Structure

```
.
├── app.py                 # Flask backend application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── templates/
│   └── index.html        # Main HTML template
└── static/
    ├── style.css         # CSS styling
    └── script.js         # Frontend JavaScript
```

## API Endpoints

### `POST /api/upload-schema`
Upload schema files to the vector database.

**Request**: multipart/form-data with `files[]` field

**Response**:
```json
{
  "success": true,
  "message": "Successfully uploaded 2 file(s) to vector database",
  "data": {...}
}
```

### `POST /api/query-schema`
Query the schema using natural language.

**Request**:
```json
{
  "query": "What tables are related to sales?"
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "results": [...],
    "count": 5
  }
}
```

### `POST /api/nl2sql`
Generate SQL from natural language.

**Request**:
```json
{
  "query": "Show me the total sales amount for today",
  "schema_hint": "schema: retail_erp, main tables: sales"
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "status": "OK",
    "sql": "SELECT SUM(amount) FROM sales WHERE DATE(created_at) = CURRENT_DATE",
    "can_execute": true
  }
}
```

### `POST /api/workflow`
Execute all three steps in sequence.

**Request**: multipart/form-data
- `files[]`: (optional) Schema files to upload
- `json_data`: JSON string containing:
  - `query`: (optional) Schema query
  - `nl2sql_query`: (optional) NL2SQL query
  - `schema_hint`: (optional) Schema hint for NL2SQL

**Response**:
```json
{
  "success": true,
  "step1_upload": {
    "success": true,
    "message": "Successfully uploaded 2 file(s)"
  },
  "step2_query": {
    "success": true,
    "data": {...}
  },
  "step3_nl2sql": {
    "success": true,
    "data": {
      "status": "OK",
      "sql": "SELECT ..."
    }
  },
  "errors": []
}
```

## Troubleshooting

### Connection Issues

If you get connection errors:
1. Verify your n8n instance is running
2. Check that webhook URLs are correct
3. Ensure n8n webhooks are activated
4. Check firewall/network settings

### File Upload Issues

- Maximum file size: 16MB per file
- Supported formats: SQL, TXT, MD, JSON, CSV
- Ensure files contain valid schema information

### Query Issues

- Make sure schema files have been uploaded first
- Use clear, specific natural language queries
- For NL2SQL, provide schema hints for better results

## License

This project is provided as-is for use with your n8n workflow.

