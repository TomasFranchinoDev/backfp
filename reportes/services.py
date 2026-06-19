import calendar
from datetime import date, timedelta
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

from calendario.models import EventoCalendario
from asignaciones.models import AsignacionDocente
from academico.models import SlotHorario
from asistencia.models import RegistroAsistencia
from core.constants import DiaSemana

def calcular_ausencias_dinamicas(desde: date, hasta: date, institucion: str = None, agrupar_por: str = 'docente'):
    """
    Cruza el catálogo teórico vs los registros reales para deducir ausencias.
    Soporta agrupamiento por 'docente', 'carrera' o 'materia'.
    """
    fecha_inicio = desde
    fecha_fin = hasta

    # 1. Obtener eventos del calendario académico del mes
    eventos = EventoCalendario.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
    mapa_eventos = {evento.fecha: evento.descripcion for evento in eventos}

    # 2. Precargar todos los registros de asistencia del mes
    registros = RegistroAsistencia.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
    # Clave: (docente_id, slot_id, fecha) -> Valor: True
    mapa_asistencia = {(r.docente_id, r.slot_horario_id, r.fecha): True for r in registros}

    # 3. Filtrar asignaciones activas (opcional por institución)
    asignaciones = AsignacionDocente.objects.filter(
        activa=True,
        fecha_inicio__lte=fecha_fin
    ).select_related('docente__user', 'materia')

    if institucion:
        asignaciones = asignaciones.filter(materia__carreras_asociadas__carrera__institucion=institucion).distinct()

    # Prefetch de carreras asociadas para evitar consultas N+1
    asignaciones = asignaciones.prefetch_related('materia__carreras_asociadas__carrera')

    # 4. Precargar Slots Horarios para esas materias
    materias_ids = [a.materia_id for a in asignaciones]
    slots = SlotHorario.objects.filter(materia_id__in=materias_ids).select_related('materia')
    
    # Agrupar slots por materia: {materia_id: [slot1, slot2]}
    slots_por_materia = defaultdict(list)
    for slot in slots:
        slots_por_materia[slot.materia_id].append(slot)

    # Estructura temporal para acumular datos
    reporte_grupos = defaultdict(lambda: {
        'nombre': '',
        'codigo': None,
        'esperadas': 0,
        'asistencias': 0,
        'ausencias': [],
    })

    nombres_dias = dict(DiaSemana.choices)

    # Iterar sobre las fechas del rango
    delta_days = (fecha_fin - fecha_inicio).days + 1
    for dia in range(delta_days):
        fecha_actual = fecha_inicio + timedelta(days=dia)
        tiene_evento = fecha_actual in mapa_eventos
        evento_desc = mapa_eventos.get(fecha_actual)
        dia_semana_actual = fecha_actual.weekday() # 0 = Lunes

        for asignacion in asignaciones:
            # Check si la asignación cubría esta fecha específica
            if asignacion.fecha_inicio > fecha_actual:
                continue
            if asignacion.fecha_fin and asignacion.fecha_fin < fecha_actual:
                continue

            docente_id = asignacion.docente_id
            docente_nombre = asignacion.docente.user.get_full_name()
            materia_id = asignacion.materia_id
            materia_nombre = asignacion.materia.nombre
            materia_codigo = asignacion.materia.codigo_siu
            carreras_asoc = list(asignacion.materia.carreras_asociadas.all())

            # Revisar si hay clases programadas para este día de la semana, vigentes en la fecha actual
            slots_hoy = [
                s for s in slots_por_materia[materia_id] 
                if s.dia_semana == dia_semana_actual and s.valido_desde <= fecha_actual and (s.valido_hasta is None or s.valido_hasta >= fecha_actual)
            ]

            for slot in slots_hoy:
                asistio = (docente_id, slot.id, fecha_actual) in mapa_asistencia
                
                # Definir los grupos a los que afecta esta clase
                grupos = []
                if agrupar_por == 'docente':
                    grupos.append({
                        'id': docente_id,
                        'nombre': docente_nombre,
                        'codigo': None
                    })
                elif agrupar_por == 'carrera':
                    for mc in carreras_asoc:
                        grupos.append({
                            'id': mc.carrera.id,
                            'nombre': mc.carrera.nombre,
                            'codigo': mc.carrera.codigo
                        })
                elif agrupar_por == 'materia':
                    grupos.append({
                        'id': materia_id,
                        'nombre': materia_nombre,
                        'codigo': materia_codigo
                    })

                for grp in grupos:
                    gid = grp['id']
                    reporte_grupos[gid]['nombre'] = grp['nombre']
                    reporte_grupos[gid]['codigo'] = grp['codigo']

                    if asistio:
                        reporte_grupos[gid]['asistencias'] += 1
                        # Si asistió en un feriado/bloqueado, lo sumamos a esperadas para evitar % > 100
                        reporte_grupos[gid]['esperadas'] += 1
                    else:
                        # Ausencia
                        if tiene_evento:
                            # Feriado: se registra con el evento pero no cuenta para la estadística de esperadas/ausencias
                            reporte_grupos[gid]['ausencias'].append({
                                'fecha': fecha_actual,
                                'materia_nombre': materia_nombre,
                                'docente_nombre': docente_nombre,
                                'dia_semana': nombres_dias.get(dia_semana_actual, str(dia_semana_actual)),
                                'hora_inicio': slot.hora_inicio.strftime('%H:%M'),
                                'evento_calendario': evento_desc
                            })
                        else:
                            # Normal: suma a esperadas y ausencias
                            reporte_grupos[gid]['esperadas'] += 1
                            reporte_grupos[gid]['ausencias'].append({
                                'fecha': fecha_actual,
                                'materia_nombre': materia_nombre,
                                'docente_nombre': docente_nombre,
                                'dia_semana': nombres_dias.get(dia_semana_actual, str(dia_semana_actual)),
                                'hora_inicio': slot.hora_inicio.strftime('%H:%M'),
                                'evento_calendario': None
                            })

    return reporte_grupos

