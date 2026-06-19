"""
Tests para el módulo de importación SIU refactorizado.

Cubren:
  - Importación exitosa completa (2 hojas).
  - Errores de validación (campos faltantes, DNI duplicado, inconsistencias).
  - Referencias cruzadas entre hojas.
  - Re-importación (upsert) de datos existentes.
  - Generación de plantilla Excel.
"""
import io
from datetime import date, time

import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase

from academico.models import Carrera, Materia, MateriaCarrera, SlotHorario
from asignaciones.models import AsignacionDocente
from usuarios.models import Docente, Usuario

from importacion.plantilla import generar_plantilla_excel
from importacion.progress import crear_tarea
from importacion.services import persistir_datos, validar_archivo


def _crear_excel(df_docentes: pd.DataFrame, df_malla: pd.DataFrame) -> io.BytesIO:
    """Genera un archivo Excel en memoria con las 2 hojas requeridas."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_docentes.to_excel(writer, sheet_name="Docentes", index=False)
        df_malla.to_excel(writer, sheet_name="Malla Académica", index=False)
    buf.seek(0)
    return buf


class ImportacionExitosaTest(TestCase):
    """Verifica que una importación válida cree todos los registros."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="secretario_test", email="sec@ices.edu.ar", password="pass"
        )
        self.task_id = crear_tarea()

    def test_importacion_completa(self):
        df_doc = pd.DataFrame([
            {"DNI": "40111222", "Nombre": "Juan", "Apellido": "Pérez",
             "Email": "juan@ices.edu.ar", "Contraseña": ""},
            {"DNI": "40333444", "Nombre": "María", "Apellido": "Gómez",
             "Email": "maria@ices.edu.ar", "Contraseña": "MiClave"},
        ])

        df_malla = pd.DataFrame([
            {"Código Materia SIU": "MAT01", "Nombre Materia": "Matemática I",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "Tecnicatura en Programación",
             "Duración Carrera (años)": 3, "Año Plan de Estudio": 1,
             "Día de Clase": "Lunes", "Hora Inicio": "08:00", "Hora Fin": "10:00",
             "DNI Docente": "40111222", "Rol Docente": "Titular",
             "Fecha Inicio Asignación": "01/03/2026", "Fecha Fin Asignación": "31/12/2026"},
            {"Código Materia SIU": "PROG1", "Nombre Materia": "Programación I",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "Tecnicatura en Programación",
             "Duración Carrera (años)": 3, "Año Plan de Estudio": 1,
             "Día de Clase": "Martes", "Hora Inicio": "14:30", "Hora Fin": "17:30",
             "DNI Docente": "40333444", "Rol Docente": "Adjunto",
             "Fecha Inicio Asignación": "01/03/2026", "Fecha Fin Asignación": ""},
        ])

        excel = _crear_excel(df_doc, df_malla)

        # Fase 1 — Validación
        datos, errores = validar_archivo(excel, self.task_id)
        self.assertEqual(errores, [])
        self.assertIsNotNone(datos)

        # Fase 2 — Persistencia
        resumen = persistir_datos(datos, self.usuario, self.task_id)

        self.assertEqual(resumen["docentes_creados"], 2)
        self.assertEqual(resumen["carreras_creadas"], 1)
        self.assertEqual(resumen["materias_creadas"], 2)
        self.assertEqual(resumen["horarios_creados"], 2)
        self.assertEqual(resumen["asignaciones_creadas"], 2)
        self.assertEqual(resumen["materia_carrera_creadas"], 2)

        # Verificar en BD
        self.assertEqual(Carrera.objects.count(), 1)
        self.assertEqual(Materia.objects.count(), 2)
        self.assertEqual(MateriaCarrera.objects.count(), 2)
        self.assertEqual(SlotHorario.objects.count(), 2)
        self.assertEqual(AsignacionDocente.objects.count(), 2)
        self.assertEqual(Docente.objects.count(), 2)
        # 2 docentes + 1 secretario
        self.assertEqual(Usuario.objects.count(), 3)

        # Contraseña: DNI por defecto
        u1 = Usuario.objects.get(username="40111222")
        self.assertTrue(u1.check_password("40111222"))
        # Contraseña: explícita
        u2 = Usuario.objects.get(username="40333444")
        self.assertTrue(u2.check_password("MiClave"))


