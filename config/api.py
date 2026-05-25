from ninja import NinjaAPI
from usuarios.api import router as usuarios_router
from academico.api import router as academico_router
from asignaciones.api import router as asignaciones_router
from calendario.api import router as calendario_router
from asistencia.api import router as asistencia_router
from importacion.api import router as importacion_router
from configuracion.api import router as configuracion_router
from reportes.api import router as reportes_router
# Inicializamos la API global
api = NinjaAPI(
    title="API - Control de Asistencia ICES",
    version="1.0.0",
    description="Backend oficial para el fichaje docente."
)
# Registramos los módulos
api.add_router("/auth/", usuarios_router)
api.add_router("/academico/", academico_router)
api.add_router("/asignaciones/", asignaciones_router) 
api.add_router("/calendario/", calendario_router) 
api.add_router("/asistencia/", asistencia_router)  
api.add_router("/importacion/", importacion_router) 
api.add_router("/configuracion/", configuracion_router)  
api.add_router("/reportes/", reportes_router)  