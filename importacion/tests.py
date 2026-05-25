import io
import pandas as pd
from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date, time

from usuarios.models import Usuario, Docente
from academico.models import Carrera, Materia, MateriaCarrera, SlotHorario
from asignaciones.models import AsignacionDocente
from importacion.services import procesar_archivo_siu

class ImportacionSIUTestCase(TestCase):
    def setUp(self):
        self.usuario_creador = get_user_model().objects.create_user(
            username='secretario_test',
            email='test@ices.edu.ar',
            password='password123'
        )

    def test_importacion_exitosa(self):
        # 1. Crear data para excel
        df_carreras = pd.DataFrame([
            {'codigo': 'TPI', 'nombre': 'Tecnicatura en Programación', 'duracion_anios': 3},
            {'codigo': 'TUI', 'nombre': 'Tecnicatura en Informática', 'duracion_anios': 2}
        ])
        
        df_docentes = pd.DataFrame([
            {'username': '40111222', 'nombre': 'Juan', 'apellido': 'Perez', 'email': 'juan@ices.edu.ar'},
            {'username': '40333444', 'nombre': 'Maria', 'apellido': 'Gomez', 'email': 'maria@ices.edu.ar'}
        ])
        
        df_materias = pd.DataFrame([
            {'codigo_siu': 'MAT01', 'nombre': 'Matemática I', 'anio': 2026},
            {'codigo_siu': 'PROG1', 'nombre': 'Programación I', 'anio': 2026}
        ])
        
        df_materia_carrera = pd.DataFrame([
            {'codigo_materia': 'MAT01', 'codigo_carrera': 'TPI', 'anio_plan': 1},
            {'codigo_materia': 'PROG1', 'codigo_carrera': 'TPI', 'anio_plan': 1}
        ])
        
        df_horarios = pd.DataFrame([
            {'codigo_materia': 'MAT01', 'dia_semana': 0, 'hora_inicio': '08:00', 'hora_fin': '10:00'},
            {'codigo_materia': 'PROG1', 'dia_semana': 1, 'hora_inicio': '14:30', 'hora_fin': '17:30'}
        ])
        
        df_asignaciones = pd.DataFrame([
            {'username_docente': '40111222', 'codigo_materia': 'MAT01', 'rol': 'Titular', 'fecha_inicio': '2026-03-01', 'fecha_fin': '2026-12-31'},
            {'username_docente': '40333444', 'codigo_materia': 'PROG1', 'rol': 'Adjunto', 'fecha_inicio': '2026-03-01', 'fecha_fin': ''}
        ])

        # Crear Excel en memoria
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_carreras.to_excel(writer, sheet_name='01_Carreras', index=False)
            df_docentes.to_excel(writer, sheet_name='05_Docentes', index=False)
            df_materias.to_excel(writer, sheet_name='02_Materias', index=False)
            df_materia_carrera.to_excel(writer, sheet_name='03_MateriaCarrera', index=False)
            df_horarios.to_excel(writer, sheet_name='04_Horarios', index=False)
            df_asignaciones.to_excel(writer, sheet_name='06_AsignacionesDocentes', index=False)
        
        excel_buffer.seek(0)
        
        # Procesar
        resumen = procesar_archivo_siu(excel_buffer, self.usuario_creador)
        
        # Verificaciones del resumen
        self.assertTrue(resumen['success'])
        self.assertEqual(resumen['carreras_creadas'], 2)
        self.assertEqual(resumen['docentes_creados'], 2)
        self.assertEqual(resumen['materias_creadas'], 2)
        self.assertEqual(resumen['horarios_creados'], 2)
        self.assertEqual(resumen['asignaciones_creadas'], 2)
        self.assertEqual(len(resumen['errores']), 0)
        
        # Verificaciones en Base de Datos
        self.assertEqual(Carrera.objects.count(), 2)
        self.assertEqual(Usuario.objects.filter(is_superuser=False).count(), 3) # 2 importados + 1 creador
        self.assertEqual(Docente.objects.count(), 2)
        self.assertEqual(Materia.objects.count(), 2)
        self.assertEqual(MateriaCarrera.objects.count(), 2)
        self.assertEqual(SlotHorario.objects.count(), 2)
        self.assertEqual(AsignacionDocente.objects.count(), 2)
        
        # Verificar auditoría y hashing de contraseña de docente
        doc_usr = Usuario.objects.get(username='40111222')
        self.assertTrue(doc_usr.check_password('40111222'))
        self.assertEqual(doc_usr.first_name, 'Juan')
        self.assertEqual(doc_usr.last_name, 'Perez')
        
        doc = Docente.objects.get(user=doc_usr)
        self.assertEqual(doc.creado_por, self.usuario_creador)
        
        materia_mat = Materia.objects.get(codigo_siu='MAT01')
        self.assertEqual(materia_mat.creado_por, self.usuario_creador)

    def test_importacion_con_errores_tolerancia(self):
        # 1. Crear data para excel, algunas filas tienen errores intencionales
        df_carreras = pd.DataFrame([
            {'codigo': 'TPI', 'nombre': 'Tecnicatura en Programación', 'duracion_anios': 3},
            {'codigo': '', 'nombre': 'Carrera Incompleta Sin Código', 'duracion_anios': 2} # Error: sin codigo
        ])
        
        df_docentes = pd.DataFrame([
            {'username': '40111222', 'first_name': 'Juan', 'last_name': 'Perez', 'email': 'juan@ices.edu.ar'},
            {'username': '', 'first_name': 'Sin', 'last_name': 'DNI', 'email': 'sindni@ices.edu.ar'} # Error: sin username
        ])
        
        df_materias = pd.DataFrame([
            {'codigo_siu': 'MAT01', 'nombre': 'Matemática I', 'anio': 2026},
            {'codigo_siu': 'PROG1', 'nombre': 'Programación I', 'anio': 'invalido'} # Error: anio invalido
        ])
        
        df_materia_carrera = pd.DataFrame([
            {'codigo_materia': 'MAT01', 'codigo_carrera': 'TPI', 'anio_plan': 1},
            {'codigo_materia': 'NO_EXISTE', 'codigo_carrera': 'TPI', 'anio_plan': 1} # Error: materia inexistente
        ])
        
        df_horarios = pd.DataFrame([
            {'codigo_materia': 'MAT01', 'dia_semana': 0, 'hora_inicio': '08:00', 'hora_fin': '10:00'},
            {'codigo_materia': 'MAT01', 'dia_semana': 0, 'hora_inicio': '12:00', 'hora_fin': '10:00'} # Error: hora_inicio >= hora_fin
        ])
        
        df_asignaciones = pd.DataFrame([
            {'username_docente': '40111222', 'codigo_materia': 'MAT01', 'rol': 'Titular', 'fecha_inicio': '2026-03-01', 'fecha_fin': '2026-12-31'},
            {'username_docente': 'NO_EXISTE_DNI', 'codigo_materia': 'MAT01', 'rol': 'Adjunto', 'fecha_inicio': '2026-03-01', 'fecha_fin': ''} # Error: docente inexistente
        ])

        # Crear Excel en memoria
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_carreras.to_excel(writer, sheet_name='01_Carreras', index=False)
            df_docentes.to_excel(writer, sheet_name='05_Docentes', index=False)
            df_materias.to_excel(writer, sheet_name='02_Materias', index=False)
            df_materia_carrera.to_excel(writer, sheet_name='03_MateriaCarrera', index=False)
            df_horarios.to_excel(writer, sheet_name='04_Horarios', index=False)
            df_asignaciones.to_excel(writer, sheet_name='06_AsignacionesDocentes', index=False)
        
        excel_buffer.seek(0)
        
        # Procesar
        resumen = procesar_archivo_siu(excel_buffer, self.usuario_creador)
        
        # Verificaciones del resumen
        self.assertFalse(resumen['success'])
        self.assertEqual(resumen['carreras_creadas'], 1)
        self.assertEqual(resumen['docentes_creados'], 1)
        self.assertEqual(resumen['materias_creadas'], 1)
        self.assertEqual(resumen['horarios_creados'], 1)
        self.assertEqual(resumen['asignaciones_creadas'], 1)
        
        # Deberíamos tener exactamente 6 errores en total (uno por cada fila fallida)
        self.assertEqual(len(resumen['errores']), 6)
        
        # Verificar que se crearon los válidos
        self.assertEqual(Carrera.objects.filter(codigo='TPI').count(), 1)
        self.assertEqual(Docente.objects.filter(user__username='40111222').count(), 1)
        self.assertEqual(Materia.objects.filter(codigo_siu='MAT01').count(), 1)
        self.assertEqual(MateriaCarrera.objects.filter(materia__codigo_siu='MAT01', carrera__codigo='TPI').count(), 1)
        self.assertEqual(SlotHorario.objects.filter(materia__codigo_siu='MAT01', dia_semana=0, hora_inicio=time(8, 0)).count(), 1)
        self.assertEqual(AsignacionDocente.objects.filter(docente__user__username='40111222', materia__codigo_siu='MAT01').count(), 1)
