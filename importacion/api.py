import logging
from urllib import request

from ninja import Router, File
from ninja.files import UploadedFile
from core.exceptions import ImportacionDataError, ImportacionSystemError
from core.security import secretario_auth
from .schemas import ResumenImportacionOut
from .services import procesar_archivo_siu

router = Router(tags=["Importación SIU"], auth=secretario_auth)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
logger = logging.getLogger(__name__)

@router.post("/siu", response={200: ResumenImportacionOut, 400: dict, 500: dict})
def subir_archivo_siu(request, file: UploadedFile = File(...)):
    """
    Recibe un archivo Excel (.xlsx) exportado del SIU y lo procesa para poblar la base de datos
    con Materias, Docentes y Asignaciones de forma masiva.
    """
    # Validar que sea un archivo Excel
    if not file.name.endswith(('.xlsx', '.xls')):
        return 400, {"success": False, "mensaje": "El archivo debe ser un Excel (.xlsx o .xls)"}
    # Validar tamaño del archivo
    if file.size > MAX_FILE_SIZE:
        return 400, {"success": False, "mensaje": "Archivo demasiado grande (máx 5MB)"}
    # Procesar el archivo pasándole el objeto en memoria y el usuario logueado
    try:
        file.file.seek(0)  # Asegurarse de que el puntero del archivo esté al inicio
        resultados = procesar_archivo_siu(file.file, request.user)
        return 200, resultados
    except ImportacionDataError as e:
        return 400, {"success": False, "mensaje": f"Error crítico al leer el archivo: {str(e)}"}
    except ImportacionSystemError:
        logger.exception("Fallo inesperado procesando la importación SIU")
        return 500, {
            "success": False,
            "mensaje": "Ocurrió un error interno al procesar el archivo. Revisá el log del servidor.",
        }