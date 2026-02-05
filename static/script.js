// Tabs: left panel
document.querySelectorAll('.tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
        var tabId = this.getAttribute('data-tab');
        document.querySelectorAll('.tab').forEach(function(b) { b.classList.remove('active'); });
        document.querySelectorAll('.tab-pane').forEach(function(p) { p.classList.remove('active'); });
        this.classList.add('active');
        var pane = document.getElementById(tabId);
        if (pane) pane.classList.add('active');
    });
});

// Documents: list and select
const documentList = document.getElementById('documentList');
const documentSelect = document.getElementById('documentSelect');

function getSelectedDocumentId() {
    const sel = document.getElementById('documentSelect');
    return sel && sel.value ? sel.value : null;
}

async function loadDocuments() {
    const workflowDocSelect = document.getElementById('workflowDocumentSelect');
    try {
        const res = await fetch('/api/documents');
        const data = await res.json();
        const docs = data.documents || [];
        var optHtml = '<option value="">— None —</option>';
        docs.forEach(function(d) {
            optHtml += '<option value="' + escapeHtml(d.id) + '">' + escapeHtml(d.name) + ' (' + (d.created_at || '').slice(0, 19) + ')</option>';
        });
        if (documentSelect) {
            documentSelect.innerHTML = optHtml;
        }
        if (workflowDocSelect) {
            workflowDocSelect.innerHTML = optHtml;
        }
        documentList.innerHTML = '';
        if (docs.length === 0) {
            documentList.innerHTML = '<p class="document-list-empty">No documents yet. Use the Upload tab to add files.</p>';
        } else {
            docs.forEach(function(d) {
                var div = document.createElement('div');
                div.className = 'document-list-item';
                div.innerHTML = '<span class="doc-name">' + escapeHtml(d.name) + '</span><span class="doc-meta"><span class="doc-date">' + escapeHtml((d.created_at || '').slice(0, 19)) + '</span> <button type="button" class="btn-delete" data-doc-id="' + escapeHtml(d.id) + '" title="Delete">Delete</button></span>';
                documentList.appendChild(div);
            });
            documentList.querySelectorAll('.btn-delete').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var id = this.getAttribute('data-doc-id');
                    if (!id || !confirm('Remove this document?')) return;
                    fetch('/api/documents/' + encodeURIComponent(id), { method: 'DELETE' })
                        .then(function(r) { return r.json(); })
                        .then(function(data) {
                            if (data.success) loadDocuments();
                        });
                });
            });
        }
    } catch (e) {
        if (documentList) documentList.innerHTML = '<p class="document-list-empty">Could not load documents.</p>';
    }
}

// File Upload Handling
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const uploadForm = document.getElementById('uploadForm');
const uploadBtn = document.getElementById('uploadBtn');
const uploadResult = document.getElementById('uploadResult');
const uploadAction = document.getElementById('uploadAction');

let selectedFiles = [];

fileInput.addEventListener('change', (e) => {
    selectedFiles = Array.from(e.target.files);
    displayFileList();
});

