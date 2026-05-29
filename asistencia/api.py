from datetime import date, timedelta
from typing import Optional
from ninja import Router
from core.security import docente_auth
from django.utils import timezone
from .schemas import FichajeEntradaIn, FichajeOut, FichajeRichOut, EstadoFichajeOut, MateriaStatsOut
from .services import declarar_clase_asincronica, registrar_entrada, registrar_salida
from .models import RegistroAsistencia
from core.security import secretario_auth 
from .schemas import SolicitudEmergenciaIn, SolicitudEmergenciaOut, ResolverEmergenciaIn
from .services import procesar_solicitud_emergencia, resolver_emergencia
from .models import SolicitudEmergencia
from core.constants import EstadoSolicitud, TipoClase
from .schemas import DeclaracionAsincronicaIn, ClaseDisponibleOut
from asignaciones.models import AsignacionDocente
from asignaciones.services import obtener_asignaciones_docente_vigentes
from academico.models import SlotHorario
from calendario.services import is_fecha_bloqueada, obtener_evento_bloqueo
from asignaciones.services import obtener_materia_vigente_para_escaneo, obtener_proxima_clase_hoy
from configuracion.models import Configuracion


# Solo docentes logueados pueden escanear
router = Router(tags=["Motor de Fichaje"], auth=docente_auth)

