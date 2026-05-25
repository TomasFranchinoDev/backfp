from ninja import Router
from django.http import HttpResponse
from io import BytesIO
from core.security import secretario_auth
from .schemas import ReporteMensualOut
from .services import calcular_ausencias_dinamicas, generar_excel_ausencias

router = Router(tags=["Reportes y Auditoría"], auth=secretario_auth)

@router.get("/ausencias", response=ReporteMensualOut)
def previsualizar_reporte_ausencias(request, mes: int, anio: int, institucion: str = None, agrupar_por: str = "docente"):
    """
    Devuelve un JSON con el cálculo dinámico de presencias y ausencias del mes.
    Ideal para mostrar una tabla de resultados en el frontend antes de exportar.
    """
    data_calculada = calcular_ausencias_dinamicas(mes, anio, institucion, agrupar_por)
    
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
            "total_ausencias": len(ausencias_reales),
            "detalle_ausencias": datos['ausencias']
        })
        
    return {
        "mes": mes,
        "anio": anio,
        "institucion": institucion,
        "agrupar_por": agrupar_por,
        "resultados": resultados_list
    }

@router.get("/exportar")
def descargar_excel_ausencias(request, mes: int, anio: int, institucion: str = "Ambas", agrupar_por: str = "docente"):
    """
    Ejecuta el cálculo y retorna un archivo Excel binario descargable.
    """
    filtro_inst = institucion if institucion != "Ambas" else None
    data_calculada = calcular_ausencias_dinamicas(mes, anio, filtro_inst, agrupar_por)
    
    wb = generar_excel_ausencias(data_calculada, mes, anio, institucion, agrupar_por)
    
    # Guardar archivo en memoria
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    response = HttpResponse(
        buffer.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Reporte_Asistencia_{agrupar_por}_{institucion}_{mes}_{anio}.xlsx"'
    return response