function displayFileList() {
    fileList.innerHTML = '';
    if (selectedFiles.length === 0) {
        fileList.innerHTML = '<p style="color: #999; text-align: center;">No files selected — choose files above, then use the button that appears to convert to schema.</p>';
        if (uploadAction) uploadAction.style.display = 'none';
        return;
    }
    
    selectedFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <span class="file-item-name">📄 ${file.name}</span>
            <span class="file-item-size">${formatFileSize(file.size)}</span>
        `;
        fileList.appendChild(fileItem);
    });
    if (uploadAction) uploadAction.style.display = 'block';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (selectedFiles.length === 0) {
        showResult(uploadResult, 'error', 'Please select at least one file');
        return;
    }
    
    const formData = new FormData();
    selectedFiles.forEach(file => {
        formData.append('files[]', file);
    });
    
    setLoading(uploadBtn, true);
    hideResult(uploadResult);
    
    try {
        const response = await fetch('/api/upload-schema', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            showResult(uploadResult, 'success', data.message, data.data);
            selectedFiles = [];
            fileInput.value = '';
            displayFileList();
            if (uploadAction) uploadAction.style.display = 'none';
            await loadDocuments();
            if (data.data && data.data.document_id) {
                if (documentSelect) documentSelect.value = data.data.document_id;
                var wd = document.getElementById('workflowDocumentSelect');
                if (wd) wd.value = data.data.document_id;
            }
        } else {
            showResult(uploadResult, 'error', data.error || 'Upload failed');
        }
    } catch (error) {
        showResult(uploadResult, 'error', `Error: ${error.message}`);
    } finally {
        setLoading(uploadBtn, false);
    }
});

// Schema Query Handling
const queryForm = document.getElementById('queryForm');
const queryBtn = document.getElementById('queryBtn');
const queryResult = document.getElementById('queryResult');

queryForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const query = document.getElementById('queryInput').value.trim();
    if (!query) {
        showResult(queryResult, 'error', 'Please enter a query');
        return;
    }
    
    setLoading(queryBtn, true);
    hideResult(queryResult);
    
    const documentId = getSelectedDocumentId();
    try {
        const response = await fetch('/api/query-schema', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query, document_id: documentId || undefined })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showResult(queryResult, 'success', 'Query Results:', data.data);
        } else {
            showResult(queryResult, 'error', data.error || 'Query failed');
        }
    } catch (error) {
        showResult(queryResult, 'error', `Error: ${error.message}`);
    } finally {
        setLoading(queryBtn, false);
    }
});

// NL2SQL Handling
const nl2sqlForm = document.getElementById('nl2sqlForm');
const nl2sqlBtn = document.getElementById('nl2sqlBtn');
const nl2sqlResult = document.getElementById('nl2sqlResult');

nl2sqlForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const query = document.getElementById('nl2sqlInput').value.trim();
    if (!query) {
        showResult(nl2sqlResult, 'error', 'Please enter a question');
        return;
    }
    
    const schemaHint = document.getElementById('schemaHint').value.trim();
    
    const documentId = getSelectedDocumentId();
    setLoading(nl2sqlBtn, true);
    hideResult(nl2sqlResult);
    const executeResultEl = document.getElementById('executeResult');
    if (executeResultEl) { executeResultEl.className = 'result-message'; executeResultEl.innerHTML = ''; }
    
    try {
        const requestBody = { query, document_id: documentId || undefined };
        if (schemaHint) {
            requestBody.schema_hint = schemaHint;
        }
        
        const response = await fetch('/api/nl2sql', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showResult(nl2sqlResult, 'success', 'Generated SQL:', data.data, true);
            const sql = data.data?.sql || data.data?.data?.sql;
            if (sql && typeof sql === 'string') {
                renderRunSqlButton(nl2sqlResult, sql);
            }
        } else {
            showResult(nl2sqlResult, 'error', data.error || 'SQL generation failed');
        }
    } catch (error) {
        showResult(nl2sqlResult, 'error', `Error: ${error.message}`);
    } finally {
        setLoading(nl2sqlBtn, false);
    }
});

// Utility Functions
function setLoading(button, isLoading) {
    const btnText = button.querySelector('.btn-text');
    const btnLoader = button.querySelector('.btn-loader');
    
    if (isLoading) {
        button.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'inline-block';
    } else {
        button.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
    }
}

function showResult(element, type, message, data = null, isSQL = false) {
    element.className = `result-message show ${type}`;
    
    let content = `<strong>${message}</strong>`;
    
    if (data) {
        if (isSQL) {
            // Format SQL result
            const sql = data.sql || data.data?.sql || JSON.stringify(data, null, 2);
            const status = data.status || data.data?.status;
            const canExecute = data.can_execute || data.data?.can_execute;
            
            content += `<div class="result-content">`;
            if (status) {
                content += `<p><strong>Status:</strong> <span style="color: ${getStatusColor(status)}">${status}</span></p>`;
            }
            if (canExecute !== undefined) {
                content += `<p><strong>Can Execute:</strong> ${canExecute ? '✅ Yes' : '❌ No'}</p>`;
            }
            if (sql) {
                content += `<div class="sql-result">${escapeHtml(sql)}</div>`;
            } else {
                content += `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
            }
            content += `</div>`;
        } else {
            // Format regular result
            content += `<div class="result-content">${escapeHtml(JSON.stringify(data, null, 2))}</div>`;
        }
    }
    
    element.innerHTML = content;
    element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function getStatusColor(status) {
    switch(status?.toUpperCase()) {
        case 'OK': return '#28a745';
        case 'APPROVAL': return '#ffc107';
        case 'REJECTED': return '#dc3545';
        default: return '#333';
    }
}

function hideResult(element) {
    element.className = 'result-message';
    element.innerHTML = '';
}

function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderRunSqlButton(container, sql) {
    let wrap = container.querySelector('.run-sql-wrap');
    if (!wrap) {
        wrap = document.createElement('div');
        wrap.className = 'run-sql-wrap';
        container.appendChild(wrap);
    }
    wrap.innerHTML = '<button type="button" class="btn btn-secondary btn-run-sql">Run SQL</button>';
    wrap.querySelector('button').onclick = () => executeSql(sql);
}