def get_client_ip(request):
    """Extrae la IP pública real del celular del request HTTP."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

@router.get("/estado_hoy", response=EstadoFichajeOut)
def verificar_estado_actual(request):
    """
    React llama a este endpoint apenas se abre la cámara.
    Sirve para saber si mostrar el botón Verde (Entrada) o Rojo (Salida),
    y ahora también para informar la clase vigente o la próxima clase del día.
    """
    docente_id = request.user.docente.id
    ahora = timezone.localtime()
    
    registro_activo = RegistroAsistencia.objects.filter(
        docente_id=docente_id,
        fecha=ahora.date(),
        hora_entrada__isnull=False,
        hora_salida__isnull=True
    ).first()

    # Estructura base de respuesta
    response = {
        "tiene_entrada_activa": False,
        "materia_actual": None,
        "hora_entrada": None,
        "clase_vigente": None,
        "proxima_clase": None,
        "metodo_validacion": None
    }

    if registro_activo:
        response["tiene_entrada_activa"] = True
        response["materia_actual"] = registro_activo.slot_horario.materia.nombre
        response["hora_entrada"] = timezone.localtime(registro_activo.hora_entrada).strftime("%H:%M")
    else:
        # 1. Si no hay entrada activa, buscar clase vigente
        slot_vigente = obtener_materia_vigente_para_escaneo(
            docente_id=docente_id,
            fecha_actual=ahora.date(),
            hora_actual=ahora.time()
        )
        if slot_vigente:
            response["clase_vigente"] = slot_vigente.materia.nombre
        else:
            # 2. Si no hay vigente, buscar próxima clase del día
            proxima = obtener_proxima_clase_hoy(
                docente_id=docente_id,
                fecha_actual=ahora.date(),
                hora_actual=ahora.time()
            )
            if proxima:
                dummy_date = ahora.date()
                dt_inicio = timezone.datetime.combine(dummy_date, proxima.hora_inicio)
                # Ventana de fichaje es 60 mins antes del inicio de la clase
                fichable_desde_dt = dt_inicio - timedelta(minutes=60)
                
                response["proxima_clase"] = {
                    "materia_nombre": proxima.materia.nombre,
                    "hora_inicio": proxima.hora_inicio.strftime("%H:%M"),
                    "hora_fin": proxima.hora_fin.strftime("%H:%M"),
                    "fichable_desde": fichable_desde_dt.strftime("%H:%M")
                }
    
    # 3. Incluir siempre el método de validación configurado
    config = Configuracion.objects.first()
    response["metodo_validacion"] = config.metodo_validacion_ubicacion if config else None

    return response

@router.post("/chequeoprofesor/entrada", response={200: FichajeRichOut, 400: FichajeRichOut})
def endpoint_fichar_entrada(request, payload: FichajeEntradaIn):
    """Endpoint que se dispara al confirmar la ENTRADA tras escanear el QR."""
    docente_id = request.user.docente.id
    ip_cliente = get_client_ip(request)
    
    resultado = registrar_entrada(
        docente_id=docente_id,
        lat=payload.latitud,
        lon=payload.longitud,
        ip=ip_cliente,
        tipo_clase=payload.tipo_clase
    )
    resultado["docente_nombre"] = request.user.get_full_name()
    
    status_code = 200 if resultado["success"] else 400
    return status_code, resultado

@router.post("/chequeoprofesor/salida", response={200: FichajeRichOut, 400: FichajeRichOut})
def endpoint_fichar_salida(request, payload: FichajeEntradaIn):
    """Endpoint que se dispara al confirmar la SALIDA tras escanear el QR."""
    docente_id = request.user.docente.id
    ip_cliente = get_client_ip(request)
    
    resultado = registrar_salida(
        docente_id=docente_id,
        lat=payload.latitud,
        lon=payload.longitud,
        ip=ip_cliente
    )
    resultado["docente_nombre"] = request.user.get_full_name()
    
    status_code = 200 if resultado["success"] else 400
    return status_code, resultado


# ==========================================
# RUTAS DEL DOCENTE (Usa el auth=docente_auth del router global)
# ==========================================

@router.post("/emergencias", response={201: FichajeOut, 400: FichajeOut})
def crear_emergencia_endpoint(request, payload: SolicitudEmergenciaIn):
    """El docente reporta un problema técnico desde su celular o la web."""
    docente_id = request.user.docente.id
    exito, mensaje = procesar_solicitud_emergencia(
        docente_id, 
        payload.slot_horario_id, 
        payload.nota_docente,
        payload.fecha
    )
    
    status_code = 201 if exito else 400
    return status_code, {"success": exito, "mensaje": mensaje}

# ==========================================
# RUTAS DE LA SECRETARÍA (Sobrescribimos el auth explícitamente)
# ==========================================

@router.get("/admin/emergencias/pendientes", response=list[SolicitudEmergenciaOut], auth=secretario_auth)
def listar_emergencias_pendientes(request):
    """Lista las alertas no resueltas para que la Secretaría actúe."""
    solicitudes = SolicitudEmergencia.objects.filter(estado=EstadoSolicitud.PENDIENTE).select_related('docente__user', 'slot_horario__materia')
    
    # Formateamos la salida para que el Front la entienda fácil
    resultado = []
    for sol in solicitudes:
        resultado.append({
            "id": sol.id,
            "docente_nombre": sol.docente.user.get_full_name(),
            "materia_nombre": sol.slot_horario.materia.nombre if sol.slot_horario else "No especificada",
            "fecha": sol.fecha,
            "estado": sol.estado,
            "nota_docente": sol.nota_docente
        })
    return resultado

@router.patch("/admin/emergencias/{solicitud_id}/resolver", response={200: FichajeOut, 400: FichajeOut}, auth=secretario_auth)
def resolver_emergencia_endpoint(request, solicitud_id: int, payload: ResolverEmergenciaIn):
    """Aprueba o rechaza la solicitud (generando el fichaje si se aprueba)."""
    exito, mensaje = resolver_emergencia(
        solicitud_id=solicitud_id, 
        aprobar=payload.aprobar, 
        nota_secretaria=payload.nota_secretaria, 
        usuario_admin=request.user
    )
    
    status_code = 200 if exito else 400
    return status_code, {"success": exito, "mensaje": mensaje}


@router.get("/mis_clases_hoy", response=list[ClaseDisponibleOut])
def listar_clases_del_dia(request, fecha: Optional[date] = None):
    """
    Devuelve las clases que el docente tiene asignadas para el día indicado (o el día actual por defecto).
    El frontend (React) usa esto para llenar el combo (dropdown) en el panel web.
    """
    docente_id = request.user.docente.id
    target_date = fecha if fecha else timezone.localdate()
    dia_semana_actual = target_date.weekday()
    
    # Buscamos las materias que dicta
    materias_ids = obtener_asignaciones_docente_vigentes(docente_id, target_date).values_list('materia_id', flat=True)
    
    # Filtramos los slots de esas materias que caen exactamente hoy
    slots_hoy = SlotHorario.objects.filter(
        materia_id__in=materias_ids, dia_semana=dia_semana_actual
    ).select_related('materia').prefetch_related('materia__carreras_asociadas__carrera')
    
    # Formateamos para el frontend
    resultado = []
    for slot in slots_hoy:
        carreras_codigos = ", ".join(
            sorted({vinculo.carrera.codigo for vinculo in slot.materia.carreras_asociadas.all()})
        )

        resultado.append({
            "slot_id": slot.id,
            "carreras_codigos": carreras_codigos,
            "materia_nombre": slot.materia.nombre,
            "hora_inicio": slot.hora_inicio.strftime("%H:%M"),
            "hora_fin": slot.hora_fin.strftime("%H:%M")
        })
        
    return resultado

@router.post("/asincronica/declarar", response={200: FichajeOut, 400: FichajeOut})
def declarar_asincronica_endpoint(request, payload: DeclaracionAsincronicaIn):
    """
    Endpoint para que el docente declare una clase asincrónica desde su panel web.
    NO pasa por el circuito de escaneo QR.
    """
    docente_id = request.user.docente.id
    
    exito, mensaje = declarar_clase_asincronica(
        docente_id=docente_id,
        slot_id=payload.slot_horario_id,
        fecha_dictado=payload.fecha_dictado,
        nota=payload.nota
    )
    
    status_code = 200 if exito else 400
    return status_code, {"success": exito, "mensaje": mensaje}


@router.get("/mis_materias_stats", response=list[MateriaStatsOut])
def obtener_mis_materias_stats(request):
    """
    Retorna el listado consolidado de materias asignadas al docente
    con sus días de dictado, totales de asistencias, asincrónicas, faltas
    e historial detallado clase por clase.
    """
    docente_id = request.user.docente.id
    hoy = timezone.localdate()
    
    asignaciones = AsignacionDocente.objects.filter(
        docente_id=docente_id,
        activa=True,
        materia__activa=True,
    ).select_related('materia')
    
    resultado = []
    
    for asig in asignaciones:
        materia = asig.materia
        slots = list(SlotHorario.objects.filter(materia=materia))
        
        # Formatear días de cursada
        dias_cursada = []
        for slot in slots:
            dias_cursada.append(
                f"{slot.get_dia_semana_display()} {slot.hora_inicio.strftime('%H:%M')} - {slot.hora_fin.strftime('%H:%M')}"
            )
            
        fecha_inicio = asig.fecha_inicio
        fecha_fin = asig.fecha_fin
        hasta_fecha = min(hoy, fecha_fin) if fecha_fin else hoy
        
        asistencias_count = 0
        asincronicas_count = 0
        faltas_count = 0
        historial = []
        
        # Prefetch de asistencias y emergencias para esta materia y rango
        registros = RegistroAsistencia.objects.filter(
            docente_id=docente_id,
            slot_horario__materia=materia,
            fecha__range=(fecha_inicio, hasta_fecha)
        ).select_related('slot_horario', 'solicitud_emergencia')
        registro_map = {(r.slot_horario_id, r.fecha): r for r in registros}
        
        emergencias = SolicitudEmergencia.objects.filter(
            docente_id=docente_id,
            fecha__range=(fecha_inicio, hasta_fecha)
        ).select_related('slot_horario')
        
        emergencia_map = {}
        emergencias_generales_map = {}
        for e in emergencias:
            if e.slot_horario_id:
                if e.slot_horario.materia_id == materia.id:
                    emergencia_map[(e.slot_horario_id, e.fecha)] = e
            else:
                emergencias_generales_map[e.fecha] = e
        
        curr_date = fecha_inicio
        while curr_date <= hasta_fecha:
            evento_calendario = obtener_evento_bloqueo(curr_date)
                
            # 1. Verificar si hay slots en este día de la semana
            dia_semana_val = curr_date.weekday()
            slots_hoy = [s for s in slots if s.dia_semana == dia_semana_val]
            
            for slot in slots_hoy:
                reg = registro_map.get((slot.id, curr_date))
                
                ahora_time = timezone.localtime().time()
                es_hoy = (curr_date == hoy)
                clase_finalizada = not es_hoy or (ahora_time > slot.hora_fin)
                
                if reg:
                    if reg.tipo_clase == TipoClase.ASINCRONICA:
                        asincronicas_count += 1
                        historial.append({
                            "fecha": curr_date.strftime("%Y-%m-%d"),
                            "tipo": "Asincrónica",
                            "estado": "Presente (Asíncrona)",
                            "detalle": f"Clase declarada como asíncrona: {reg.nota or ''}".strip()
                        })
                    else:
                        asistencias_count += 1
                        entrada_str = timezone.localtime(reg.hora_entrada).strftime("%H:%M") if reg.hora_entrada else "N/A"
                        salida_str = timezone.localtime(reg.hora_salida).strftime("%H:%M") if reg.hora_salida else "Pendiente"
                        historial.append({
                            "fecha": curr_date.strftime("%Y-%m-%d"),
                            "tipo": reg.tipo_clase.capitalize() if reg.tipo_clase else "Presencial",
                            "estado": "Presente",
                            "detalle": f"Entrada: {entrada_str} - Salida: {salida_str}"
                        })
                else:
                    if evento_calendario:
                        faltas_count += 1
                        historial.append({
                            "fecha": curr_date.strftime("%Y-%m-%d"),
                            "tipo": "Evento Institucional",
                            "estado": "Ausente Justificada",
                            "detalle": f"Evento: {evento_calendario.descripcion}"
                        })
                    elif clase_finalizada:
                        emerg = emergencia_map.get((slot.id, curr_date)) or emergencias_generales_map.get(curr_date)
                        if emerg:
                            if emerg.estado == EstadoSolicitud.PENDIENTE:
                                faltas_count += 1
                                historial.append({
                                    "fecha": curr_date.strftime("%Y-%m-%d"),
                                    "tipo": "Presencial",
                                    "estado": "Ausente",
                                    "detalle": "Ausente (Emergencia reportada pendiente de revisión)"
                                })
                            elif emerg.estado == EstadoSolicitud.RECHAZADA:
                                faltas_count += 1
                                historial.append({
                                    "fecha": curr_date.strftime("%Y-%m-%d"),
                                    "tipo": "Presencial",
                                    "estado": "Ausente",
                                    "detalle": f"Ausente (Emergencia rechazada: {emerg.nota_secretaria or ''})".strip()
                                })
                            else: # Aprobada
                                asistencias_count += 1
                                historial.append({
                                    "fecha": curr_date.strftime("%Y-%m-%d"),
                                    "tipo": "Presencial",
                                    "estado": "Presente",
                                    "detalle": "Presente (Emergencia aprobada por secretaría)"
                                })
                        else:
                            faltas_count += 1
                            historial.append({
                                "fecha": curr_date.strftime("%Y-%m-%d"),
                                "tipo": "Presencial",
                                "estado": "Ausente",
                                "detalle": "Ausente (Sin registro de asistencia)"
                            })
                    else:
                        # Hoy, clase no finalizada aún
                        historial.append({
                            "fecha": curr_date.strftime("%Y-%m-%d"),
                            "tipo": "Presencial",
                            "estado": "Pendiente",
                            "detalle": f"Clase programada para hoy {slot.hora_inicio.strftime('%H:%M')} - {slot.hora_fin.strftime('%H:%M')}"
                        })
                        
            curr_date += timedelta(days=1)
            
        # Ordenamos el historial para que las fechas más recientes vayan primero
        historial.sort(key=lambda x: x["fecha"], reverse=True)
        
        carreras_codigos = ", ".join(
            sorted({vinculo.carrera.codigo for vinculo in materia.carreras_asociadas.all()})
        )
        
        resultado.append({
            "materia_id": materia.id,
            "materia_nombre": materia.nombre,
            "materia_anio": materia.anio,
            "carreras_codigos": carreras_codigos,
            "dias_cursada": dias_cursada,
            "asistencias": asistencias_count,
            "asincronicas": asincronicas_count,
            "faltas": faltas_count,
            "historial": historial
        })
        
    return resultado