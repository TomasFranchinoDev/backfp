from django.utils import timezone
from datetime import date, timedelta
from typing import Optional
from django.db.models import Q
from ninja import Router
import asignaciones
from .validators import validar_ubicacion
from asignaciones.services import obtener_materia_vigente_para_escaneo
from asignaciones.services import obtener_asignaciones_docente_vigentes
from configuracion.models import Configuracion
from core.constants import EstadoSolicitud, TipoClase
from .models import SolicitudEmergencia, RegistroAsistencia
from academico.models import SlotHorario
from asignaciones.models import AsignacionDocente
from django.db import transaction


def _derivar_estado_flujo_ubicacion(resultado) -> str:
    """Determina el estado_flujo específico según qué validación de ubicación falló."""
    if resultado.gps_ok is False and resultado.wifi_ok is False:
        return "error_ubicacion"
    elif resultado.gps_ok is False:
        return "error_gps"
    elif resultado.wifi_ok is False:
        return "error_wifi"
    return "error_ubicacion"  # fallback genérico


@transaction.atomic
def registrar_entrada(usuario, lat: float, lon: float, ip: str, tipo_clase: str) -> dict:
    """
    Procesa un escaneo de ENTRADA con soporte para Fichaje Solidario y Sinceridad Horaria.
    """
    ahora = timezone.localtime()
    docente_accion = usuario.docente # El profesor que hizo clic
    
    # 1. Obtener la clase actual del docente (Valida el margen horario)
    slot_vigente = obtener_materia_vigente_para_escaneo(
        docente_id=docente_accion.id, 
        fecha_actual=ahora.date(), 
        hora_actual=ahora.time()
    )
    
    if not slot_vigente:
        return {
            "success": False,
            "estado_flujo": "sin_clases",
            "mensaje": "No tenés ninguna clase programada para este horario.",
        }

    materia_nombre = slot_vigente.materia.nombre

    # 2. Validar ubicación SOLO para el profesor que tiene el celular en la mano
    gps_ok, wifi_ok, ubicacion_ok = None, None, None
    if tipo_clase == TipoClase.PRESENCIAL:
        config = Configuracion.objects.first() or Configuracion.objects.create(id=1)
        resultado_ubicacion = validar_ubicacion(lat, lon, ip, config)
        gps_ok = resultado_ubicacion.gps_ok
        wifi_ok = resultado_ubicacion.wifi_ok
        
        if not resultado_ubicacion.ubicacion_ok:
            return {
                "success": False,
                "estado_flujo": _derivar_estado_flujo_ubicacion(resultado_ubicacion),
                "gps_ok": gps_ok,
                "wifi_ok": wifi_ok,
                "materia": materia_nombre,
                "tipo_clase": tipo_clase,
                "mensaje": resultado_ubicacion.mensaje,
            }
        ubicacion_ok = True

    # 3. Flujo de Fichaje Solidario
    # Buscamos a TODOS los docentes asignados a esta materia que estén activos
    asignaciones = AsignacionDocente.objects.filter(materia=slot_vigente.materia, activa=True)
    
    estado_final_flujo = "exito"
    mensaje_final = f"Entrada registrada exitosamente para {materia_nombre}."

    for asignacion in asignaciones:
        docente_asignado = asignacion.docente
        
        # Buscar si ya existe un registro hoy para este docente en este slot
        registro_existente = RegistroAsistencia.objects.filter(
            docente=docente_asignado,
            slot_horario=slot_vigente,
            fecha=ahora.date()
        ).first()

        if docente_asignado == docente_accion:
            # =======================================================
            # CASO A: EL PROFESOR QUE ESTÁ USANDO LA APP
            # =======================================================
            if registro_existente:
                ya_se_ficho = (registro_existente.creado_por == usuario) or (registro_existente.modificado_por == usuario)
                if ya_se_ficho:
                    # Él mismo se había fichado antes o ya hizo sinceridad -> Bloquear por duplicado
                    return {
                        "success": False,
                        "estado_flujo": "duplicado",
                        "materia": materia_nombre,
                        "mensaje": "Ya registraste tu entrada para esta clase hoy.",
                    }
                else:
                    # Un compañero lo fichó antes -> SINCERIDAD HORARIA (Actualizar)
                    registro_existente.hora_entrada = ahora
                    registro_existente.modificado_por = usuario
                    # Le inyectamos la ubicación real que acaba de validar
                    registro_existente.ubicacion_validada = ubicacion_ok
                    registro_existente.latitud_registrada = lat
                    registro_existente.longitud_registrada = lon
                    registro_existente.ip_registrada = ip
                    registro_existente.save()
                    
                    estado_final_flujo = "horario_actualizado"
                    mensaje_final = f"Horario de entrada actualizado a las {ahora.strftime('%H:%M')}."
            else:
                # No existe registro -> Crear el suyo normalmente
                RegistroAsistencia.objects.create(
                    docente=docente_accion,
                    slot_horario=slot_vigente,
                    fecha=ahora.date(),
                    anio=ahora.year,
                    tipo_clase=tipo_clase,
                    hora_entrada=ahora,
                    ubicacion_validada=ubicacion_ok,
                    latitud_registrada=lat,
                    longitud_registrada=lon,
                    ip_registrada=ip,
                    creado_por=usuario # La firma de autoría
                )
        else:
            # =======================================================
            # CASO B: EL COMPAÑERO (Fichaje Solidario)
            # =======================================================
            if not registro_existente:
                # Se le crea el registro, pero con GPS/IP nulos (como solicitaste)
                RegistroAsistencia.objects.create(
                    docente=docente_asignado,
                    slot_horario=slot_vigente,
                    fecha=ahora.date(),
                    anio=ahora.year,
                    tipo_clase=tipo_clase,
                    hora_entrada=ahora,
                    ubicacion_validada=None,
                    latitud_registrada=None,
                    longitud_registrada=None,
                    ip_registrada=None,
                    creado_por=usuario # Firma de que lo creó el otro profesor
                )
            # Si el compañero ya tenía registro, no hacemos nada.

    return {
        "success": True,
        "estado_flujo": estado_final_flujo,
        "gps_ok": gps_ok,
        "wifi_ok": wifi_ok,
        "materia": materia_nombre,
        "hora_fichada": ahora.strftime("%H:%M"),
        "tipo_clase": tipo_clase,
        "mensaje": mensaje_final,
    }