async function executeSql(sql) {
    const el = document.getElementById('executeResult');
    if (!el) return;
    el.className = 'result-message show info';
    el.innerHTML = '<strong>Running SQL…</strong>';
    try {
        const res = await fetch('/api/execute-sql', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sql })
        });
        const data = await res.json();
        el.className = 'result-message show ' + (data.success ? 'success' : 'error');
        el.innerHTML = '<strong>' + (data.success ? 'Execution result' : 'Execution failed') + '</strong>' +
            (data.data ? '<div class="result-content">' + escapeHtml(JSON.stringify(data.data, null, 2)) + '</div>' : '') +
            (data.error ? '<p>' + escapeHtml(data.error) + '</p>' : '');
    } catch (e) {
        el.className = 'result-message show error';
        el.innerHTML = '<strong>Error</strong><p>' + escapeHtml(e.message) + '</p>';
    }
}

// Sequential Workflow Handling
const workflowFileInput = document.getElementById('workflowFileInput');
const workflowFileList = document.getElementById('workflowFileList');
const workflowForm = document.getElementById('workflowForm');
const workflowBtn = document.getElementById('workflowBtn');
const workflowResult = document.getElementById('workflowResult');
const workflowProgress = document.getElementById('workflowProgress');

let workflowFiles = [];

const workflowUploadAction = document.getElementById('workflowUploadAction');
const workflowConvertBtn = document.getElementById('workflowConvertBtn');

workflowFileInput.addEventListener('change', (e) => {
    workflowFiles = Array.from(e.target.files);
    displayWorkflowFileList();
});

