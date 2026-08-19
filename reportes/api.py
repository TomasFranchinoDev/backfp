from ninja import Router
from django.http import HttpResponse
from datetime import date
from io import BytesIO
from core.security import secretario_auth
from core.ratelimit import ratelimit_heavy_ops
from .schemas import ReporteMensualOut
from .services import (
    calcular_ausencias_dinamicas,
    generar_datos_desnormalizados,
    generar_datos_desnormalizados_asistencias,
    generar_excel_ausencias,
)

router = Router(tags=["Reportes y Auditoría"], auth=secretario_auth)

@router.get("/ausencias", response=ReporteMensualOut)
@ratelimit_heavy_ops
def previsualizar_reporte_ausencias(request, desde: date, hasta: date, institucion: str = None, agrupar_por: str = "docente"):
    """
    Devuelve un JSON con el cálculo dinámico de asistencias y ausencias del período.
    Incluye discriminación de tipo de clase (Presencial, Virtual Sincrónica, Asincrónica)
    y el detalle clase por clase.
    """
    data_calculada = calcular_ausencias_dinamicas(desde, hasta, institucion, agrupar_por)
    
    # Mapear el diccionario al schema de respuesta Pydantic
    resultados_list = []
    for gid, datos in data_calculada.items():
        ausencias_reales = [a for a in datos['ausencias'] if not a.get('evento_calendario')]
        
        resultados_list.append({
            "id": gid,
            "codigo": datos['codigo'],
            "nombre": datos['nombre'],
            "total_clases_esperadas": datos['esperadas'],
            "total_asistencias": datos['asistencias'],
            "asistencias_presenciales": datos.get('asistencias_presenciales', 0),
            "asistencias_virtuales_sincronicas": datos.get('asistencias_virtuales_sincronicas', 0),
            "asistencias_asincronicas": datos.get('asistencias_asincronicas', 0),
            "total_ausencias": len(ausencias_reales),
            "detalle_ausencias": datos['ausencias'],
            "detalle_asistencias": datos.get('detalle_asistencias', []),
        })
        
    return {
        "desde": desde,
        "hasta": hasta,
        "institucion": institucion,
        "agrupar_por": agrupar_por,
        "resultados": resultados_list
    }

@router.get("/exportar")
@ratelimit_heavy_ops
def descargar_excel_ausencias(request, desde: date, hasta: date, institucion: str = "Ambas"):
    """
    Genera un Excel completo con 4 hojas (Asistencias con Tipo de Clase, Inasistencias, Resumen e Info Reporte).
    """
    filtro_inst = institucion if institucion != "Ambas" else None
    datos_inasistencias = generar_datos_desnormalizados(desde, hasta, filtro_inst)
    datos_asistencias = generar_datos_desnormalizados_asistencias(desde, hasta, filtro_inst)
    
    wb = generar_excel_ausencias(
        datos_desnormalizados=datos_inasistencias,
        desde=desde,
        hasta=hasta,
        institucion=filtro_inst,
        datos_asistencias=datos_asistencias,
    )
    
    # Guardar archivo en memoria
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    inst_label = institucion if institucion != "Ambas" else "Todas"
    response = HttpResponse(
        buffer.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Reporte_Asistencia_{inst_label}_{desde.strftime("%Y%m%d")}_{hasta.strftime("%Y%m%d")}.xlsx"'
    return response