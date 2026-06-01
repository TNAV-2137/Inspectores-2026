import pandas as pd
import folium
import os
import json
import webbrowser
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine

# Configuración de Base de Datos
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")

engine = create_engine(DATABASE_URL) if DATABASE_URL else None
DATABASE_TABLE = "inspectores"

def procesar_y_generar_html():
    # Intentamos leer primero de PostgreSQL
    df = None
    if engine:
        try:
            df = pd.read_sql(f"SELECT * FROM {DATABASE_TABLE}", engine)
            print("📦 Datos leídos con éxito desde PostgreSQL para el mapa.")
        except Exception as e:
            print(f"⚠️ Error al leer de la DB, usando Excel de respaldo: {e}")

    # Si la DB está vacía o falló, usamos el Excel original
    if df is None:
        if not os.path.exists(EXCEL_FILE):
            df_empty = pd.DataFrame(columns=['ZONA', 'GRADO', 'APELLIDO Y NOMBRE', 'ESPECIALIDAD', 'NIVEL', 'CARGO', 'DESTINO', 'TELEFONO', 'CORREO', 'LATITUD Y LONGITUD'])
            df_empty.to_excel(EXCEL_FILE, index=False)
        df = pd.read_excel(EXCEL_FILE)

    # Normalizamos nombres de columnas a mayúsculas
    df.columns = [c.strip().upper() for c in df.columns]

    columnas_requeridas = ['ZONA', 'GRADO', 'APELLIDO Y NOMBRE', 'ESPECIALIDAD', 'NIVEL', 'CARGO', 'DESTINO', 'TELEFONO', 'CORREO', 'LATITUD Y LONGITUD']
    for col in columnas_requeridas:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna('').astype(str).replace(['-', '<->', 'nan', 'NAN'], '')
    def parse_coords(val):
        try:
            if not val or pd.isna(val) or str(val).strip().upper() in ['NONE', 'NAN', '']: 
                return None, None
            v_str = str(val).strip()
            if ',' not in v_str:
                return None, None
            p = v_str.split(',')
            return float(p[0].strip()), float(p[1].strip())
        except Exception:
            return None, None

    # Procesamos de forma segura la columna combinada
    coordenadas_limpias = [parse_coords(x) for x in df['LATITUD Y LONGITUD']]
    df['LAT_TEMP'] = [c[0] for c in coordenadas_limpias]
    df['LON_TEMP'] = [c[1] for c in coordenadas_limpias]
    
    # Creamos el df_mapa eliminando los registros que no tengan coordenadas válidas
    df_mapa = df.dropna(subset=['LAT_TEMP', 'LON_TEMP']).copy()
    
    # ─── CONFIGURACIÓN DEL MAPA (SOLUCIÓN REPETICIÓN Y ZOOM) ───
    limites_argentina = [[-59.5, -77.0], [-20.0, -48.0]]

    m = folium.Map(
        location=[-38.4161, -63.6167],
        zoom_start=4.6,
        tiles='cartodbpositron',          # Evita la carga de mapas infinitos predeterminados
        min_zoom=3.9,                      # Límite máximo para alejar el zoom
        max_zoom=15,
        max_bounds=True,     # Restringe el movimiento fuera de la zona
        min_lat=-60.0,
        max_lat=-20.0,
        min_lon=-75.0,
        max_lon=-50.0,
        control_scale=True
    )
    
    # Métricas superiores
    total_inspectores = len(df)
    total_destinos = df['DESTINO'].nunique()
    total_zonas = df['ZONA'].dropna().nunique()

    grados = sorted([str(x) for x in df['GRADO'].unique() if str(x).strip()])
    esps = sorted([str(x) for x in df['ESPECIALIDAD'].unique() if str(x).strip()])
    cargos = sorted([str(x) for x in df['CARGO'].unique() if str(x).strip()])
    destinos = sorted([str(x) for x in df['DESTINO'].unique() if str(x).strip()])
    
    # Redondeamos a 4 decimales para asegurar que los inspectores del mismo edificio caigan EXACTO en el mismo punto
    df_mapa['LAT_TEMP'] = pd.to_numeric(df_mapa['LAT_TEMP'], errors='coerce').round(4)
    df_mapa['LON_TEMP'] = pd.to_numeric(df_mapa['LON_TEMP'], errors='coerce').round(4)
    
    # Ahora sí, agrupamos por la coordenada unificada
    inspectores_por_coordenada = df_mapa.groupby(['LAT_TEMP', 'LON_TEMP'])

    for (lat, lon), grupo in inspectores_por_coordenada:
    print("COORDENADA:", lat, lon)
    print("CANTIDAD:", len(grupo))

    popup_html = """
    <div style="
        font-family:'Inter',sans-serif;
        min-width:260px;
        max-width:320px;
    ">
    """

    por_destino = grupo.groupby('DESTINO')

    for destino, personal in por_destino:

        total_destino = len(personal)

        popup_html += f"""
        <div style="
            background:#0D3B66;
            color:#EDB445;
            font-weight:bold;
            font-size:11px;
            padding:6px 8px;
            border-radius:4px;
            margin-bottom:6px;
        ">
            {destino} (TOTAL: {total_destino})
        </div>

        <div style="
            max-height:170px;
            overflow-y:auto;
            border:1px solid #1f2937;
            border-radius:4px;
            margin-bottom:10px;
            padding:4px;
        ">
        """

        for _, row in personal.iterrows():

            zona = row.get('ZONA', '')
            grado = row.get('GRADO', '')
            apellido_nombre = row.get('APELLIDO Y NOMBRE', '')
            especialidad = row.get('ESPECIALIDAD', '')
            nivel = row.get('NIVEL', '')
            cargo = row.get('CARGO', '')

            popup_html += f"""
            <div style="
                padding:4px 6px;
                border-bottom:1px solid #eeeeee;
                font-size:11px;
                color:#3B7EF6;
            ">
                <strong>{grado} {apellido_nombre}</strong><br>

                <span style="color:#52637A; font-size:10.5px;">
                    Esp: {especialidad} |
                    Nivel: {nivel}
                </span><br>

                <span style="
                    color:#52637A;
                    font-size:10.5px;
                    font-style:italic;
                ">
                    Cargo: {cargo}
                </span>
            </div>
            """

        popup_html += "</div>"

    popup_html += "</div>"

    folium.Marker(
        location=[float(lat), float(lon)],
        popup=folium.Popup(popup_html, max_width=320),
        icon=folium.Icon(
            color='blue',
            icon='anchor',
            prefix='fa'
        )
    ).add_to(m)
    
    m.fit_bounds(limites_argentina)
    raw_map_html = m._repr_html_()
    
    map_html = f"""
    <div style="width: 100%; height: 100%; position: relative;">
        {raw_map_html}
    </div>
    <style>
        .folium-map {{ width: 100% !important; height: 100% !important;}}
        ::-webkit-scrollbar {{ width: 5px; }}
        ::-webkit-scrollbar-track {{ background: rgba(255,255,255,0.02); }}
        ::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.15); border-radius: 4px; }}
        .btn-delete{{background:#7A1D1D; color:white; border:none;}}
        .btn-delete:hover{{background:#A52A2A;}}
    </style>
    """

    opt_g = "".join(f'<option value="{x}">{x}</option>' for x in grados)
    opt_e = "".join(f'<option value="{x}">{x}</option>' for x in esps)
    opt_c = "".join(f'<option value="{x}">{x}</option>' for x in cargos)
    opt_d = "".join(f'<option value="{x}">{x}</option>' for x in destinos)

    filas_html = ""
    from folium.plugins import MarkerCluster
    for idx, r in df.iterrows():
        filas_html += f"""
        <tr onclick="seleccionarFila(this)" data-idx="{idx}" data-grado="{r['GRADO']}" data-especialidad="{r['ESPECIALIDAD']}" data-cargo="{r['CARGO']}" data-destino="{r['DESTINO']}">
            <td><span class="badge-grado">{r['GRADO']}</span></td>
            <td class="nombre-celda">{r['APELLIDO Y NOMBRE']}</td>
            <td>{r['ESPECIALIDAD']}</td>
            <td>{r['NIVEL']}</td>
            <td>{r['CARGO']}</td>
            <td>{r['DESTINO']}</td>
            <td>{r['TELEFONO']}</td>
            <td style="color: #5B9BFF; font-family: monospace; font-weight: 500;">{r['CORREO']}</td>
            <td style="display:none;" class="val-coor">{r['LATITUD Y LONGITUD']}</td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>DPSN · Panel Técnico de Navegación</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght=400;500;600;700&family=Space+Grotesk:wght=600;700&family=JetBrains+Mono:wght=500;600&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #05080F; --bg-card: #080D17; --bg-card2: #111827; --border: rgba(255, 255, 255, 0.06);
                --accent: #3B7EF6; --gold: #EDB445; --green: #22C55E; --text-main: #F1F5FB; --text-muted: #9BAEC8; --text-dim: #52637A;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; }}
            body {{ background-color: var(--bg); color: var(--text-main); min-height: 100vh; display: flex; flex-direction: column; }}
            .fixed-top-container {{ position: sticky; top: 0; z-index: 1000; background: var(--bg); border-bottom: 1px solid rgba(200, 148, 26, 0.25); box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
            .header-panel {{ display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); padding: 0 24px; height: 150px; }}
            .brand-identity {{ display: flex; align-items: center; gap: 16px; }}
            .brand-logo {{ height: 130px; width: auto; object-fit: contain; display: block; }}
            .title-section h1 {{ font-family: 'Space Grotesk', sans-serif; font-size: 13.5px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; }}
            .title-section span {{ font-family: 'JetBrains Mono', monospace; font-size: 9.5px; color: var(--gold); letter-spacing: 2px; text-transform: uppercase; }}
            .hdr-stats {{ display: flex; align-items: center; margin-left: auto; }}
            .stat {{ display: flex; flex-direction: column; align-items: center; padding: 0 20px; height: 75px; justify-content: center; border-left: 1px solid var(--border); }}
            .stat-n {{ font-family: 'JetBrains Mono', monospace; font-size: 22px; font-weight: 600; color: var(--gold); }}
            .stat-l {{ font-size: 9px; color: var(--text-dim); text-transform: uppercase; margin-top: 4px; letter-spacing: 1px; }}
            .view-selector {{ display: flex; gap: 4px; padding-left: 24px; }}
            .btn-view {{ background: transparent; border: 1px solid transparent; color: var(--text-dim); padding: 8px 16px; font-size: 13px; font-weight: 500; border-radius: 6px; cursor: pointer; }}
            .btn-view.active {{ background: #161F30; color: var(--text-main); border-color: rgba(59,126,246,0.25); position: relative; }}
            .btn-view.active::after {{ content:''; position:absolute; bottom:0; left:10%; width:80%; height:2px; background:var(--accent); }}
            .filter-dashboard {{ background: rgba(5, 8, 15, 0.98); padding: 10px 24px; border-top: 1px solid var(--border); }}
            .tb-inner {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; width: 100%; }}
            .search-box {{ background: var(--bg-card2); border: 1px solid var(--border); padding: 8px 14px; border-radius: 6px; color: var(--text-main); width: 260px; font-size: 13px; outline: none; }}
            .filter-select {{ background: var(--bg-card2); color: var(--text-muted); border: 1px solid var(--border); padding: 8px 12px; border-radius: 6px; font-size: 12px; min-width: 135px; cursor: pointer; outline: none; }}
            .btn-action {{ background: transparent; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; padding: 8px 14px; color: var(--text-muted); font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.2s; }}
            .btn-action:hover {{ background: var(--bg-card2); color: var(--text-main); }}
            .btn-modify {{ background: rgba(59, 126, 246, 0.1); border-color: rgba(59, 126, 246, 0.4); color: #79AFFF; }}
            .btn-modify:hover {{ background: var(--accent); color: white; }}
            .counter-rows {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-dim); margin-left: auto; }}
            .counter-rows b {{ color: var(--gold); }}
            .main-content {{ flex: 1; padding: 20px 24px; }}
            .view-section {{ display: none; }}
            .view-section.active {{ display: block; }}
            .table-wrapper {{ background: var(--bg-card2); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
            th {{ background: #0F1624; color: var(--text-dim); font-weight: 600; padding: 12px 14px; border-bottom: 1px solid var(--border); text-transform: uppercase; font-size: 11px; }}
            td {{ padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.02); color: var(--text-muted); cursor: pointer; }}
            tr.selected-row {{ background: rgba(237, 180, 69, 0.1) !important; border-left: 3px solid var(--gold); }}
            tr:hover {{ background: rgba(255,255,255,0.02); }}
            .badge-grado {{ background: rgba(59,126,246,0.08); border: 1px solid rgba(59,126,246,0.2); color: #79AFFF; padding: 2px 6px; border-radius: 4px; font-weight: 600; font-size: 11px; }}
            .map-wrapper {{ background: var(--bg-card2); border: 1px solid var(--border); height: 700px; max-width: 1100px; margin: 0 auto; border-radius: 10px; overflow: hidden; }}
            .modal-overlay {{ position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(3, 5, 10, 0.85); display: flex; align-items: center; justify-content: center; z-index: 2000; display: none; }}
            .modal-content {{ background: var(--bg-card); border: 1px solid rgba(200, 148, 26, 0.3); width: 480px; border-radius: 12px; padding: 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.7); }}
            .modal-title {{ font-family: 'Space Grotesk', sans-serif; font-size: 16px; color: var(--gold); margin-bottom: 18px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
            .form-group {{ display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }}
            .form-group label {{ font-size: 11px; color: var(--text-dim); text-transform: uppercase; font-weight: 600; }}
            .form-group input {{ background: var(--bg-card2); border: 1px solid var(--border); padding: 8px 12px; border-radius: 6px; color: white; font-size: 13px; outline: none; }}
            .modal-actions {{ display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }}
            .btn-save {{ background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 13px; }}
            .btn-save:hover {{ background: #2563EB; }}
        </style>
    </head>
    <body>
        <div class="fixed-top-container">
            <header class="header-panel">
                <div class="brand-identity">
                    <img src="{LOGO_PATH}" class="brand-logo" alt="HERALDICO_TNAV" onerror="this.src='https://www.prefecturanaval.gob.ar/assets/img/logo_pna.png';">
                    <div class="title-section">
                        <h1>Departamento Técnico de la Navegación</h1>
                        <span>Inspectores Técnicos 2026 · Sistema de Gestión</span>
                    </div>
                </div>
                <div class="hdr-stats">
                    <div class="stat"><div class="stat-n">{total_inspectores}</div><div class="stat-l">Inspectores</div></div>
                    <div class="stat"><div class="stat-n">{total_zonas}</div><div class="stat-l">Zonas</div></div>
                    <div class="stat"><div class="stat-n">{total_destinos}</div><div class="stat-l">Destinos</div></div>
                </div>
                <nav class="view-selector">
                    <button class="btn-view active" onclick="switchView('listado', this)">📋 Listado</button>
                    <button class="btn-view" onclick="switchView('mapa', this)">🗺️ Ubicación Geográfica</button>
                </nav>
            </header>
            <div class="filter-dashboard">
                <div class="tb-inner">
                    <input type="text" id="inputBusqueda" class="search-box" onkeyup="filtrarTodo()" placeholder="🔍 Filtrar por nombre...">
                    <select id="selectGrado" class="filter-select" onchange="filtrarTodo()">
                        <option value="">Grados (Todos)</option>
                        {opt_g}
                    </select>
                    <select id="selectEspecialidad" class="filter-select" onchange="filtrarTodo()">
                        <option value="">Especialidad</option>
                        {opt_e}
                    </select>
                    <select id="selectCargo" class="filter-select" onchange="filtrarTodo()">
                        <option value="">Cargo</option>
                        {opt_c}
                    </select>
                    <select id="selectDestino" class="filter-select" onchange="filtrarTodo()">
                        <option value="">Destino</option>
                        {opt_d}
                    </select>
                    <button class="btn-action" onclick="limpiarFiltros()">✕ Limpiar Filtros</button>
                    <button class="btn-action btn-modify" onclick="abrirModalModificar()">✏️ Modificar</button>
                    <button class="btn-action btn-add" onclick="abrirModalAgregar()"> ＋Agregar</button>
                    <button class="btn-action btn-delete" onclick="eliminarInspector()">🗑 Eliminar</button>                    
                    <div class="counter-rows" id="contador">Mostrando: <b>{total_inspectores}</b> registros</div>
                </div>
            </div>
        </div>

        <main class="main-content">
            <div id="section-listado" class="view-section active">
                <div class="table-wrapper">
                    <table id="tablaInspectores">
                        <thead>
                            <tr>
                                <th>Grado</th>
                                <th>Apellido y Nombre</th>
                                <th>Especialidad</th>
                                <th>Nivel</th>
                                <th>Cargo</th>
                                <th>Destino</th>
                                <th>Telefono</th>
                                <th>Correo</th>
                            </tr>
                        </thead>
                        <tbody>
                           {filas_html}
                        </tbody>
                    </table>
                </div>
            </div>
            <div id="section-mapa" class="view-section">
                <div class="map-wrapper">
                    {map_html}
                </div>
            </div>
        </main>

        <div class="modal-overlay" id="modalModificar" onclick="cerrarModal(event)">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-title">Gestión de Inspector</div>
                <input type="hidden" id="editIdx">
                <div class="form-group"><label>Grado</label><input type="text" id="editGrado"></div>
                <div class="form-group"><label>Apellido y Nombre</label><input type="text" id="editNombre"></div>
                <div class="form-group"><label>Especialidad</label><input type="text" id="editEsp"></div>
                <div class="form-group"><label>Nivel</label><input type="text" id="editNivel"></div>
                <div class="form-group"><label>Cargo</label><input type="text" id="editCargo"></div>
                <div class="form-group"><label>Destino</label><input type="text" id="editDestino"></div>
                <div class="form-group"><label>Telefono</label><input type="text" id="editTelefono"></div>
                <div class="form-group"><label>Correo</label><input type="text" id="editCorreo"></div>
                <div class="form-group"><label>Coordenadas</label><input type="text" id="editCoords"></div>
                <div class="modal-actions">
                    <button class="btn-action" onclick="document.getElementById('modalModificar').style.display='none'">Cancelar</button>
                    <button class="btn-save" onclick="guardarCambiosExcel()">Guardar Cambios</button>
                </div>
            </div>
        </div>

        <script>
            let filaSeleccionada = null;

            function switchView(viewName, button) {{
                document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
                document.querySelectorAll('.btn-view').forEach(b => b.classList.remove('active'));
                document.getElementById('section-' + viewName).classList.add('active');
                button.classList.add('active');
            }}
            
            function seleccionarFila(row) {{
                if(filaSeleccionada) filaSeleccionada.classList.remove('selected-row');
                filaSeleccionada = row;
                filaSeleccionada.classList.add('selected-row');
            }}

            function abrirModalAgregar() {{
                document.getElementById('editIdx').value = '';
                document.getElementById('editGrado').value = '';
                document.getElementById('editNombre').value = '';
                document.getElementById('editEsp').value = '';
                document.getElementById('editNivel').value = '';
                document.getElementById('editCargo').value = '';
                document.getElementById('editDestino').value = '';
                document.getElementById('editTelefono').value = '';
                document.getElementById('editCorreo').value = '';
                document.getElementById('editCoords').value = '';
                document.getElementById('modalModificar').style.display = 'flex';
            }}

            function abrirModalModificar() {{
                if(!filaSeleccionada) {{
                    alert("Por favor, seleccione una fila de la tabla primero haciendo clic sobre ella.");
                    return;
                }}
                document.getElementById('editIdx').value = filaSeleccionada.getAttribute('data-idx');
                document.getElementById('editGrado').value = filaSeleccionada.cells[0].textContent;
                document.getElementById('editNombre').value = filaSeleccionada.cells[1].textContent;
                document.getElementById('editEsp').value = filaSeleccionada.cells[2].textContent;
                document.getElementById('editNivel').value = filaSeleccionada.cells[3].textContent;
                document.getElementById('editCargo').value = filaSeleccionada.cells[4].textContent;
                document.getElementById('editDestino').value = filaSeleccionada.cells[5].textContent;
                document.getElementById('editTelefono').value = filaSeleccionada.cells[6].textContent;
                document.getElementById('editCorreo').value = filaSeleccionada.cells[7].textContent;
                document.getElementById('editCoords').value = filaSeleccionada.querySelector('.val-coor').textContent;
                document.getElementById('modalModificar').style.display = 'flex';
            }}

            function cerrarModal() {{
                document.getElementById('modalModificar').style.display = 'none';
            }}

            function guardarCambiosExcel() {{
                let data = {{
                    idx: document.getElementById('editIdx').value,
                    grado: document.getElementById('editGrado').value,
                    nombre: document.getElementById('editNombre').value,
                    especialidad: document.getElementById('editEsp').value,
                    nivel: document.getElementById('editNivel').value,
                    cargo: document.getElementById('editCargo').value,
                    destino: document.getElementById('editDestino').value,
                    telefono: document.getElementById('editTelefono').value,
                    correo: document.getElementById('editCorreo').value,
                    coords: document.getElementById('editCoords').value
                }};
                fetch('/update', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }})
                .then(r => r.json())
                .then(resp => {{
                    cerrarModal();
                    location.reload();
                }})
                .catch(err => {{
                    alert('Error al guardar cambios');
                    console.error(err);
                }});
            }}

            function eliminarInspector() {{
                if (!filaSeleccionada) {{
                    alert('Seleccione un inspector primero.');
                    return;
                }}
                if (!confirm('¿Desea eliminar este inspector?')) {{
                    return;
                }}
                let idx = filaSeleccionada.getAttribute('data-idx');
                fetch('/delete', {{
                    method: 'POST', 
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ idx: idx }})
                }})
                .then(r => r.json())
                .then(resp => {{
                    cerrarModal();
                    location.reload();
                }})
                .catch(err => {{
                    alert('Error al eliminar inspector');
                    console.error(err);
                }});
            }}

            function filtrarTodo() {{
                let txt = document.getElementById("inputBusqueda").value.toUpperCase();
                let fGrado = document.getElementById("selectGrado").value.toUpperCase();
                let fEsp = document.getElementById("selectEspecialidad").value.toUpperCase();
                let fCargo = document.getElementById("selectCargo").value.toUpperCase();
                let fDest = document.getElementById("selectDestino").value.toUpperCase();
                let rows = document.querySelectorAll("#tablaInspectores tbody tr");
                let visibleCount = 0;

                rows.forEach(row => {{
                    let textContent = row.textContent.toUpperCase();
                    let matchTxt = textContent.includes(txt);
                    let matchGrado = !fGrado || row.getAttribute("data-grado").toUpperCase() === fGrado;
                    let matchEsp = !fEsp || row.getAttribute("data-especialidad").toUpperCase() === fEsp;
                    let matchCargo = !fCargo || row.getAttribute("data-cargo").toUpperCase() === fCargo;
                    let matchDest = !fDest || row.getAttribute("data-destino").toUpperCase() === fDest;
                    
                    if (matchTxt && matchGrado && matchEsp && matchCargo && matchDest) {{
                        row.style.display = ""; visibleCount++;
                    }} else {{
                        row.style.display = "none";
                    }}
                }});
                document.getElementById("contador").innerHTML = "Mostrando: <b>" + visibleCount + "</b> registros";
            }}

            function limpiarFiltros() {{
                document.getElementById("inputBusqueda").value = "";
                document.getElementById("selectGrado").value = "";
                document.getElementById("selectEspecialidad").value = "";
                document.getElementById("selectCargo").value = "";
                document.getElementById("selectDestino").value = "";
                filtrarTodo();
            }}
        </script>
    </body>
    </html>
    """
    with open(HTML_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(html_content)

# ─── MICRO SERVIDOR OPERATIVO INTERNO ───
class ServidorPanelControl(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            procesar_y_generar_html()
            self.path = '/' + HTML_OUTPUT
        return super().do_GET()

    def do_POST(self):
        length = int(self.headers['Content-Length'])
        post_data = json.loads(self.rfile.read(length).decode('utf-8'))
        
        df = pd.read_excel(EXCEL_FILE)
        df.columns = [c.strip().upper() for c in df.columns]
        
        columnas_requeridas = ['ZONA', 'GRADO', 'APELLIDO Y NOMBRE', 'ESPECIALIDAD', 'NIVEL', 'CARGO', 'DESTINO', 'TELEFONO', 'CORREO', 'LATITUD Y LONGITUD']
        for col in columnas_requeridas:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str).replace(['-', '<->', 'nan', 'NAN'], '')
        
        # Ruta para eliminar
        if self.path == '/delete':
            idx = int(post_data['idx'])
            df.drop(idx, inplace=True)
            df.reset_index(drop=True, inplace=True)
            df.to_excel(EXCEL_FILE, index=False)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'deleted'}).encode('utf-8'))
            return

        # Ruta para actualizar / agregar
        if self.path == '/update':
            idx = post_data.get('idx', '')
            
            nueva_fila = {
                'ZONA': str(post_data.get('zona', '')),
                'GRADO': str(post_data.get('grado', '')),
                'APELLIDO Y NOMBRE': str(post_data.get('nombre', '')),
                'ESPECIALIDAD': str(post_data.get('especialidad', '')),
                'NIVEL': str(post_data.get('nivel', '')),
                'CARGO': str(post_data.get('cargo', '')),
                'DESTINO': str(post_data.get('destino', '')),
                'TELEFONO': str(post_data.get('telefono', '')),
                'CORREO': str(post_data.get('correo', '')),
                'LATITUD Y LONGITUD': str(post_data.get('coords', ''))
            }

            if idx == '':
                df.loc[len(df)] = nueva_fila
            else:
                idx = int(idx)
                for llave, valor in nueva_fila.items():
                    df.at[idx, llave] = valor

            df.to_excel(EXCEL_FILE, index=False)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
            return

def iniciar_servidor_seguro():
    procesar_y_generar_html()
    
    # DETECCIÓN DE ENTORNO EN LA NUBE: 
    # Render asigna un puerto dinámico mediante la variable 'PORT'. Si no existe, usa el 8080.
    PUERTO_NUBE = int(os.environ.get("PORT", PORT))
    
    # Escuchamos en 0.0.0.0 y en el puerto que nos exige la nube
    server = HTTPServer(('0.0.0.0', PUERTO_NUBE), ServidorPanelControl)
    
    print("\n" + "="*50)
    print(f" 🚀 SERVIDOR EN LA NUBE INICIADO CON ÉXITO")
    print(f" Escuchando peticiones en el puerto: {PUERTO_NUBE}")
    print("="*50 + "\n")
    
    # CONTROL CRÍTICO: Solo abre el navegador si estás en tu PC local.
    # En Render (Linux Server), 'os.environ.get("PORT")' existe, por lo que NO intentará abrir el navegador.
    if "PORT" not in os.environ:
        try:
            webbrowser.open(f'http://localhost:{PUERTO_NUBE}')
        except Exception:
            pass

    server.serve_forever()

if __name__ == '__main__':
    iniciar_servidor_seguro()
