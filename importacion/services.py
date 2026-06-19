"""
Servicio de importación SIU — Arquitectura de 2 Fases.

Fase 1 (Validación):  Lee el Excel, valida formato, datos faltantes y
                       referencias cruzadas.  NO toca la base de datos.

Fase 2 (Persistencia): Si la validación pasa sin errores, ejecuta upserts
                        masivos en una única transacción atómica.
"""
import logging
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable, Optional

import pandas as pd
from django.contrib.auth.hashers import make_password
from django.db import connection, transaction
from django.utils import timezone

from academico.models import Carrera, Materia, MateriaCarrera, SlotHorario
from asignaciones.models import AsignacionDocente
from core.constants import RolDocente
from usuarios.models import Docente, Usuario

from .progress import (
    actualizar_progreso,
    completar_tarea,
    error_sistema_tarea,
    error_validacion_tarea,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses — estructuras intermedias de datos validados
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DocenteValidado:
    username: str          # DNI
    first_name: str
    last_name: str
    email: str
    password_raw: str      # Texto plano (se hashea en persistencia)
    password_explicita: bool  # True si la secretaria ingresó contraseña


@dataclass
class CarreraExtraida:
    codigo: str
    nombre: str
    duracion_anios: int
    institucion: str


@dataclass
class MateriaExtraida:
    codigo_siu: str
    nombre: str
    anio: int


@dataclass
class MateriaCarreraExtraida:
    codigo_materia: str
    codigo_carrera: str
    anio_plan: int


@dataclass
class SlotExtraido:
    codigo_materia: str
    dia_semana: int
    hora_inicio: time
    hora_fin: time


@dataclass
class AsignacionExtraida:
    username_docente: str
    codigo_materia: str
    rol: str
    fecha_inicio: date
    fecha_fin: Optional[date]


@dataclass
class DatosValidados:
    docentes: list[DocenteValidado]
    carreras: dict[str, CarreraExtraida]
    materias: dict[str, MateriaExtraida]
    materia_carreras: list[MateriaCarreraExtraida]
    slots: list[SlotExtraido]
    asignaciones: list[AsignacionExtraida]


# ═══════════════════════════════════════════════════════════════════════════
# Constantes
# ═══════════════════════════════════════════════════════════════════════════

DIAS_NOMBRE: dict[str, int] = {
    "LUNES": 0, "MARTES": 1, "MIERCOLES": 2, "MIÉRCOLES": 2,
    "JUEVES": 3, "VIERNES": 4, "SABADO": 5, "SÁBADO": 5, "DOMINGO": 6,
}

ROLES_VALIDOS: dict[str, str] = {
    "TITULAR": RolDocente.TITULAR,
    "ADJUNTO": RolDocente.ADJUNTO,
}

COLUMNAS_DOCENTES = ["DNI", "Nombre", "Apellido", "Email", "Contraseña"]

COLUMNAS_MALLA = [
    "Código Materia SIU", "Nombre Materia", "Año Cursado",
    "Institución", "Código Carrera", "Nombre Carrera", "Duración Carrera (años)",
    "Año Plan de Estudio",
    "Día de Clase", "Hora Inicio", "Hora Fin",
    "DNI Docente", "Rol Docente",
    "Fecha Inicio Asignación", "Fecha Fin Asignación",
]


# ═══════════════════════════════════════════════════════════════════════════
# Funciones utilitarias
# ═══════════════════════════════════════════════════════════════════════════

def _normalizar(texto: str) -> str:
    """Quita acentos de un texto para comparaciones insensibles."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def clean_str(val) -> str:
    """Limpia un valor de celda Excel a string."""
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    val_str = str(val).strip()
    # Pandas lee enteros como float (ej: 40111222.0) → limpiar sufijo .0
    if val_str.endswith(".0"):
        try:
            int(val_str[:-2])
            val_str = val_str[:-2]
        except ValueError:
            pass
    return val_str


def clean_int(val) -> Optional[int]:
    """Convierte un valor de celda a entero, o devuelve None."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def parse_date_val(val) -> Optional[date]:
    """Parsea una fecha desde una celda Excel (soporta múltiples formatos)."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime().date()
    val_str = str(val).strip()
    if not val_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_time_val(val) -> Optional[time]:
    """Parsea una hora desde una celda Excel (soporta time, datetime, float, str)."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, time):
        return val
    if isinstance(val, datetime):
        return val.time()
    # Excel a veces almacena horas como fracción del día (ej: 0.333… = 08:00)
    if isinstance(val, float):
        total_seconds = int(round(val * 86400))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if 0 <= hours < 24:
            return time(hours, minutes)
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(val_str, fmt).time()
        except ValueError:
            continue
    return None


def normalizar_dia(nombre: str) -> Optional[int]:
    """Convierte nombre de día a número (0=Lunes … 6=Domingo)."""
    normalizado = _normalizar(nombre.strip().upper())
    return DIAS_NOMBRE.get(normalizado)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers de error
# ═══════════════════════════════════════════════════════════════════════════

def _error(hoja: str, fila: int, columna: str, valor, mensaje: str) -> dict:
    return {
        "hoja": hoja,
        "fila": fila,
        "columna": columna,
        "valor_recibido": str(valor) if valor is not None else "",
        "mensaje": mensaje,
    }


# ═══════════════════════════════════════════════════════════════════════════
# FASE 1 — Validación
# ═══════════════════════════════════════════════════════════════════════════

def _validar_columnas(df: pd.DataFrame, esperadas: list[str], hoja: str) -> list[dict]:
    """Verifica que existan todas las columnas esperadas en el DataFrame."""
    actuales = {str(c).strip() for c in df.columns}
    faltantes = [c for c in esperadas if c not in actuales]
    return [
        _error(hoja, 1, col, "", f"Falta la columna obligatoria '{col}'")
        for col in faltantes
    ]


def _validar_hoja_docentes(df: pd.DataFrame) -> tuple[list[DocenteValidado], list[dict]]:
    """Valida la hoja Docentes fila por fila."""
    errores: list[dict] = []
    docentes: list[DocenteValidado] = []
    dnis_vistos: dict[str, int] = {}

    for idx, row in df.iterrows():
        fila = idx + 2  # Fila de Excel (1-indexed + encabezado)
        if row.isnull().all():
            continue

        dni = clean_str(row.get("DNI"))
        nombre = clean_str(row.get("Nombre"))
        apellido = clean_str(row.get("Apellido"))
        email = clean_str(row.get("Email"))
        pwd_raw = clean_str(row.get("Contraseña"))

        if not dni:
            errores.append(_error("Docentes", fila, "DNI", "", "El DNI es obligatorio"))
            continue

        if dni in dnis_vistos:
            errores.append(_error(
                "Docentes", fila, "DNI", dni,
                f"DNI duplicado — ya fue definido en la fila {dnis_vistos[dni]}",
            ))
            continue
        dnis_vistos[dni] = fila

        if not nombre:
            errores.append(_error("Docentes", fila, "Nombre", "", "El nombre es obligatorio"))
        if not apellido:
            errores.append(_error("Docentes", fila, "Apellido", "", "El apellido es obligatorio"))

        if not email:
            email = f"{dni}@ices.edu.ar"

        pwd_explicita = bool(pwd_raw)
        if not pwd_raw:
            pwd_raw = dni

        if nombre and apellido:
            docentes.append(DocenteValidado(
                username=dni,
                first_name=nombre,
                last_name=apellido,
                email=email,
                password_raw=pwd_raw,
                password_explicita=pwd_explicita,
            ))

    return docentes, errores


def _validar_hoja_malla(
    df: pd.DataFrame,
    dnis_excel: set[str],
) -> tuple[DatosValidados, list[dict]]:
    """Valida la hoja Malla Académica y extrae entidades desnormalizadas."""
    errores: list[dict] = []

    carreras: dict[str, CarreraExtraida] = {}
    materias: dict[str, MateriaExtraida] = {}
    mc_set: set[tuple[str, str]] = set()
    materia_carreras: list[MateriaCarreraExtraida] = []
    slot_set: set[tuple] = set()
    slots: list[SlotExtraido] = []
    asig_set: set[tuple] = set()
    asignaciones: list[AsignacionExtraida] = []

    # Pre-cargar DNIs que ya existen en la BD para validar referencias
    dnis_en_bd = set(Usuario.objects.values_list("username", flat=True))
    dnis_validos = dnis_excel | dnis_en_bd

    for idx, row in df.iterrows():
        fila = idx + 2
        if row.isnull().all():
            continue

        fila_ok = True  # Se pone en False ante errores críticos de la fila

        # ── Materia (obligatorio) ────────────────────────────────────────
        cod_mat = clean_str(row.get("Código Materia SIU"))
        nom_mat = clean_str(row.get("Nombre Materia"))
        anio_cur_raw = row.get("Año Cursado")
        anio_cur = clean_int(anio_cur_raw)

        if not cod_mat:
            errores.append(_error("Malla Académica", fila, "Código Materia SIU", "", "Campo obligatorio"))
            fila_ok = False
        if not nom_mat:
            errores.append(_error("Malla Académica", fila, "Nombre Materia", "", "Campo obligatorio"))
            fila_ok = False
        if anio_cur is None:
            errores.append(_error("Malla Académica", fila, "Año Cursado", anio_cur_raw,
                                  "Debe ser un número entero"))
            fila_ok = False

        # Consistencia con filas anteriores
        if cod_mat and cod_mat in materias:
            prev = materias[cod_mat]
            if nom_mat and prev.nombre != nom_mat:
                errores.append(_error("Malla Académica", fila, "Nombre Materia", nom_mat,
                    f"Inconsistencia: '{cod_mat}' ya fue definida como '{prev.nombre}'"))
                fila_ok = False
        elif cod_mat and nom_mat and anio_cur is not None:
            materias[cod_mat] = MateriaExtraida(cod_mat, nom_mat, anio_cur)

        # ── Carrera (obligatorio) ────────────────────────────────────────
        cod_car = clean_str(row.get("Código Carrera"))
        nom_car = clean_str(row.get("Nombre Carrera"))
        dur_raw = row.get("Duración Carrera (años)")
        dur_car = clean_int(dur_raw)
        inst = clean_str(row.get("Institución")).lower() or "ices"

        if not cod_car:
            errores.append(_error("Malla Académica", fila, "Código Carrera", "", "Campo obligatorio"))
            fila_ok = False
        if not nom_car:
            errores.append(_error("Malla Académica", fila, "Nombre Carrera", "", "Campo obligatorio"))
            fila_ok = False
        if dur_car is None:
            errores.append(_error("Malla Académica", fila, "Duración Carrera (años)", dur_raw,
                                  "Debe ser un número entero"))
            fila_ok = False
        elif dur_car < 0:
            errores.append(_error("Malla Académica", fila, "Duración Carrera (años)", dur_car,
                                  "No puede ser negativo"))
            fila_ok = False

        if len(inst) > 20:
            errores.append(_error("Malla Académica", fila, "Institución", inst,
                                  "Máximo 20 caracteres"))
            fila_ok = False

        if cod_car and cod_car in carreras:
            prev = carreras[cod_car]
            if nom_car and prev.nombre != nom_car:
                errores.append(_error("Malla Académica", fila, "Nombre Carrera", nom_car,
                    f"Inconsistencia: '{cod_car}' ya fue definida como '{prev.nombre}'"))
                fila_ok = False
        elif cod_car and nom_car and dur_car is not None:
            carreras[cod_car] = CarreraExtraida(cod_car, nom_car, dur_car, inst)

        # ── Año Plan de Estudio ──────────────────────────────────────────
        anio_plan_raw = row.get("Año Plan de Estudio")
        anio_plan = clean_int(anio_plan_raw)
        if anio_plan is None:
            errores.append(_error("Malla Académica", fila, "Año Plan de Estudio", anio_plan_raw,
                                  "Debe ser un número entero"))
            fila_ok = False

        # ── MateriaCarrera (deduplicar por par) ──────────────────────────
        if fila_ok and cod_mat and cod_car and anio_plan is not None:
            mc_key = (cod_mat, cod_car)
            if mc_key not in mc_set:
                mc_set.add(mc_key)
                materia_carreras.append(MateriaCarreraExtraida(cod_mat, cod_car, anio_plan))

        # ── Slot Horario (opcional como grupo) ───────────────────────────
        dia_str = clean_str(row.get("Día de Clase"))
        hi_raw = row.get("Hora Inicio")
        hf_raw = row.get("Hora Fin")
        hi_str = clean_str(hi_raw)
        hf_str = clean_str(hf_raw)

        tiene_horario = bool(dia_str or hi_str or hf_str)

        if tiene_horario:
            dia_num = normalizar_dia(dia_str) if dia_str else None
            hora_i = parse_time_val(hi_raw)
            hora_f = parse_time_val(hf_raw)

            if not dia_str:
                errores.append(_error("Malla Académica", fila, "Día de Clase", "",
                    "Si se define horario, el día es obligatorio"))
                fila_ok = False
            elif dia_num is None:
                errores.append(_error("Malla Académica", fila, "Día de Clase", dia_str,
                    "Día inválido. Use: Lunes, Martes, Miércoles, Jueves, Viernes, Sábado"))
                fila_ok = False

            if not hi_str:
                errores.append(_error("Malla Académica", fila, "Hora Inicio", "",
                    "Si se define horario, la hora de inicio es obligatoria"))
                fila_ok = False
            elif hora_i is None:
                errores.append(_error("Malla Académica", fila, "Hora Inicio", hi_str,
                    "Formato de hora inválido (use HH:MM)"))
                fila_ok = False

            if not hf_str:
                errores.append(_error("Malla Académica", fila, "Hora Fin", "",
                    "Si se define horario, la hora de fin es obligatoria"))
                fila_ok = False
            elif hora_f is None:
                errores.append(_error("Malla Académica", fila, "Hora Fin", hf_str,
                    "Formato de hora inválido (use HH:MM)"))
                fila_ok = False

            if hora_i and hora_f and hora_i >= hora_f:
                errores.append(_error("Malla Académica", fila, "Hora Fin",
                    f"{hora_i} → {hora_f}",
                    "La hora de inicio debe ser anterior a la hora de fin"))
                fila_ok = False

            if fila_ok and dia_num is not None and hora_i and hora_f and cod_mat:
                slot_key = (cod_mat, dia_num, hora_i, hora_f)
                if slot_key not in slot_set:
                    slot_set.add(slot_key)
                    slots.append(SlotExtraido(cod_mat, dia_num, hora_i, hora_f))

        # ── Asignación Docente (opcional) ────────────────────────────────
        dni_doc = clean_str(row.get("DNI Docente"))

        if dni_doc:
            rol_raw = clean_str(row.get("Rol Docente"))
            fi_raw = row.get("Fecha Inicio Asignación")
            ff_raw = row.get("Fecha Fin Asignación")
            fecha_ini = parse_date_val(fi_raw)
            fecha_fin = parse_date_val(ff_raw)

            if dni_doc not in dnis_validos:
                errores.append(_error("Malla Académica", fila, "DNI Docente", dni_doc,
                    "Este DNI no existe en la hoja Docentes ni en la base de datos"))
                fila_ok = False

            rol_norm = _normalizar(rol_raw.upper()) if rol_raw else ""
            if rol_norm not in ROLES_VALIDOS:
                errores.append(_error("Malla Académica", fila, "Rol Docente", rol_raw,
                    "Debe ser 'Titular' o 'Adjunto'"))
                fila_ok = False

            if not fecha_ini:
                errores.append(_error("Malla Académica", fila, "Fecha Inicio Asignación",
                    clean_str(fi_raw),
                    "Obligatoria cuando hay docente asignado (DD/MM/AAAA)"))
                fila_ok = False

            if fila_ok and cod_mat and rol_norm in ROLES_VALIDOS:
                rol_final = ROLES_VALIDOS[rol_norm]
                asig_key = (dni_doc, cod_mat, rol_final)
                if asig_key not in asig_set:
                    asig_set.add(asig_key)
                    asignaciones.append(AsignacionExtraida(
                        dni_doc, cod_mat, rol_final, fecha_ini, fecha_fin,
                    ))

    datos = DatosValidados(
        docentes=[],
        carreras=carreras,
        materias=materias,
        materia_carreras=materia_carreras,
        slots=slots,
        asignaciones=asignaciones,
    )
    return datos, errores


def validar_archivo(
    archivo,
    task_id: str,
) -> tuple[Optional[DatosValidados], list[dict]]:
    """Orquesta la validación completa del archivo Excel."""

    actualizar_progreso(task_id, estado="procesando", fase="validacion",
                        paso="Leyendo archivo Excel…", progreso=5)

    # Leer todas las hojas
    try:
        sheets = pd.read_excel(archivo, sheet_name=None)
    except Exception as e:
        return None, [_error("-", 0, "-", "-", f"No se pudo leer el archivo Excel: {e}")]

    hojas = list(sheets.keys())

    # ── Verificar existencia de hojas ────────────────────────────────────
    err_struct: list[dict] = []
    if "Docentes" not in sheets:
        err_struct.append(_error("-", 0, "-", "-",
            f"Falta la hoja 'Docentes'. Hojas encontradas: {', '.join(hojas)}"))
    if "Malla Académica" not in sheets:
        err_struct.append(_error("-", 0, "-", "-",
            f"Falta la hoja 'Malla Académica'. Hojas encontradas: {', '.join(hojas)}"))
    if err_struct:
        return None, err_struct

    # ── Verificar columnas ───────────────────────────────────────────────
    err_cols = _validar_columnas(sheets["Docentes"], COLUMNAS_DOCENTES, "Docentes")
    err_cols += _validar_columnas(sheets["Malla Académica"], COLUMNAS_MALLA, "Malla Académica")
    if err_cols:
        return None, err_cols

    # ── Validar Docentes ─────────────────────────────────────────────────
    actualizar_progreso(task_id, paso="Validando hoja Docentes…", progreso=15)
    docentes, err_doc = _validar_hoja_docentes(sheets["Docentes"])

    # ── Validar Malla Académica ──────────────────────────────────────────
    actualizar_progreso(task_id, paso="Validando hoja Malla Académica…", progreso=35)
    dnis_excel = {d.username for d in docentes}
    datos_malla, err_malla = _validar_hoja_malla(sheets["Malla Académica"], dnis_excel)

    todos_errores = err_doc + err_malla
    if todos_errores:
        return None, todos_errores

    actualizar_progreso(task_id, paso="Validación completada sin errores", progreso=50)

    datos_malla.docentes = docentes
    return datos_malla, []


# ═══════════════════════════════════════════════════════════════════════════
# FASE 2 — Persistencia (bulk operations)
# ═══════════════════════════════════════════════════════════════════════════

def persistir_datos(
    datos: DatosValidados,
    usuario_creador: Usuario,
    task_id: str,
) -> dict:
    """Persiste todos los datos validados usando operaciones bulk en una
    única transacción atómica."""

    now = timezone.now()
    resumen = {
        "docentes_creados": 0, "docentes_actualizados": 0,
        "carreras_creadas": 0, "carreras_actualizadas": 0,
        "materias_creadas": 0, "materias_actualizadas": 0,
        "horarios_creados": 0,
        "asignaciones_creadas": 0, "asignaciones_actualizadas": 0,
        "materia_carrera_creadas": 0, "materia_carrera_actualizadas": 0,
    }

    with transaction.atomic():

        # ── 1. Usuarios ──────────────────────────────────────────────────
        actualizar_progreso(task_id, fase="persistencia",
                            paso="Guardando usuarios…", progreso=55)

        existing_users = {u.username: u for u in Usuario.objects.all()}
        new_users: list[Usuario] = []
        upd_users_pwd: list[Usuario] = []
        upd_users_nopwd: list[Usuario] = []

        for d in datos.docentes:
            if d.username in existing_users:
                u = existing_users[d.username]
                u.first_name = d.first_name
                u.last_name = d.last_name
                u.email = d.email
                if d.password_explicita:
                    u.password = make_password(d.password_raw)
                    upd_users_pwd.append(u)
                else:
                    upd_users_nopwd.append(u)
            else:
                new_users.append(Usuario(
                    username=d.username,
                    first_name=d.first_name,
                    last_name=d.last_name,
                    email=d.email,
                    password=make_password(d.password_raw),
                ))

        if new_users:
            created = Usuario.objects.bulk_create(new_users)
            for u in created:
                existing_users[u.username] = u
        resumen["docentes_creados"] = len(new_users)

        if upd_users_pwd:
            Usuario.objects.bulk_update(upd_users_pwd,
                ["first_name", "last_name", "email", "password"])
        if upd_users_nopwd:
            Usuario.objects.bulk_update(upd_users_nopwd,
                ["first_name", "last_name", "email"])
        resumen["docentes_actualizados"] = len(upd_users_pwd) + len(upd_users_nopwd)

        # ── 2. Perfiles Docente ──────────────────────────────────────────
        actualizar_progreso(task_id, paso="Guardando perfiles docentes…", progreso=60)

        existing_docentes = {
            d.user_id: d for d in Docente.objects.all()
        }
        new_docentes: list[Docente] = []
        for d in datos.docentes:
            user = existing_users[d.username]
            if user.id not in existing_docentes:
                new_docentes.append(Docente(
                    user=user, activo=True,
                    creado_por=usuario_creador,
                    modificado_por=usuario_creador,
                ))

        if new_docentes:
            Docente.objects.bulk_create(new_docentes)

        # Refrescar caché de docentes (incluye los nuevos)
        docentes_dict: dict[str, Docente] = {
            d.user.username: d
            for d in Docente.objects.select_related("user").all()
        }

        # ── 3. Carreras (upsert) ────────────────────────────────────────
        actualizar_progreso(task_id, paso="Guardando carreras…", progreso=65)

        carreras_antes = Carrera.objects.count()
        carrera_objs = [
            Carrera(
                codigo=c.codigo, nombre=c.nombre,
                duracion_anios=c.duracion_anios, institucion=c.institucion,
                creado_por=usuario_creador, modificado_por=usuario_creador,
                modificado_en=now,
            )
            for c in datos.carreras.values()
        ]
        if carrera_objs:
            Carrera.objects.bulk_create(
                carrera_objs,
                update_conflicts=True,
                unique_fields=["codigo"],
                update_fields=["nombre", "duracion_anios", "institucion",
                               "modificado_por", "modificado_en"],
            )
        carreras_despues = Carrera.objects.count()
        resumen["carreras_creadas"] = carreras_despues - carreras_antes
        resumen["carreras_actualizadas"] = len(carrera_objs) - resumen["carreras_creadas"]

        carreras_db = {c.codigo: c for c in Carrera.objects.all()}

        # ── 4. Materias (upsert) ─────────────────────────────────────────
        actualizar_progreso(task_id, paso="Guardando materias…", progreso=72)

        materias_antes = Materia.objects.count()
        materia_objs = [
            Materia(
                codigo_siu=m.codigo_siu, nombre=m.nombre,
                anio=m.anio, activa=True,
                creado_por=usuario_creador, modificado_por=usuario_creador,
                modificado_en=now,
            )
            for m in datos.materias.values()
        ]
        if materia_objs:
            Materia.objects.bulk_create(
                materia_objs,
                update_conflicts=True,
                unique_fields=["codigo_siu"],
                update_fields=["nombre", "anio", "activa",
                               "modificado_por", "modificado_en"],
            )
        materias_despues = Materia.objects.count()
        resumen["materias_creadas"] = materias_despues - materias_antes
        resumen["materias_actualizadas"] = len(materia_objs) - resumen["materias_creadas"]

        materias_db = {m.codigo_siu: m for m in Materia.objects.all()}

        # ── 5. MateriaCarrera (upsert) ───────────────────────────────────
        actualizar_progreso(task_id, paso="Guardando relaciones materia-carrera…", progreso=78)

        mc_antes = MateriaCarrera.objects.count()
        mc_objs = []
        for mc in datos.materia_carreras:
            mat = materias_db.get(mc.codigo_materia)
            car = carreras_db.get(mc.codigo_carrera)
            if mat and car:
                mc_objs.append(MateriaCarrera(
                    materia=mat, carrera=car, anio_plan=mc.anio_plan,
                    creado_por=usuario_creador, modificado_por=usuario_creador,
                    modificado_en=now,
                ))
        if mc_objs:
            MateriaCarrera.objects.bulk_create(
                mc_objs,
                update_conflicts=True,
                unique_fields=["materia", "carrera"],
                update_fields=["anio_plan", "modificado_por", "modificado_en"],
            )
        mc_despues = MateriaCarrera.objects.count()
        resumen["materia_carrera_creadas"] = mc_despues - mc_antes
        resumen["materia_carrera_actualizadas"] = len(mc_objs) - resumen["materia_carrera_creadas"]

        # ── 6. SlotHorario (solo crear nuevos) ───────────────────────────
        actualizar_progreso(task_id, paso="Guardando horarios…", progreso=85)

        existing_slots = {
            (s.materia_id, s.dia_semana, s.hora_inicio, s.hora_fin): s
            for s in SlotHorario.objects.filter(valido_hasta__isnull=True)
        }
        new_slots: list[SlotHorario] = []
        for sl in datos.slots:
            mat = materias_db.get(sl.codigo_materia)
            if mat:
                key = (mat.id, sl.dia_semana, sl.hora_inicio, sl.hora_fin)
                if key not in existing_slots:
                    new_slots.append(SlotHorario(
                        materia=mat,
                        dia_semana=sl.dia_semana,
                        hora_inicio=sl.hora_inicio,
                        hora_fin=sl.hora_fin,
                        valido_desde=now.date(),
                        creado_por=usuario_creador,
                        modificado_por=usuario_creador,
                    ))
        if new_slots:
            SlotHorario.objects.bulk_create(new_slots)
        resumen["horarios_creados"] = len(new_slots)

        # ── 7. AsignacionDocente (upsert manual) ─────────────────────────
        actualizar_progreso(task_id, paso="Guardando asignaciones…", progreso=92)

        existing_asig: dict[tuple, AsignacionDocente] = {}
        for a in AsignacionDocente.objects.select_related("docente__user", "materia").all():
            key = (a.docente.user.username, a.materia.codigo_siu, a.rol)
            existing_asig[key] = a

        new_asig: list[AsignacionDocente] = []
        upd_asig: list[AsignacionDocente] = []
        for asig in datos.asignaciones:
            doc = docentes_dict.get(asig.username_docente)
            mat = materias_db.get(asig.codigo_materia)
            if doc and mat:
                key = (asig.username_docente, asig.codigo_materia, asig.rol)
                if key in existing_asig:
                    ea = existing_asig[key]
                    ea.fecha_inicio = asig.fecha_inicio
                    ea.fecha_fin = asig.fecha_fin
                    ea.activa = True
                    ea.modificado_por = usuario_creador
                    ea.modificado_en = now
                    upd_asig.append(ea)
                else:
                    new_asig.append(AsignacionDocente(
                        docente=doc, materia=mat, rol=asig.rol,
                        fecha_inicio=asig.fecha_inicio,
                        fecha_fin=asig.fecha_fin,
                        activa=True,
                        creado_por=usuario_creador,
                        modificado_por=usuario_creador,
                    ))

        if new_asig:
            AsignacionDocente.objects.bulk_create(new_asig)
        if upd_asig:
            AsignacionDocente.objects.bulk_update(
                upd_asig,
                ["fecha_inicio", "fecha_fin", "activa",
                 "modificado_por", "modificado_en"],
            )
        resumen["asignaciones_creadas"] = len(new_asig)
        resumen["asignaciones_actualizadas"] = len(upd_asig)

    return resumen


# ═══════════════════════════════════════════════════════════════════════════
# Orquestador — corre en hilo de fondo
# ═══════════════════════════════════════════════════════════════════════════

def procesar_importacion(archivo, user_id: int, task_id: str):
    """Función principal de importación.  Se ejecuta en un hilo daemon
    lanzado por el endpoint API.

    Coordina Fase 1 (validación) → Fase 2 (persistencia) y reporta
    progreso al almacén en memoria que el SSE consume.
    """
    try:
        actualizar_progreso(
            task_id, estado="procesando", fase="validacion",
            paso="Iniciando importación…", progreso=2,
        )

        # ── Fase 1 ──────────────────────────────────────────────────────
        datos, errores = validar_archivo(archivo, task_id)

        if errores:
            error_validacion_tarea(task_id, errores)
            return

        if datos is None:
            error_sistema_tarea(task_id, "Error desconocido durante la validación")
            return

        # ── Fase 2 ──────────────────────────────────────────────────────
        actualizar_progreso(
            task_id, fase="persistencia",
            paso="Iniciando guardado en base de datos…", progreso=52,
        )

        usuario = Usuario.objects.get(id=user_id)
        resumen = persistir_datos(datos, usuario, task_id)
        resumen["success"] = True

        completar_tarea(task_id, resumen)

    except Exception as e:
        logger.exception("Error inesperado en importación SIU (task_id=%s)", task_id)
        error_sistema_tarea(task_id, f"Error inesperado del sistema: {e}")
    finally:
        connection.close()