def registrar_salida(docente_id: int, lat: float, lon: float, ip: str) -> dict:
    """
    Procesa un escaneo de SALIDA. Valida ubicación para clases presenciales.
    Retorna un dict compatible con FichajeRichOut.
    """
    ahora = timezone.localtime()
    
    # Buscamos el registro de hoy sin salida marcada
    registro_pendiente = RegistroAsistencia.objects.filter(
        docente_id=docente_id,
        fecha=ahora.date(),
        hora_entrada__isnull=False,
        hora_salida__isnull=True
    ).order_by('-hora_entrada').first()

    if not registro_pendiente:
        return {
            "success": False,
            "estado_flujo": "sin_clases",
            "mensaje": "No tenés ninguna entrada activa para registrar salida.",
        }

    materia_nombre = registro_pendiente.slot_horario.materia.nombre
    tipo_clase = registro_pendiente.tipo_clase

    # 2. Validar ubicación (Solo si es clase presencial)
    gps_ok = None
    wifi_ok = None

    if tipo_clase == TipoClase.PRESENCIAL:
        config = Configuracion.objects.first() or Configuracion.objects.create(id=1)
        resultado_ubicacion = validar_ubicacion(lat, lon, ip, config)
        gps_ok = resultado_ubicacion.gps_ok
        wifi_ok = resultado_ubicacion.wifi_ok
        
        if not resultado_ubicacion.ubicacion_ok:
            return {
                "success": False,
                "estado_flujo": _derivar_estado_flujo_ubicacion(resultado_ubicacion),
                "gps_ok": gps_ok,
                "wifi_ok": wifi_ok,
                "materia": materia_nombre,
                "tipo_clase": tipo_clase,
                "mensaje": resultado_ubicacion.mensaje,
            }

    # Actualizamos el registro con la hora de salida
    registro_pendiente.hora_salida = ahora
    registro_pendiente.save()

    return {
        "success": True,
        "estado_flujo": "exito",
        "gps_ok": gps_ok,
        "wifi_ok": wifi_ok,
        "materia": materia_nombre,
        "hora_fichada": ahora.strftime("%H:%M"),
        "tipo_clase": tipo_clase,
        "mensaje": f"Salida registrada exitosamente para {materia_nombre}.",
    }


def procesar_solicitud_emergencia(docente_id: int, slot_id: Optional[int], nota: str, fecha: Optional[date] = None):
    """
    Crea la alerta desde el celular del docente.
    """
    if fecha is None:
        fecha = timezone.localdate()
    
    # Validamos que el slot exista si lo envió
    slot = SlotHorario.objects.filter(id=slot_id).first() if slot_id else None
    
    # Prevenimos spam: que no mande 20 alertas iguales para la misma fecha
    if SolicitudEmergencia.objects.filter(docente_id=docente_id, fecha=fecha, estado=EstadoSolicitud.PENDIENTE).exists():
        return False, "Ya tenés una solicitud pendiente de revisión para la fecha indicada."

    SolicitudEmergencia.objects.create(
        docente_id=docente_id,
        slot_horario=slot,
        fecha=fecha,
        nota_docente=nota,
        estado=EstadoSolicitud.PENDIENTE
    )
    return True, "Solicitud de emergencia enviada a Secretaría."


