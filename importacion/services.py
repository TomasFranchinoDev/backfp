import logging
import pandas as pd
import unicodedata
from django.db import IntegrityError, transaction
from django.contrib.auth.hashers import make_password
from datetime import date, datetime, time

from usuarios.models import Usuario, Docente
from academico.models import Carrera, Materia, MateriaCarrera, SlotHorario
from asignaciones.models import AsignacionDocente
from core.constants import RolDocente
from core.exceptions import ImportacionDataError, ImportacionSystemError


logger = logging.getLogger(__name__)

def normalizar_texto(texto: str) -> str:
    """Elimina acentos, espacios extra y convierte a mayúsculas para comparar."""
    if not texto:
        return ""
    texto = str(texto).strip().upper()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto

def clean_str(val):
    if pd.isna(val) or val is None:
        return ""
    val_str = str(val).strip()
    if val_str.endswith('.0'):
        val_str = val_str[:-2]
    return val_str

def clean_int(val):
    if pd.isna(val) or val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        raise ValueError(f"Valor entero inválido: {val}")

def parse_date(val):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    if isinstance(val, date):
        return val
    if hasattr(val, 'to_pydatetime'):
        return val.to_pydatetime().date()
    try:
        return datetime.strptime(str(val).strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError(f"Formato de fecha inválido: {val}")

def parse_time(val):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, datetime):
        return val.time()
    val_str = str(val).strip()
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(val_str, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Formato de hora inválido: {val}")

def procesar_archivo_siu(archivo, usuario_creador):
    """
    Procesa un archivo Excel de múltiples pestañas de manera secuencial y transaccional.
    """
    try:
        sheets = pd.read_excel(archivo, sheet_name=None)
    except Exception as e:
        logger.exception("No se pudo leer el archivo Excel SIU")
        raise ImportacionDataError(f"No se pudo leer el archivo Excel: {str(e)}") from e


    def find_sheet_df(prefix):
        for name, df in sheets.items():
            if name.strip().startswith(prefix):
                return name, df
        raise ValueError(f"No se encontró la pestaña con el prefijo '{prefix}'")

    # Buscar pestañas
    try:
        carreras_name, df_carreras = find_sheet_df("01")
        docentes_name, df_docentes = find_sheet_df("05")
        materias_name, df_materias = find_sheet_df("02")
        materia_carrera_name, df_materia_carrera = find_sheet_df("03")
        horarios_name, df_horarios = find_sheet_df("04")
        asignaciones_name, df_asignaciones = find_sheet_df("06")
    except ValueError as e:
        # Esto convertirá el error de pestaña faltante en un error 400 controlado
        raise ImportacionDataError(str(e))
    
    resumen = {
        "success": False,
        "carreras_creadas": 0,
        "materias_creadas": 0,
        "docentes_creados": 0,
        "horarios_creados": 0,
        "asignaciones_creadas": 0,
        "errores": []
    }

    # Transacción atómica global
    with transaction.atomic():
        # Inicialización de cachés para evitar consultas N+1
        carreras_cache = {c.codigo: c for c in Carrera.objects.all()}
        materias_cache = {m.codigo_siu: m for m in Materia.objects.all()}
        usuarios_cache = {u.username: u for u in Usuario.objects.all()}
        docentes_cache = {d.user.username: d for d in Docente.objects.select_related('user').all()}

        # --- 1. Carreras ---
        for idx, row in df_carreras.iterrows():
            fila_num = idx + 2
            if row.isnull().all():
                continue
            try:
                with transaction.atomic():
                    codigo = clean_str(row.get('codigo'))
                    nombre = clean_str(row.get('nombre'))
                    duracion_anios = clean_int(row.get('duracion_anios'))
                    
                    if not codigo:
                        raise ValueError("El campo 'código' es obligatorio")
                    if not nombre:
                        raise ValueError("El campo 'nombre' es obligatorio")
                    if duracion_anios is None:
                        raise ValueError("El campo 'duracion_anios' es obligatorio")
                    if duracion_anios < 0:
                        raise ValueError("El campo 'duracion_anios' no puede ser negativo")
                    
                    carrera, created = Carrera.objects.update_or_create(
                        codigo=codigo,
                        defaults={
                            'nombre': nombre,
                            'duracion_anios': duracion_anios,
                            'creado_por': usuario_creador
                        }
                    )
                    carreras_cache[codigo] = carrera
                    if created:
                        resumen["carreras_creadas"] += 1
            except (ValueError, IntegrityError) as e:
                resumen["errores"].append({
                    "pestana": carreras_name,
                    "fila": fila_num,
                    "error": str(e)
                })
            except Exception as e:
                logger.exception("Error inesperado procesando %s fila %s", carreras_name, fila_num)
                raise ImportacionSystemError(
                    f"Error inesperado procesando la pestaña '{carreras_name}', fila {fila_num}."
                ) from e

        # --- 2. Docentes ---
        for idx, row in df_docentes.iterrows():
            fila_num = idx + 2
            if row.isnull().all():
                continue
            try:
                with transaction.atomic():
                    username = clean_str(row.get('username'))
                    first_name_val = row.get('first_name')
                    if pd.isna(first_name_val) or first_name_val is None:
                        first_name_val = row.get('nombre')
                    first_name = clean_str(first_name_val)

                    last_name_val = row.get('last_name')
                    if pd.isna(last_name_val) or last_name_val is None:
                        last_name_val = row.get('apellido')
                    last_name = clean_str(last_name_val)

                    email = clean_str(row.get('email'))
                    
                    if not username:
                        raise ValueError("El campo 'username' (DNI) es obligatorio")
                    if not email:
                        email = f"{username}@ices.edu.ar"
                    
                    usuario = usuarios_cache.get(username)
                    if usuario:
                        usuario.first_name = first_name
                        usuario.last_name = last_name
                        usuario.email = email
                        usuario.save()
                    else:
                        usuario = Usuario.objects.create_user(
                            username=username,
                            email=email,
                            password=username,
                            first_name=first_name,
                            last_name=last_name
                        )
                        usuarios_cache[username] = usuario

                    docente = docentes_cache.get(username)
                    if docente:
                        doc_created = False
                    else:
                        docente, doc_created = Docente.objects.get_or_create(
                            user=usuario,
                            defaults={'creado_por': usuario_creador}
                        )
                        docentes_cache[username] = docente
                    if doc_created:
                        resumen["docentes_creados"] += 1
            except (ValueError, IntegrityError) as e:
                resumen["errores"].append({
                    "pestana": docentes_name,
                    "fila": fila_num,
                    "error": str(e)
                })
            except Exception as e:
                logger.exception("Error inesperado procesando %s fila %s", docentes_name, fila_num)
                raise ImportacionSystemError(
                    f"Error inesperado procesando la pestaña '{docentes_name}', fila {fila_num}."
                ) from e

        # --- 3. Materias ---
        for idx, row in df_materias.iterrows():
            fila_num = idx + 2
            if row.isnull().all():
                continue
            try:
                with transaction.atomic():
                    codigo_siu = clean_str(row.get('codigo_siu'))
                    nombre = clean_str(row.get('nombre'))
                    anio = clean_int(row.get('anio'))
                    
                    if not codigo_siu:
                        raise ValueError("El campo 'codigo_siu' es obligatorio")
                    if not nombre:
                        raise ValueError("El campo 'nombre' es obligatorio")
                    if anio is None:
                        raise ValueError("El campo 'anio' es obligatorio")
                    
                    materia, created = Materia.objects.update_or_create(
                        codigo_siu=codigo_siu,
                        defaults={
                            'nombre': nombre,
                            'anio': anio,
                            'creado_por': usuario_creador
                        }
                    )
                    materias_cache[codigo_siu] = materia
                    if created:
                        resumen["materias_creadas"] += 1
            except (ValueError, IntegrityError) as e:
                resumen["errores"].append({
                    "pestana": materias_name,
                    "fila": fila_num,
                    "error": str(e)
                })
            except Exception as e:
                logger.exception("Error inesperado procesando %s fila %s", materias_name, fila_num)
                raise ImportacionSystemError(
                    f"Error inesperado procesando la pestaña '{materias_name}', fila {fila_num}."
                ) from e

        # --- 4. MateriaCarrera ---
        for idx, row in df_materia_carrera.iterrows():
            fila_num = idx + 2
            if row.isnull().all():
                continue
            try:
                with transaction.atomic():
                    codigo_materia = clean_str(row.get('codigo_materia'))
                    codigo_carrera = clean_str(row.get('codigo_carrera'))
                    anio_plan = clean_int(row.get('anio_plan'))
                    
                    if not codigo_materia:
                        raise ValueError("El campo 'codigo_materia' es obligatorio")
                    if not codigo_carrera:
                        raise ValueError("El campo 'codigo_carrera' es obligatorio")
                    if anio_plan is None:
                        raise ValueError("El campo 'anio_plan' es obligatorio")
                    
                    materia = materias_cache.get(codigo_materia)
                    if not materia:
                        raise ValueError(f"Materia con codigo_siu '{codigo_materia}' no existe")
                        
                    carrera = carreras_cache.get(codigo_carrera)
                    if not carrera:
                        raise ValueError(f"Carrera con código '{codigo_carrera}' no existe")
                    
                    materia_carrera, created = MateriaCarrera.objects.update_or_create(
                        materia=materia,
                        carrera=carrera,
                        defaults={
                            'anio_plan': anio_plan,
                            'creado_por': usuario_creador
                        }
                    )
            except (ValueError, IntegrityError) as e:
                resumen["errores"].append({
                    "pestana": materia_carrera_name,
                    "fila": fila_num,
                    "error": str(e)
                })
            except Exception as e:
                logger.exception("Error inesperado procesando %s fila %s", materia_carrera_name, fila_num)
                raise ImportacionSystemError(
                    f"Error inesperado procesando la pestaña '{materia_carrera_name}', fila {fila_num}."
                ) from e

        # --- 5. Horarios ---
        for idx, row in df_horarios.iterrows():
            fila_num = idx + 2
            if row.isnull().all():
                continue
            try:
                with transaction.atomic():
                    codigo_materia = clean_str(row.get('codigo_materia'))
                    dia_semana = clean_int(row.get('dia_semana'))
                    hora_inicio = parse_time(row.get('hora_inicio'))
                    hora_fin = parse_time(row.get('hora_fin'))
                    
                    if not codigo_materia:
                        raise ValueError("El campo 'codigo_materia' es obligatorio")
                    if dia_semana is None:
                        raise ValueError("El campo 'dia_semana' es obligatorio")
                    if dia_semana < 0 or dia_semana > 6:
                        raise ValueError(f"Día de la semana inválido: {dia_semana}. Debe estar entre 0 (Lunes) y 6 (Domingo)")
                    if not hora_inicio:
                        raise ValueError("El campo 'hora_inicio' es obligatorio")
                    if not hora_fin:
                        raise ValueError("El campo 'hora_fin' es obligatorio")
                    if hora_inicio >= hora_fin:
                        raise ValueError(f"La hora de inicio ({hora_inicio}) debe ser menor que la hora de fin ({hora_fin})")
                    
                    materia = materias_cache.get(codigo_materia)
                    if not materia:
                        raise ValueError(f"Materia con codigo_siu '{codigo_materia}' no existe")
                    
                    slot, created = SlotHorario.objects.get_or_create(
                        materia=materia,
                        dia_semana=dia_semana,
                        hora_inicio=hora_inicio,
                        hora_fin=hora_fin,
                        defaults={
                            'creado_por': usuario_creador
                        }
                    )
                    if created:
                        resumen["horarios_creados"] += 1
            except (ValueError, IntegrityError) as e:
                resumen["errores"].append({
                    "pestana": horarios_name,
                    "fila": fila_num,
                    "error": str(e)
                })
            except Exception as e:
                logger.exception("Error inesperado procesando %s fila %s", horarios_name, fila_num)
                raise ImportacionSystemError(
                    f"Error inesperado procesando la pestaña '{horarios_name}', fila {fila_num}."
                ) from e

        # --- 6. Asignaciones ---
        for idx, row in df_asignaciones.iterrows():
            fila_num = idx + 2
            if row.isnull().all():
                continue
            try:
                with transaction.atomic():
                    username_docente = clean_str(row.get('username_docente'))
                    codigo_materia = clean_str(row.get('codigo_materia'))
                    rol_val = row.get('rol')
                    fecha_inicio = parse_date(row.get('fecha_inicio'))
                    fecha_fin = parse_date(row.get('fecha_fin'))
                    
                    if not username_docente:
                        raise ValueError("El campo 'username_docente' es obligatorio")
                    if not codigo_materia:
                        raise ValueError("El campo 'codigo_materia' es obligatorio")
                    if not fecha_inicio:
                        raise ValueError("El campo 'fecha_inicio' es obligatorio")
                    
                    docente = docentes_cache.get(username_docente)
                    if not docente:
                        raise ValueError(f"Docente con DNI '{username_docente}' no existe")
                    
                    materia = materias_cache.get(codigo_materia)
                    if not materia:
                        raise ValueError(f"Materia con codigo_siu '{codigo_materia}' no existe")
                    
                    rol_texto = clean_str(rol_val).lower() if rol_val else 'titular'
                    rol_final = RolDocente.TITULAR if 'titular' in rol_texto else RolDocente.ADJUNTO
                    
                    asignacion, created = AsignacionDocente.objects.update_or_create(
                        docente=docente,
                        materia=materia,
                        rol=rol_final,
                        defaults={
                            'fecha_inicio': fecha_inicio,
                            'fecha_fin': fecha_fin,
                            'activa': True,
                            'creado_por': usuario_creador
                        }
                    )
                    if created:
                        resumen["asignaciones_creadas"] += 1
            except (ValueError, IntegrityError) as e:
                resumen["errores"].append({
                    "pestana": asignaciones_name,
                    "fila": fila_num,
                    "error": str(e)
                })
            except Exception as e:
                logger.exception("Error inesperado procesando %s fila %s", asignaciones_name, fila_num)
                raise ImportacionSystemError(
                    f"Error inesperado procesando la pestaña '{asignaciones_name}', fila {fila_num}."
                ) from e

    resumen["success"] = len(resumen["errores"]) == 0
    return resumen