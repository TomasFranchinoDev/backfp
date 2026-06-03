from datetime import date, time, datetime, timedelta
from django.db.models import Q
from .models import AsignacionDocente
from academico.models import SlotHorario


def obtener_asignaciones_docente_vigentes(docente_id: int, fecha_actual: date):
    """
    Devuelve solo las asignaciones que deben ser visibles para el docente en una fecha dada.
    Excluye asignaciones inactivas y materias desactivadas.
    """
    return AsignacionDocente.objects.filter(
        docente_id=docente_id,
        activa=True,
        fecha_inicio__lte=fecha_actual,
        materia__activa=True,
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_actual)
    )

def obtener_materia_vigente_para_escaneo(docente_id: int, fecha_actual: date, hora_actual: time):
    """
    Busca qué clase le toca dar al docente en este momento exacto.
    Retorna el objeto SlotHorario si encuentra una coincidencia, sino None.
    """
    # 1. ¿Qué día de la semana es hoy? (0 = Lunes, 6 = Domingo)
    dia_semana_actual = fecha_actual.weekday()
    
    # 2. Buscar materias asignadas activas para este docente en la fecha actual
    asignaciones_activas = obtener_asignaciones_docente_vigentes(docente_id, fecha_actual)
    
    # Extraemos los IDs de las materias que dicta
    materias_ids = asignaciones_activas.values_list('materia_id', flat=True)
    
    if not materias_ids:
        return None # No dicta nada hoy (o ya no está activo)

    # 3. Buscar los slots horarios de esas materias para el día de hoy (excluyendo los ya completados o asincrónicos)
    from core.constants import TipoClase
    from asistencia.models import RegistroAsistencia
    
    slots_ya_fichados = RegistroAsistencia.objects.filter(
        docente_id=docente_id,
        fecha=fecha_actual
    ).filter(
        Q(hora_salida__isnull=False) | Q(tipo_clase=TipoClase.ASINCRONICA)
    ).values_list('slot_horario_id', flat=True)

    slots_del_dia = SlotHorario.objects.filter(
        materia_id__in=materias_ids,
        dia_semana=dia_semana_actual,
        valido_desde__lte=fecha_actual
    ).filter(
        Q(valido_hasta__isnull=True) | Q(valido_hasta__gte=fecha_actual)
    ).exclude(id__in=slots_ya_fichados).select_related('materia').order_by('hora_inicio')
    
    # 4. Encontrar el slot que coincida con la hora actual (con tolerancia)
    # Convertimos hora_actual a un objeto datetime dummy para poder sumar/restar minutos
    dummy_date = datetime.today()
    dt_actual = datetime.combine(dummy_date, hora_actual)
    
    MARGEN_MINUTOS = 60 # Aceptamos escaneos 60 min antes o 60 min después
    
    for slot in slots_del_dia:
        dt_inicio = datetime.combine(dummy_date, slot.hora_inicio)
        dt_fin = datetime.combine(dummy_date, slot.hora_fin)
        
        # Ampliamos la ventana permitida con el margen
        ventana_inicio = dt_inicio - timedelta(minutes=MARGEN_MINUTOS)
        ventana_fin = dt_fin + timedelta(minutes=MARGEN_MINUTOS)
        
        # Si la hora del escaneo cae dentro de esta ventana, ¡encontramos la clase!
        if ventana_inicio <= dt_actual <= ventana_fin:
            return slot
            
    return None


def obtener_proxima_clase_hoy(docente_id: int, fecha_actual: date, hora_actual: time):
    """
    Busca la próxima clase del docente para hoy que aún no empezó.
    Retorna el SlotHorario más próximo cuya hora_inicio > hora_actual, o None.
    """
    dia_semana_actual = fecha_actual.weekday()

    # Buscar materias asignadas activas
    asignaciones_activas = obtener_asignaciones_docente_vigentes(docente_id, fecha_actual)

    materias_ids = asignaciones_activas.values_list('materia_id', flat=True)

    if not materias_ids:
        return None

    # Slots del día de hoy, ordenados por hora_inicio (excluyendo los ya completados o asincrónicos)
    from core.constants import TipoClase
    from asistencia.models import RegistroAsistencia
    
    slots_ya_fichados = RegistroAsistencia.objects.filter(
        docente_id=docente_id,
        fecha=fecha_actual
    ).filter(
        Q(hora_salida__isnull=False) | Q(tipo_clase=TipoClase.ASINCRONICA)
    ).values_list('slot_horario_id', flat=True)

    slots_del_dia = SlotHorario.objects.filter(
        materia_id__in=materias_ids,
        dia_semana=dia_semana_actual,
        valido_desde__lte=fecha_actual
    ).filter(
        Q(valido_hasta__isnull=True) | Q(valido_hasta__gte=fecha_actual)
    ).exclude(id__in=slots_ya_fichados).select_related('materia').order_by('hora_inicio')

    # Retornar el primer slot cuya hora de inicio es posterior a la hora actual
    for slot in slots_del_dia:
        if slot.hora_inicio > hora_actual:
            return slot

    return None