def generar_datos_desnormalizados(desde: date, hasta: date, institucion: str = None):
    """
    Genera una lista plana de diccionarios con todas las inasistencias desnormalizadas.
    Cada elemento representa una única ausencia con todos los datos cruzados (14 columnas).
    Incluye ausencias por feriado con la columna 'tipo_dia' indicando el evento.
    """
    fecha_inicio = desde
    fecha_fin = hasta

    # 1. Eventos del calendario
    eventos = EventoCalendario.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
    mapa_eventos = {evento.fecha: evento.descripcion for evento in eventos}

    # 2. Registros de asistencia
    registros = RegistroAsistencia.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
    mapa_asistencia = {(r.docente_id, r.slot_horario_id, r.fecha): True for r in registros}

    # 3. Asignaciones activas
    asignaciones = AsignacionDocente.objects.filter(
        activa=True,
        fecha_inicio__lte=fecha_fin
    ).select_related('docente__user', 'materia')

    if institucion:
        asignaciones = asignaciones.filter(materia__carreras_asociadas__carrera__institucion=institucion).distinct()

    asignaciones = asignaciones.prefetch_related('materia__carreras_asociadas__carrera')

    # 4. Slots horarios
    materias_ids = [a.materia_id for a in asignaciones]
    slots = SlotHorario.objects.filter(materia_id__in=materias_ids).select_related('materia')

    slots_por_materia = defaultdict(list)
    for slot in slots:
        slots_por_materia[slot.materia_id].append(slot)

    nombres_dias = dict(DiaSemana.choices)
    filas = []

    delta_days = (fecha_fin - fecha_inicio).days + 1
    for dia in range(delta_days):
        fecha_actual = fecha_inicio + timedelta(days=dia)
        tiene_evento = fecha_actual in mapa_eventos
        evento_desc = mapa_eventos.get(fecha_actual)
        dia_semana_actual = fecha_actual.weekday()

        for asignacion in asignaciones:
            if asignacion.fecha_inicio > fecha_actual:
                continue
            if asignacion.fecha_fin and asignacion.fecha_fin < fecha_actual:
                continue

            docente = asignacion.docente
            docente_nombre = docente.user.get_full_name()
            docente_dni = docente.user.username
            materia = asignacion.materia
            carreras_asoc = list(materia.carreras_asociadas.all())

            # Concatenar carreras asociadas
            if carreras_asoc:
                carreras_nombres = ' / '.join(mc.carrera.nombre for mc in carreras_asoc)
                carreras_codigos = ' / '.join(mc.carrera.codigo for mc in carreras_asoc)
                instituciones = ' / '.join(
                    mc.carrera.get_institucion_display() if hasattr(mc.carrera, 'get_institucion_display') 
                    else mc.carrera.institucion.upper() 
                    for mc in carreras_asoc
                )
            else:
                carreras_nombres = 'Sin carrera asignada'
                carreras_codigos = '-'
                instituciones = '-'

            slots_hoy = [
                s for s in slots_por_materia[materia.id]
                if s.dia_semana == dia_semana_actual and s.valido_desde <= fecha_actual and (s.valido_hasta is None or s.valido_hasta >= fecha_actual)
            ]

            for slot in slots_hoy:
                asistio = (docente.id, slot.id, fecha_actual) in mapa_asistencia

                if not asistio:
                    filas.append({
                        'fecha': fecha_actual,
                        'dia': nombres_dias.get(dia_semana_actual, str(dia_semana_actual)),
                        'tipo_dia': evento_desc if tiene_evento else 'Laborable',
                        'docente': docente_nombre,
                        'dni': docente_dni,
                        'materia': materia.nombre,
                        'codigo_materia': materia.codigo_siu,
                        'anio_materia': materia.anio,
                        'carreras': carreras_nombres,
                        'codigo_carrera': carreras_codigos,
                        'institucion': instituciones,
                        'hora_inicio': slot.hora_inicio.strftime('%H:%M'),
                        'hora_fin': slot.hora_fin.strftime('%H:%M'),
                        'rol_docente': asignacion.get_rol_display() if hasattr(asignacion, 'get_rol_display') else asignacion.rol.capitalize(),
                    })

    # Ordenar por fecha, luego por docente
    filas.sort(key=lambda f: (f['fecha'], f['docente'], f['hora_inicio']))
    return filas


