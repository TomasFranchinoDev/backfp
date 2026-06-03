import calendar
from datetime import date
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

from calendario.models import EventoCalendario
from asignaciones.models import AsignacionDocente
from academico.models import SlotHorario
from asistencia.models import RegistroAsistencia
from core.constants import DiaSemana

def calcular_ausencias_dinamicas(mes: int, anio: int, institucion: str = None, agrupar_por: str = 'docente'):
    """
    Cruza el catálogo teórico vs los registros reales para deducir ausencias.
    Soporta agrupamiento por 'docente', 'carrera' o 'materia'.
    """
    _, ultimo_dia = calendar.monthrange(anio, mes)
    fecha_inicio = date(anio, mes, 1)
    fecha_fin = date(anio, mes, ultimo_dia)

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

    for dia in range(1, ultimo_dia + 1):
        fecha_actual = date(anio, mes, dia)
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

def generar_excel_ausencias(reporte_data, mes: int, anio: int, institucion: str, agrupar_por: str = 'docente'):
    """
    Genera un archivo Excel (.xlsx) en memoria con la estructura Pivot.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = f"Asistencia {mes}-{anio}"

    # Estilos
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    
    # Cabecera principal dinámica
    if agrupar_por == 'docente':
        entidad_header = "Docente"
    elif agrupar_por == 'carrera':
        entidad_header = "Carrera"
    else:
        entidad_header = "Materia"

    # Cabeceras
    headers = [entidad_header, "Total Esperadas", "Asistencias", "Ausencias", "Detalle Faltas (Fecha | Info | Hora)"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Llenado de datos
    row_num = 2
    for grupo_id, datos in reporte_data.items():
        nombre_mostrar = datos['nombre']
        if datos['codigo']:
            nombre_mostrar = f"[{datos['codigo']}] {datos['nombre']}"

        ws.cell(row=row_num, column=1, value=nombre_mostrar)
        ws.cell(row=row_num, column=2, value=datos['esperadas']).alignment = Alignment(horizontal="center")
        ws.cell(row=row_num, column=3, value=datos['asistencias']).alignment = Alignment(horizontal="center")
        
        # Excluir feriados de la cantidad de ausencias para que coincida con las esperadas
        ausencias_reales = [a for a in datos['ausencias'] if not a.get('evento_calendario')]
        ws.cell(row=row_num, column=4, value=len(ausencias_reales)).alignment = Alignment(horizontal="center")
        
        # Formatear el detalle de ausencias como un string con saltos de línea
        detalles_str_list = []
        for a in datos['ausencias']:
            fecha_str = a['fecha'].strftime('%d/%m/%Y')
            if agrupar_por == 'docente':
                info = a['materia_nombre']
            elif agrupar_por == 'carrera':
                info = f"{a['docente_nombre']} - {a['materia_nombre']}"
            else:
                info = a['docente_nombre']

            evento_str = f" [⚠️ {a['evento_calendario']}]" if a.get('evento_calendario') else ""
            detalles_str_list.append(f"{fecha_str} | {info} ({a['hora_inicio']}){evento_str}")

        detalle_str = "\n".join(detalles_str_list)
        cell_detalle = ws.cell(row=row_num, column=5, value=detalle_str)
        cell_detalle.alignment = Alignment(wrap_text=True)
        
        row_num += 1

    # Ajustar ancho de columnas
    ws.column_dimensions['A'].width = 35
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 60

    return wb