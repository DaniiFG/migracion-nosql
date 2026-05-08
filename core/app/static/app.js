// ============ TABS ============
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('content-' + tab.dataset.tab).classList.add('active');
    });
});

// ============ INIT ============
document.addEventListener('DOMContentLoaded', () => {
    checkConnections();
    loadSqlTables();
    loadMongoCollections();
    loadMappingInfo();
});

// ============ HEALTH CHECK ============
async function checkConnections() {
    try {
        const res = await fetch('/api/sql/tables');
        document.getElementById('sqlStatus').textContent = res.ok ? 'SQL Server ✅' : 'SQL Server ❌';
    } catch { document.getElementById('sqlStatus').textContent = 'SQL Server ❌'; }
    try {
        const res = await fetch('/api/mongo/collections');
        document.getElementById('mongoStatus').textContent = res.ok ? 'MongoDB ✅' : 'MongoDB ❌';
    } catch { document.getElementById('mongoStatus').textContent = 'MongoDB ❌'; }
}

// ============ SQL SERVER ============
let sqlTablesData = [];
async function loadSqlTables() {
    const container = document.getElementById('sqlTableList');
    container.innerHTML = '<div class="loading">Cargando...</div>';
    try {
        const res = await fetch('/api/sql/tables');
        const data = await res.json();
        sqlTablesData = data.tables;
        container.innerHTML = data.tables.map(t =>
            `<div class="table-item" onclick="loadSqlTableData('${t.schema_name}','${t.table_name}',this)">
                <span>${t.schema_name}.${t.table_name}</span>
                <span class="count">${t.row_count}</span>
            </div>`
        ).join('');
    } catch (e) { container.innerHTML = `<div class="loading" style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

async function loadSqlTableData(schema, table, el) {
    document.querySelectorAll('.table-item').forEach(i => i.classList.remove('active'));
    if (el) el.classList.add('active');
    document.getElementById('sqlTableTitle').textContent = `${schema}.${table}`;
    const container = document.getElementById('sqlTableData');
    container.innerHTML = '<div class="loading">Cargando datos...</div>';
    try {
        const res = await fetch(`/api/sql/table/${schema}/${table}?limit=100`);
        const data = await res.json();
        document.getElementById('sqlRowCount').textContent = `${data.total_rows} filas totales`;
        container.innerHTML = renderTable(data.columns, data.data);
    } catch (e) { container.innerHTML = `<div class="loading" style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

async function executeSqlQuery() {
    const q = document.getElementById('sqlQueryInput').value.trim();
    if (!q) return;
    const container = document.getElementById('sqlQueryResult');
    container.innerHTML = '<div class="loading">Ejecutando...</div>';
    try {
        const res = await fetch(`/api/sql/query?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (!res.ok) { container.innerHTML = `<div style="color:var(--accent-rose)">❌ ${data.detail}</div>`; return; }
        container.innerHTML = `<p style="color:var(--accent-emerald);margin-bottom:8px">✅ ${data.row_count} filas</p>` + renderTable(data.columns, data.data);
    } catch (e) { container.innerHTML = `<div style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

// ============ MONGODB ============
let mongoViewMode = 'table';
let currentMongoData = null;

async function loadMongoCollections() {
    const container = document.getElementById('mongoCollectionList');
    container.innerHTML = '<div class="loading">Cargando...</div>';
    try {
        const res = await fetch('/api/mongo/collections');
        const data = await res.json();
        if (data.collections.length === 0) {
            container.innerHTML = '<div class="placeholder"><p>No hay colecciones. Ejecuta la migración primero.</p></div>';
            return;
        }
        container.innerHTML = data.collections.map(c =>
            `<div class="table-item" onclick="loadMongoCollData('${c.collection}',this)">
                <span>${c.collection}</span>
                <span class="count">${c.document_count}</span>
            </div>`
        ).join('');
        // Update query select
        const sel = document.getElementById('mongoQueryCollection');
        sel.innerHTML = '<option value="">Seleccionar...</option>' + data.collections.map(c => `<option value="${c.collection}">${c.collection}</option>`).join('');
    } catch (e) { container.innerHTML = `<div class="loading" style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

async function loadMongoCollData(name, el) {
    document.querySelectorAll('#mongoCollectionList .table-item').forEach(i => i.classList.remove('active'));
    if (el) el.classList.add('active');
    document.getElementById('mongoCollTitle').textContent = name;
    const container = document.getElementById('mongoCollData');
    container.innerHTML = '<div class="loading">Cargando...</div>';
    document.getElementById('mongoViewToggle').style.display = 'inline-block';
    try {
        const res = await fetch(`/api/mongo/collection/${name}?limit=50`);
        currentMongoData = await res.json();
        document.getElementById('mongoDocCount').textContent = `${currentMongoData.total_documents} documentos`;
        renderMongoData();
    } catch (e) { container.innerHTML = `<div style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

function toggleMongoView() {
    mongoViewMode = mongoViewMode === 'table' ? 'json' : 'table';
    document.getElementById('mongoViewToggle').textContent = `Vista: ${mongoViewMode === 'table' ? 'Tabla' : 'JSON'}`;
    renderMongoData();
}

function renderMongoData() {
    const container = document.getElementById('mongoCollData');
    if (!currentMongoData || !currentMongoData.data.length) { container.innerHTML = '<div class="placeholder"><p>Sin documentos</p></div>'; return; }
    if (mongoViewMode === 'json') {
        container.innerHTML = `<div class="json-view">${JSON.stringify(currentMongoData.data, null, 2)}</div>`;
    } else {
        const flat = currentMongoData.data.map(d => flattenDoc(d));
        const cols = [...new Set(flat.flatMap(d => Object.keys(d)))];
        container.innerHTML = renderTable(cols, flat);
    }
}

function flattenDoc(obj, prefix = '') {
    const result = {};
    for (const [k, v] of Object.entries(obj)) {
        const key = prefix ? `${prefix}.${k}` : k;
        if (v && typeof v === 'object' && !Array.isArray(v)) {
            Object.assign(result, flattenDoc(v, key));
        } else if (Array.isArray(v)) {
            result[key] = `[${v.length} items]`;
        } else {
            result[key] = v;
        }
    }
    return result;
}

async function executeMongoQuery() {
    const col = document.getElementById('mongoQueryCollection').value;
    const filter = document.getElementById('mongoQueryFilter').value.trim() || '{}';
    if (!col) { alert('Selecciona una colección'); return; }
    const container = document.getElementById('mongoQueryResult');
    container.innerHTML = '<div class="loading">Ejecutando...</div>';
    try {
        const res = await fetch(`/api/mongo/query?collection=${col}&filter_json=${encodeURIComponent(filter)}&limit=50`);
        const data = await res.json();
        if (!res.ok) { container.innerHTML = `<div style="color:var(--accent-rose)">❌ ${data.detail}</div>`; return; }
        container.innerHTML = `<p style="color:var(--accent-emerald);margin-bottom:8px">✅ ${data.total_matches} coincidencias (mostrando ${data.returned})</p><div class="json-view">${JSON.stringify(data.data, null, 2)}</div>`;
    } catch (e) { container.innerHTML = `<div style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

// ============ MIGRATION ============
async function executeMigration() {
    if (!confirm('¿Ejecutar la migración completa (Saga) de SQL Server a MongoDB?')) return;
    const prog = document.getElementById('migrationProgress');
    prog.style.display = 'block';
    document.getElementById('migrationSteps').innerHTML = '<div class="loading">Ejecutando Saga de migración...</div>';
    try {
        const res = await fetch('/api/migration/execute', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            // Mostrar rollback si hubo fallo
            let errorHtml = `<div class="step-item error">❌ ${data.detail}</div>`;
            if (data.status && data.status.rollback_log && data.status.rollback_log.length) {
                errorHtml += '<h4 style="margin-top:12px;color:var(--accent-amber)">↩️ Rollback ejecutado:</h4>';
                errorHtml += data.status.rollback_log.map(r => `<div class="step-item" style="color:var(--accent-amber)">${r}</div>`).join('');
            }
            document.getElementById('migrationSteps').innerHTML = errorHtml;
            return;
        }
        const st = data.status;
        document.getElementById('progressBar').style.width = st.progress + '%';
        document.getElementById('migrationPercent').textContent = st.progress + '%';
        document.getElementById('migrationStep').textContent = st.current_step;
        
        // Mostrar pasos completados
        let stepsHtml = st.steps_completed.map(s => `<div class="step-item">${s}</div>`).join('');
        
        // Mostrar Saga log
        if (st.saga_log && st.saga_log.length) {
            stepsHtml += '<h4 style="margin-top:16px;color:var(--accent-indigo)">📋 Saga Log (Orquestación):</h4>';
            stepsHtml += st.saga_log.map(s => `<div class="step-item" style="color:var(--accent-cyan)">${s}</div>`).join('');
        }
        
        // Mostrar rollback si hubo
        if (st.rollback_log && st.rollback_log.length) {
            stepsHtml += '<h4 style="margin-top:12px;color:var(--accent-amber)">↩️ Rollback Log:</h4>';
            stepsHtml += st.rollback_log.map(r => `<div class="step-item" style="color:var(--accent-amber)">${r}</div>`).join('');
        }
        
        if (st.errors.length) {
            stepsHtml += st.errors.map(e => `<div class="step-item error">❌ ${e}</div>`).join('');
        }
        
        document.getElementById('migrationSteps').innerHTML = stepsHtml;
        loadMongoCollections();
        checkConnections();
    } catch (e) { alert('Error: ' + e.message); }
}

async function resetMigration() {
    if (!confirm('¿Eliminar todas las colecciones de MongoDB?')) return;
    try {
        await fetch('/api/migration/reset', { method: 'POST' });
        document.getElementById('migrationSteps').innerHTML = '<p class="text-muted">MongoDB reseteado. Ejecuta la migración nuevamente.</p>';
        document.getElementById('migrationProgress').style.display = 'none';
        loadMongoCollections();
    } catch (e) { alert('Error: ' + e.message); }
}

// ============ COMPARISON ============
async function loadComparisonSummary() {
    const container = document.getElementById('compareSummary');
    container.innerHTML = '<div class="loading">Comparando...</div>';
    try {
        const res = await fetch('/api/compare/summary');
        const data = await res.json();
        let html = `<div class="overall-status ${data.overall_match ? 'status-match' : 'status-mismatch'}">${data.status}</div>`;
        html += '<div class="compare-row header"><div>Entidad</div><div>SQL Server</div><div>Conteo</div><div>MongoDB</div><div>Conteo</div></div>';
        data.comparisons.forEach(c => {
            html += `<div class="compare-row">
                <div><strong>${c.entity}</strong></div>
                <div style="font-size:.78rem;color:var(--text-muted)">${c.sql_table}</div>
                <div><strong>${c.sql_count}</strong></div>
                <div style="font-size:.78rem;color:var(--text-muted)">${c.mongo_collection}</div>
                <div><strong>${c.mongo_count}</strong> <span class="match-badge ${c.match ? 'match-yes' : 'match-no'}">${c.match ? '✅' : '❌'}</span></div>
            </div>`;
        });
        container.innerHTML = html;
    } catch (e) { container.innerHTML = `<div style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

async function loadComparison(type) {
    const container = document.getElementById('compareResults');
    container.innerHTML = '<div class="loading">Comparando...</div>';
    try {
        const res = await fetch(`/api/compare/${type}`);
        const data = await res.json();
        let html = `<div class="compare-card">
            <h4>${data.query_description} <span class="match-badge ${data.match ? 'match-yes' : 'match-no'}">${data.match ? '✅ Coincide' : '❌ Diferencia'}</span></h4>`;
        
        html += '<div class="side-by-side"><div>';
        html += `<div class="side-label">🗄️ SQL Server (${data.sql_count || (data.sql_detail_count || 0)} resultados)</div>`;
        html += `<div class="query-display">${data.sql_query}</div>`;
        if (Array.isArray(data.sql_results) && data.sql_results.length) {
            const cols = Object.keys(data.sql_results[0]);
            html += renderTable(cols, data.sql_results);
        }
        html += '</div><div>';
        html += `<div class="side-label">🍃 MongoDB (${data.mongo_count || (data.mongo_detail_count || 0)} resultados)</div>`;
        html += `<div class="query-display">${data.mongo_query}</div>`;
        if (Array.isArray(data.mongo_results) && data.mongo_results.length) {
            const cols = Object.keys(data.mongo_results[0]);
            html += renderTable(cols, data.mongo_results);
        } else if (data.mongo_result) {
            html += `<div class="json-view">${JSON.stringify(data.mongo_result, null, 2)}</div>`;
        }
        html += '</div></div></div>';
        container.innerHTML = html;
    } catch (e) { container.innerHTML = `<div style="color:var(--accent-rose)">Error: ${e.message}</div>`; }
}

// ============ MAPPING INFO ============
async function loadMappingInfo() {
    try {
        const res = await fetch('/api/migration/mapping');
        const data = await res.json();
        const container = document.getElementById('mappingInfo');
        let html = '<h3>🗺️ Dominios y Mapeo</h3><div class="strategy-grid">';
        data.domains.forEach(d => {
            html += `<div class="strategy-card">
                <h4>${d.domain} <span class="pattern-badge embed">${d.pattern}</span></h4>
                <p>${d.description}</p>
                <div style="margin-top:8px">
                    <div style="font-size:.75rem;color:var(--text-muted)">SQL: ${d.sql_tables.join(', ')}</div>
                    <div style="font-size:.75rem;color:var(--accent-emerald)">→ MongoDB: ${d.mongo_collections.join(', ')}</div>
                </div>
            </div>`;
        });
        html += '</div>';
        container.innerHTML = html;
    } catch (e) { console.error(e); }
}

// ============ HELPERS ============
function renderTable(columns, data) {
    if (!data || !data.length) return '<p class="text-muted">Sin datos</p>';
    let html = '<table class="data-table"><thead><tr>';
    columns.forEach(c => html += `<th>${c}</th>`);
    html += '</tr></thead><tbody>';
    data.forEach(row => {
        html += '<tr>';
        columns.forEach(c => {
            let v = row[c];
            if (v === null || v === undefined) v = '<span style="color:var(--text-muted)">NULL</span>';
            else if (typeof v === 'object') v = JSON.stringify(v).substring(0, 80);
            else v = String(v).substring(0, 100);
            html += `<td>${v}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
}