class ImportacionSinHorarioNiDocenteTest(TestCase):
    """Filas sin horario ni docente (solo materia-carrera)."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="sec", email="s@i.ar", password="p"
        )
        self.task_id = crear_tarea()

    def test_sin_horario_ni_docente(self):
        df_doc = pd.DataFrame([
            {"DNI": "10000001", "Nombre": "A", "Apellido": "B",
             "Email": "", "Contraseña": ""},
        ])

        df_malla = pd.DataFrame([
            {"Código Materia SIU": "MAT01", "Nombre Materia": "Mate",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "TPI carrera", "Duración Carrera (años)": 3,
             "Año Plan de Estudio": 1,
             "Día de Clase": "", "Hora Inicio": "", "Hora Fin": "",
             "DNI Docente": "", "Rol Docente": "",
             "Fecha Inicio Asignación": "", "Fecha Fin Asignación": ""},
        ])

        datos, errores = validar_archivo(_crear_excel(df_doc, df_malla), self.task_id)
        self.assertEqual(errores, [])
        resumen = persistir_datos(datos, self.usuario, self.task_id)
        self.assertEqual(resumen["horarios_creados"], 0)
        self.assertEqual(resumen["asignaciones_creadas"], 0)
        self.assertEqual(resumen["materias_creadas"], 1)
        self.assertEqual(resumen["materia_carrera_creadas"], 1)


class ValidacionErroresTest(TestCase):
    """Verifica que la validación detecte múltiples tipos de errores."""

    def setUp(self):
        self.task_id = crear_tarea()

    def test_campos_obligatorios_faltantes(self):
        df_doc = pd.DataFrame([
            {"DNI": "", "Nombre": "Juan", "Apellido": "P",
             "Email": "", "Contraseña": ""},
        ])
        df_malla = pd.DataFrame([
            {"Código Materia SIU": "", "Nombre Materia": "",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "TPI", "Duración Carrera (años)": 3,
             "Año Plan de Estudio": 1,
             "Día de Clase": "", "Hora Inicio": "", "Hora Fin": "",
             "DNI Docente": "", "Rol Docente": "",
             "Fecha Inicio Asignación": "", "Fecha Fin Asignación": ""},
        ])

        datos, errores = validar_archivo(_crear_excel(df_doc, df_malla), self.task_id)
        self.assertIsNone(datos)
        self.assertGreater(len(errores), 0)

        columnas_error = {e["columna"] for e in errores}
        self.assertIn("DNI", columnas_error)
        self.assertIn("Código Materia SIU", columnas_error)

    def test_dni_duplicado(self):
        df_doc = pd.DataFrame([
            {"DNI": "40111222", "Nombre": "A", "Apellido": "B",
             "Email": "", "Contraseña": ""},
            {"DNI": "40111222", "Nombre": "C", "Apellido": "D",
             "Email": "", "Contraseña": ""},
        ])
        df_malla = pd.DataFrame([
            {"Código Materia SIU": "M1", "Nombre Materia": "Mat",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "TPI", "Duración Carrera (años)": 3,
             "Año Plan de Estudio": 1,
             "Día de Clase": "", "Hora Inicio": "", "Hora Fin": "",
             "DNI Docente": "", "Rol Docente": "",
             "Fecha Inicio Asignación": "", "Fecha Fin Asignación": ""},
        ])

        datos, errores = validar_archivo(_crear_excel(df_doc, df_malla), self.task_id)
        self.assertIsNone(datos)
        dup_errors = [e for e in errores if "duplicado" in e["mensaje"].lower()]
        self.assertEqual(len(dup_errors), 1)

    def test_inconsistencia_materia(self):
        df_doc = pd.DataFrame([
            {"DNI": "10000001", "Nombre": "A", "Apellido": "B",
             "Email": "", "Contraseña": ""},
        ])
        df_malla = pd.DataFrame([
            {"Código Materia SIU": "MAT01", "Nombre Materia": "Matemática I",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "TPI", "Duración Carrera (años)": 3,
             "Año Plan de Estudio": 1,
             "Día de Clase": "", "Hora Inicio": "", "Hora Fin": "",
             "DNI Docente": "", "Rol Docente": "",
             "Fecha Inicio Asignación": "", "Fecha Fin Asignación": ""},
            {"Código Materia SIU": "MAT01", "Nombre Materia": "Otro nombre",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "TPI", "Duración Carrera (años)": 3,
             "Año Plan de Estudio": 1,
             "Día de Clase": "", "Hora Inicio": "", "Hora Fin": "",
             "DNI Docente": "", "Rol Docente": "",
             "Fecha Inicio Asignación": "", "Fecha Fin Asignación": ""},
        ])

        datos, errores = validar_archivo(_crear_excel(df_doc, df_malla), self.task_id)
        self.assertIsNone(datos)
        inc_errors = [e for e in errores if "inconsistencia" in e["mensaje"].lower()]
        self.assertGreater(len(inc_errors), 0)

    def test_referencia_cruzada_dni_inexistente(self):
        df_doc = pd.DataFrame([
            {"DNI": "10000001", "Nombre": "A", "Apellido": "B",
             "Email": "", "Contraseña": ""},
        ])
        df_malla = pd.DataFrame([
            {"Código Materia SIU": "M1", "Nombre Materia": "Mat",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "TPI", "Duración Carrera (años)": 3,
             "Año Plan de Estudio": 1,
             "Día de Clase": "Lunes", "Hora Inicio": "08:00", "Hora Fin": "10:00",
             "DNI Docente": "99999999", "Rol Docente": "Titular",
             "Fecha Inicio Asignación": "01/03/2026", "Fecha Fin Asignación": ""},
        ])

        datos, errores = validar_archivo(_crear_excel(df_doc, df_malla), self.task_id)
        self.assertIsNone(datos)
        ref_errors = [e for e in errores if "no existe" in e["mensaje"].lower()]
        self.assertGreater(len(ref_errors), 0)

    def test_hora_inicio_mayor_a_fin(self):
        df_doc = pd.DataFrame([
            {"DNI": "10000001", "Nombre": "A", "Apellido": "B",
             "Email": "", "Contraseña": ""},
        ])
        df_malla = pd.DataFrame([
            {"Código Materia SIU": "M1", "Nombre Materia": "Mat",
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "TPI", "Duración Carrera (años)": 3,
             "Año Plan de Estudio": 1,
             "Día de Clase": "Lunes", "Hora Inicio": "14:00", "Hora Fin": "10:00",
             "DNI Docente": "", "Rol Docente": "",
             "Fecha Inicio Asignación": "", "Fecha Fin Asignación": ""},
        ])

        datos, errores = validar_archivo(_crear_excel(df_doc, df_malla), self.task_id)
        self.assertIsNone(datos)
        time_errors = [e for e in errores if "anterior" in e["mensaje"].lower()]
        self.assertGreater(len(time_errors), 0)

    def test_hoja_faltante(self):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="OtraHoja", index=False)
        buf.seek(0)

        datos, errores = validar_archivo(buf, self.task_id)
        self.assertIsNone(datos)
        self.assertGreater(len(errores), 0)
        self.assertTrue(any("Docentes" in e["mensaje"] for e in errores))


class ReimportacionUpsertTest(TestCase):
    """Verifica que una segunda importación actualice en vez de duplicar."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="sec", email="s@i.ar", password="p"
        )
        self.task_id = crear_tarea()

    def _build_excel(self, nombre_materia="Matemática I"):
        df_doc = pd.DataFrame([
            {"DNI": "40111222", "Nombre": "Juan", "Apellido": "Pérez",
             "Email": "juan@ices.edu.ar", "Contraseña": ""},
        ])
        df_malla = pd.DataFrame([
            {"Código Materia SIU": "MAT01", "Nombre Materia": nombre_materia,
             "Año Cursado": 1, "Institución": "ICES", "Código Carrera": "TPI",
             "Nombre Carrera": "Tecnicatura en Programación",
             "Duración Carrera (años)": 3, "Año Plan de Estudio": 1,
             "Día de Clase": "Lunes", "Hora Inicio": "08:00", "Hora Fin": "10:00",
             "DNI Docente": "40111222", "Rol Docente": "Titular",
             "Fecha Inicio Asignación": "01/03/2026", "Fecha Fin Asignación": ""},
        ])
        return _crear_excel(df_doc, df_malla)

    def test_segunda_importacion_no_duplica(self):
        # Primera importación
        task1 = crear_tarea()
        datos1, _ = validar_archivo(self._build_excel(), task1)
        persistir_datos(datos1, self.usuario, task1)

        self.assertEqual(Materia.objects.count(), 1)
        self.assertEqual(Docente.objects.count(), 1)

        # Segunda importación con nombre actualizado
        task2 = crear_tarea()
        datos2, _ = validar_archivo(self._build_excel("Matemática I (Actualizada)"), task2)
        resumen = persistir_datos(datos2, self.usuario, task2)

        # No se crearon nuevos — se actualizaron
        self.assertEqual(resumen["materias_creadas"], 0)
        self.assertEqual(resumen["materias_actualizadas"], 1)
        self.assertEqual(resumen["docentes_actualizados"], 1)

        # BD sigue con 1 registro de cada uno
        self.assertEqual(Materia.objects.count(), 1)
        self.assertEqual(Docente.objects.count(), 1)

        # Nombre actualizado
        self.assertEqual(
            Materia.objects.get(codigo_siu="MAT01").nombre,
            "Matemática I (Actualizada)",
        )


class PlantillaExcelTest(TestCase):
    """Verifica que la plantilla se genere correctamente."""

    def test_generar_plantilla(self):
        buf = generar_plantilla_excel()
        self.assertIsNotNone(buf)
        self.assertGreater(len(buf.getvalue()), 0)

        # Verificar que tiene las hojas correctas
        sheets = pd.read_excel(buf, sheet_name=None)
        self.assertIn("Instrucciones", sheets)
        self.assertIn("Docentes", sheets)
        self.assertIn("Malla Académica", sheets)

        # Verificar columnas de Docentes
        doc_cols = list(sheets["Docentes"].columns)
        self.assertIn("DNI", doc_cols)
        self.assertIn("Nombre", doc_cols)

        # Verificar columnas de Malla
        malla_cols = list(sheets["Malla Académica"].columns)
        self.assertIn("Código Materia SIU", malla_cols)
        self.assertIn("DNI Docente", malla_cols)