def generar_excel_ausencias(datos_desnormalizados: list, desde: date, hasta: date, institucion: str):
    """
    Genera un archivo Excel (.xlsx) desnormalizado con una fila por cada inasistencia.
    Incluye 14 columnas con toda la información cruzada, filtros automáticos y formato profesional.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Inasistencias"

    # ── Estilos ──
    header_fill = PatternFill(start_color="2B3A67", end_color="2B3A67", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    feriado_fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
    feriado_font = Font(color="856404", italic=True)
    date_font = Font(bold=True)

    # ── Cabeceras (14 columnas) ──
    headers = [
        "Fecha",
        "Día",
        "Tipo Día",
        "Docente",
        "DNI",
        "Materia",
        "Código Materia (SIU)",
        "Año Materia",
        "Carrera(s)",
        "Código Carrera",
        "Institución",
        "Hora Inicio",
        "Hora Fin",
        "Rol Docente",
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # ── Llenado de datos ──
    for row_idx, fila in enumerate(datos_desnormalizados, start=2):
        fecha_cell = ws.cell(row=row_idx, column=1, value=fila['fecha'].strftime('%d/%m/%Y'))
        fecha_cell.font = date_font

        ws.cell(row=row_idx, column=2, value=fila['dia'])
        tipo_dia_cell = ws.cell(row=row_idx, column=3, value=fila['tipo_dia'])
        ws.cell(row=row_idx, column=4, value=fila['docente'])
        ws.cell(row=row_idx, column=5, value=fila['dni'])
        ws.cell(row=row_idx, column=6, value=fila['materia'])
        ws.cell(row=row_idx, column=7, value=fila['codigo_materia'])
        ws.cell(row=row_idx, column=8, value=fila['anio_materia']).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=9, value=fila['carreras'])
        ws.cell(row=row_idx, column=10, value=fila['codigo_carrera'])
        ws.cell(row=row_idx, column=11, value=fila['institucion'])
        ws.cell(row=row_idx, column=12, value=fila['hora_inicio']).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=13, value=fila['hora_fin']).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=14, value=fila['rol_docente'])

        # Resaltar filas de feriado
        if fila['tipo_dia'] != 'Laborable':
            tipo_dia_cell.fill = feriado_fill
            tipo_dia_cell.font = feriado_font

    # ── Filtros automáticos ──
    last_row = max(len(datos_desnormalizados) + 1, 2)
    ws.auto_filter.ref = f"A1:N{last_row}"

    # ── Congelar fila de cabecera ──
    ws.freeze_panes = "A2"

    # ── Ancho de columnas ──
    column_widths = {
        'A': 14,   # Fecha
        'B': 12,   # Día
        'C': 28,   # Tipo Día
        'D': 30,   # Docente
        'E': 14,   # DNI
        'F': 35,   # Materia
        'G': 20,   # Código Materia
        'H': 14,   # Año Materia
        'I': 35,   # Carrera(s)
        'J': 16,   # Código Carrera
        'K': 14,   # Institución
        'L': 14,   # Hora Inicio
        'M': 12,   # Hora Fin
        'N': 14,   # Rol Docente
    }
    for col_letter, width in column_widths.items():
        ws.column_dimensions[col_letter].width = width

    # ── Hoja de resumen con filtros aplicados ──
    ws_info = wb.create_sheet(title="Info Reporte")
    info_header_fill = PatternFill(start_color="2B3A67", end_color="2B3A67", fill_type="solid")
    info_header_font = Font(color="FFFFFF", bold=True, size=11)
    
    info_data = [
        ("Parámetro", "Valor"),
        ("Fecha Desde", desde.strftime('%d/%m/%Y')),
        ("Fecha Hasta", hasta.strftime('%d/%m/%Y')),
        ("Institución", institucion if institucion else "Todas"),
        ("Total Inasistencias", len(datos_desnormalizados)),
        ("Inasistencias Laborables", sum(1 for f in datos_desnormalizados if f['tipo_dia'] == 'Laborable')),
        ("Inasistencias en Feriado/Evento", sum(1 for f in datos_desnormalizados if f['tipo_dia'] != 'Laborable')),
    ]

    for row_idx, (param, valor) in enumerate(info_data, start=1):
        cell_param = ws_info.cell(row=row_idx, column=1, value=param)
        cell_valor = ws_info.cell(row=row_idx, column=2, value=valor)
        if row_idx == 1:
            cell_param.fill = info_header_fill
            cell_param.font = info_header_font
            cell_valor.fill = info_header_fill
            cell_valor.font = info_header_font

    ws_info.column_dimensions['A'].width = 30
    ws_info.column_dimensions['B'].width = 30

    return wb