function displayWorkflowFileList() {
    workflowFileList.innerHTML = '';
    if (workflowFiles.length === 0) {
        workflowFileList.innerHTML = '<p style="color: #999; text-align: center;">No files selected (optional)</p>';
        if (workflowUploadAction) workflowUploadAction.style.display = 'none';
        return;
    }
    
    workflowFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <span class="file-item-name">📄 ${file.name}</span>
            <span class="file-item-size">${formatFileSize(file.size)}</span>
        `;
        workflowFileList.appendChild(fileItem);
    });
    if (workflowUploadAction) workflowUploadAction.style.display = 'block';
}

// Convert to Schema (Step 1 only) in workflow section
if (workflowConvertBtn) {
    workflowConvertBtn.addEventListener('click', async () => {
        if (workflowFiles.length === 0) return;
        const formData = new FormData();
        workflowFiles.forEach(file => formData.append('files[]', file));
        setLoading(workflowConvertBtn, true);
        hideWorkflowResult();
        try {
            const response = await fetch('/api/upload-schema', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.success) {
                showWorkflowResult('success', data.message, `<div class="result-content">${escapeHtml(JSON.stringify(data.data, null, 2))}</div>`);
                workflowFiles = [];
                workflowFileInput.value = '';
                displayWorkflowFileList();
                if (workflowUploadAction) workflowUploadAction.style.display = 'none';
                loadDocuments();
                if (data.data && data.data.document_id) {
                    if (documentSelect) documentSelect.value = data.data.document_id;
                    var wd = document.getElementById('workflowDocumentSelect');
                    if (wd) wd.value = data.data.document_id;
                }
            } else {
                showWorkflowResult('error', data.error || 'Convert failed');
            }
        } catch (err) {
            showWorkflowResult('error', `Error: ${err.message}`);
        } finally {
            setLoading(workflowConvertBtn, false);
        }
    });
}

workflowForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const query = document.getElementById('workflowQueryInput').value.trim();
    const nl2sqlQuery = document.getElementById('workflowNL2SQLInput').value.trim();
    const schemaHint = document.getElementById('workflowSchemaHint').value.trim();
    
    // At least one step must be provided
    if (workflowFiles.length === 0 && !query && !nl2sqlQuery) {
        showWorkflowResult('error', 'Please provide at least one step: files, query, or NL2SQL query');
        return;
    }
    
    setLoading(workflowBtn, true);
    hideWorkflowResult();
    updateWorkflowProgress('Starting workflow...');
    
    try {
        // Prepare FormData for file upload
        const formData = new FormData();
        
        // Add files if provided
        workflowFiles.forEach(file => {
            formData.append('files[]', file);
        });
        
        // Add JSON data
        const jsonData = {};
        if (query) jsonData.query = query;
        if (nl2sqlQuery) jsonData.nl2sql_query = nl2sqlQuery;
        if (schemaHint) jsonData.schema_hint = schemaHint;
        const workflowDocId = document.getElementById('workflowDocumentSelect') && document.getElementById('workflowDocumentSelect').value;
        if (workflowDocId) jsonData.document_id = workflowDocId;
        
        // Convert JSON to string and append
        formData.append('json_data', JSON.stringify(jsonData));
        
        // Send to workflow endpoint
        const response = await fetch('/api/workflow', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        // Display results
        let resultHtml = '<div class="workflow-results">';
        
        if (data.step1_upload) {
            updateWorkflowProgress('✅ Step 1 (Upload) completed');
            resultHtml += `<div class="workflow-step-result">
                <h4>Step 1: Upload Files</h4>
                <p class="${data.step1_upload.success ? 'success' : 'error'}">
                    ${data.step1_upload.success ? '✅ ' + data.step1_upload.message : '❌ ' + data.step1_upload.error}
                </p>
            </div>`;
        }
        
        if (data.step2_query) {
            updateWorkflowProgress('✅ Step 2 (Schema Query) completed');
            resultHtml += `<div class="workflow-step-result">
                <h4>Step 2: Schema Query</h4>
                <p class="${data.step2_query.success ? 'success' : 'error'}">
                    ${data.step2_query.success ? '✅ Query successful' : '❌ ' + data.step2_query.error}
                </p>
                ${data.step2_query.success ? `<div class="result-content">${escapeHtml(JSON.stringify(data.step2_query.data, null, 2))}</div>` : ''}
            </div>`;
        }
        
        if (data.step3_nl2sql) {
            updateWorkflowProgress('✅ Step 3 (NL2SQL) completed');
            const sqlData = data.step3_nl2sql.data;
            const sql = sqlData?.sql || sqlData?.data?.sql || JSON.stringify(sqlData, null, 2);
            const status = sqlData?.status || sqlData?.data?.status;
            const canExecute = sqlData?.can_execute || sqlData?.data?.can_execute;
            
            resultHtml += `<div class="workflow-step-result">
                <h4>Step 3: NL2SQL Generation</h4>
                <p class="${data.step3_nl2sql.success ? 'success' : 'error'}">
                    ${data.step3_nl2sql.success ? '✅ SQL generated' : '❌ ' + data.step3_nl2sql.error}
                </p>`;
            
            if (data.step3_nl2sql.success) {
                resultHtml += `<div class="result-content">`;
                if (status) {
                    resultHtml += `<p><strong>Status:</strong> <span style="color: ${getStatusColor(status)}">${status}</span></p>`;
                }
                if (canExecute !== undefined) {
                    resultHtml += `<p><strong>Can Execute:</strong> ${canExecute ? '✅ Yes' : '❌ No'}</p>`;
                }
                if (sql) {
                    resultHtml += `<div class="sql-result">${escapeHtml(sql)}</div>`;
                }
                resultHtml += `</div>`;
            }
            resultHtml += `</div>`;
        }
        
        resultHtml += '</div>';
        
        if (data.errors && data.errors.length > 0) {
            resultHtml += `<div class="workflow-errors">
                <h4>Errors:</h4>
                <ul>${data.errors.map(err => `<li>${escapeHtml(err)}</li>`).join('')}</ul>
            </div>`;
        }
        
        showWorkflowResult(data.success ? 'success' : 'error', 
            data.success ? 'Workflow completed successfully!' : 'Workflow completed with errors', 
            resultHtml);
        
    } catch (error) {
        showWorkflowResult('error', `Error: ${error.message}`);
    } finally {
        setLoading(workflowBtn, false);
        updateWorkflowProgress('');
    }
});

function showWorkflowResult(type, message, html = '') {
    workflowResult.className = `result-message show ${type}`;
    workflowResult.innerHTML = `<strong>${message}</strong>${html}`;
    workflowResult.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideWorkflowResult() {
    workflowResult.className = 'result-message';
    workflowResult.innerHTML = '';
}

function updateWorkflowProgress(message) {
    if (message) {
        workflowProgress.innerHTML = `<p class="progress-text">${message}</p>`;
        workflowProgress.style.display = 'block';
    } else {
        workflowProgress.style.display = 'none';
        workflowProgress.innerHTML = '';
    }
}

// Clear vector store (Documents tab)
var clearVectorBtn = document.getElementById('clearVectorBtn');
var clearVectorResult = document.getElementById('clearVectorResult');
if (clearVectorBtn) {
    clearVectorBtn.addEventListener('click', async function() {
        if (!confirm('Clear all schema from the vector store? You can re-upload to repopulate.')) return;
        clearVectorResult.className = 'result-message';
        clearVectorResult.innerHTML = '';
        clearVectorBtn.disabled = true;
        try {
            var res = await fetch('/api/clear-vector-store', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
            var data = await res.json();
            clearVectorResult.className = 'result-message show ' + (data.success ? 'success' : 'error');
            clearVectorResult.innerHTML = '<strong>' + (data.success ? data.message || 'Vector store cleared.' : (data.error || 'Failed')) + '</strong>';
        } catch (e) {
            clearVectorResult.className = 'result-message show error';
            clearVectorResult.innerHTML = '<strong>Error: ' + escapeHtml(e.message) + '</strong>';
        }
        clearVectorBtn.disabled = false;
    });
}

// Initialize workflow file list and load documents
displayWorkflowFileList();
loadDocuments();