def resolver_emergencia(solicitud_id: int, aprobar: bool, nota_secretaria: str, usuario_admin):
    """
    La Secretaría aprueba o rechaza. Si aprueba, genera la asistencia perfecta automáticamente.
    """
    solicitud = SolicitudEmergencia.objects.filter(id=solicitud_id, estado=EstadoSolicitud.PENDIENTE).first()
    
    if not solicitud:
        return False, "La solicitud no existe o ya fue resuelta."

    ahora = timezone.localtime()

    if aprobar:
        solicitud.estado = EstadoSolicitud.APROBADA
        
        # --- LA GENERACIÓN MÁGICA DE ASISTENCIA ---
        slots_to_process = []
        if solicitud.slot_horario:
            slots_to_process.append(solicitud.slot_horario)
        else:
            # Emergencia general: Buscar todas las materias asignadas al docente vigentes en esa fecha
            dia_semana_val = solicitud.fecha.weekday()
            
            materias_ids = obtener_asignaciones_docente_vigentes(
                solicitud.docente_id,
                solicitud.fecha,
            ).values_list('materia_id', flat=True)
            
            slots_to_process = list(SlotHorario.objects.filter(
                materia_id__in=materias_ids,
                dia_semana=dia_semana_val,
                valido_desde__lte=solicitud.fecha
            ).filter(
                Q(valido_hasta__isnull=True) | Q(valido_hasta__gte=solicitud.fecha)
            ))

        for slot in slots_to_process:
            # Verificar si ya existe registro de asistencia para evitar duplicados
            exists = RegistroAsistencia.objects.filter(
                docente_id=solicitud.docente_id,
                slot_horario=slot,
                fecha=solicitud.fecha
            ).exists()
            
            if not exists:
                RegistroAsistencia.objects.create(
                    docente_id=solicitud.docente_id,
                    slot_horario=slot,
                    fecha=solicitud.fecha,
                    anio=solicitud.fecha.year,
                    tipo_clase=TipoClase.PRESENCIAL, # Asumimos presencial
                    
                    # Simulamos que entró y salió a la hora perfecta del slot
                    hora_entrada=timezone.make_aware(timezone.datetime.combine(solicitud.fecha, slot.hora_inicio)),
                    hora_salida=timezone.make_aware(timezone.datetime.combine(solicitud.fecha, slot.hora_fin)),
                    ubicacion_validada=True, # Secretaría avala
                    solicitud_emergencia=solicitud, # Vinculamos el registro con la emergencia para auditoría
                    nota=f"Fichaje manual por emergencia (Autorizado por: {usuario_admin.get_full_name()})"
                )
    else:
        solicitud.estado = EstadoSolicitud.RECHAZADA

    # Guardamos los datos de auditoría
    solicitud.nota_secretaria = nota_secretaria
    solicitud.revisado_por = usuario_admin.secretario
    solicitud.revisado_en = ahora
    solicitud.save()

    return True, f"Solicitud {'aprobada' if aprobar else 'rechazada'} exitosamente."

def declarar_clase_asincronica(docente_id: int, slot_id: int, fecha_dictado: date, nota: str):
    """
    Registra una clase asincrónica basada en la presunción de verdad del docente.
    """
    # 1. Validar que la fecha esté en el rango permitido (hasta 7 días antes o después)
    hoy = timezone.localdate()
    if fecha_dictado > hoy + timedelta(days=8):
        return False, "No podés declarar asistencia con más de 7 días de anticipación."
    if fecha_dictado < hoy - timedelta(days=8):
        return False, "No podés declarar asistencia para fechas con más de 7 días de antigüedad."

    # 2. Validar que el slot exista y coincida con el día de la semana
    slot = SlotHorario.objects.filter(id=slot_id).select_related('materia').first()
    if not slot:
        return False, "El horario seleccionado no existe."

    if slot.valido_desde > fecha_dictado or (slot.valido_hasta and slot.valido_hasta < fecha_dictado):
        return False, "El horario seleccionado no era válido en esa fecha."

    if slot.dia_semana != fecha_dictado.weekday():
        return False, "El día de la semana seleccionado no coincide con la cursada oficial de la materia."

    # 3. Validar que el docente esté asignado a esa materia en esa fecha
    asignacion_activa = asignaciones.models.AsignacionDocente.objects.filter(
        docente_id=docente_id,
        materia_id=slot.materia_id,
        activa=True,
        fecha_inicio__lte=fecha_dictado,
        materia__activa=True,
    ).first()

    if not asignacion_activa:
        return False, "No tenés una asignación activa para esta materia en la fecha indicada."

    # 4. Validar duplicados (Que no haya fichado presencial o asincrónico antes ese mismo día)
    if RegistroAsistencia.objects.filter(docente_id=docente_id, slot_horario_id=slot_id, fecha=fecha_dictado).exists():
        return False, "Ya existe un registro de asistencia para esta materia en la fecha indicada."

    # 5. Generar el registro directo (RN-03: Asistencia automática sin validación manual)
    RegistroAsistencia.objects.create(
        docente_id=docente_id,
        slot_horario_id=slot_id,
        fecha=fecha_dictado,
        anio=fecha_dictado.year,
        tipo_clase=TipoClase.ASINCRONICA,
        # Nulos porque no hay presencia física:
        hora_entrada=None, 
        hora_salida=None,
        ubicacion_validada=None,
        nota=f"Modalidad Asincrónica declarada vía web. Nota: {nota}"
    )

    return True, f"Clase asincrónica declarada exitosamente para {slot.materia.nombre}."