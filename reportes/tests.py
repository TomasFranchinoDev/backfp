from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date, time
from usuarios.models import Docente, Secretario
from academico.models import Carrera, Materia, MateriaCarrera, SlotHorario
from asignaciones.models import AsignacionDocente
from asistencia.models import RegistroAsistencia
from calendario.models import EventoCalendario
from reportes.services import calcular_ausencias_dinamicas

class ReportesTestCase(TestCase):
    def setUp(self):
        # 1. User/Secretario
        self.secretario = get_user_model().objects.create_user(
            username='secretario',
            email='secre@ices.edu.ar',
            password='password123'
        )
        self.secretario_profile = Secretario.objects.create(
            user=self.secretario,
            activo=True
        )

        # 2. Docente
        self.user_docente = get_user_model().objects.create_user(
            username='40111222',
            email='docente@ices.edu.ar',
            first_name='Juan',
            last_name='Perez',
            password='password123'
        )
        self.docente = Docente.objects.create(
            user=self.user_docente,
            creado_por=self.secretario
        )

        # 3. Carrera y Materia
        self.carrera = Carrera.objects.create(
            codigo='TPI',
            nombre='Tecnicatura en Programación',
            duracion_anios=3,
            creado_por=self.secretario
        )
        self.materia = Materia.objects.create(
            codigo_siu='MAT01',
            nombre='Matemática I',
            anio=2026,
            creado_por=self.secretario
        )
        self.materia_carrera = MateriaCarrera.objects.create(
            materia=self.materia,
            carrera=self.carrera,
            anio_plan=1,
            creado_por=self.secretario
        )

        # 4. Slot de Horario - Lunes (weekday 0)
        # En mayo 2026 los lunes son: 4, 11, 18, 25.
        self.slot = SlotHorario.objects.create(
            materia=self.materia,
            dia_semana=0,
            hora_inicio=time(8, 0),
            hora_fin=time(10, 0),
            creado_por=self.secretario
        )

        # 5. Asignacion Docente activa en mayo 2026
        self.asignacion = AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.materia,
            rol='Titular',
            activa=True,
            fecha_inicio=date(2026, 5, 1),
            fecha_fin=date(2026, 5, 31),
            creado_por=self.secretario
        )

    def test_reporte_mensual_basico_sin_asistencias(self):
        # En mayo de 2026 hay 4 lunes: 4, 11, 18, 25.
        # Sin ningún registro de asistencia, debería haber 4 clases esperadas y 4 ausencias.
        res = calcular_ausencias_dinamicas(mes=5, anio=2026, agrupar_por='docente')
        
        self.assertIn(self.docente.id, res)
        doc_res = res[self.docente.id]
        self.assertEqual(doc_res['nombre'], 'Juan Perez')
        self.assertEqual(doc_res['esperadas'], 4)
        self.assertEqual(doc_res['asistencias'], 0)
        self.assertEqual(len(doc_res['ausencias']), 4)
        
        # Todas deben ser ausencias normales (sin evento_calendario)
        for aus in doc_res['ausencias']:
            self.assertIsNone(aus['evento_calendario'])

    def test_reporte_mensual_con_asistencia_parcial(self):
        # Registrar asistencia para el lunes 4 de mayo
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=date(2026, 5, 4),
            anio=2026,
            tipo_clase='Presencial',
            creado_por=self.secretario
        )
        
        # Ahora debería haber 4 esperadas, 1 asistencia, 3 ausencias.
        res = calcular_ausencias_dinamicas(mes=5, anio=2026, agrupar_por='docente')
        doc_res = res[self.docente.id]
        self.assertEqual(doc_res['esperadas'], 4)
        self.assertEqual(doc_res['asistencias'], 1)
        self.assertEqual(len(doc_res['ausencias']), 3)

    def test_reporte_mensual_con_feriado(self):
        # Crear feriado el lunes 25 de mayo (Día de la Revolución de Mayo)
        EventoCalendario.objects.create(
            fecha=date(2026, 5, 25),
            descripcion='Día de la Revolución de Mayo',
            creado_por=self.secretario
        )
        
        # Registrar asistencia el lunes 4
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=date(2026, 5, 4),
            anio=2026,
            tipo_clase='Presencial',
            creado_por=self.secretario
        )
        
        # Lunes en mayo 2026: 4, 11, 18, 25.
        # - 4: Asistió (esperada +1, asistencia +1)
        # - 11: No asistió (esperada +1, ausencia normal +1)
        # - 18: No asistió (esperada +1, ausencia normal +1)
        # - 25: Feriado, no asistió (esperada 0, asistencia 0, ausencia feriado +1)
        # Totales esperados: esperadas = 3, asistencias = 1, ausencias = 3 (pero 1 es feriado).
        res = calcular_ausencias_dinamicas(mes=5, anio=2026, agrupar_por='docente')
        doc_res = res[self.docente.id]
        
        self.assertEqual(doc_res['esperadas'], 3)
        self.assertEqual(doc_res['asistencias'], 1)
        self.assertEqual(len(doc_res['ausencias']), 3)
        
        # Verificar que el feriado esté en el detalle con su advertencia
        aus_feriado = [a for a in doc_res['ausencias'] if a['fecha'] == date(2026, 5, 25)][0]
        self.assertEqual(aus_feriado['evento_calendario'], 'Día de la Revolución de Mayo')
        
        # Las otras dos deben no tener evento
        aus_normales = [a for a in doc_res['ausencias'] if a['fecha'] != date(2026, 5, 25)]
        self.assertEqual(len(aus_normales), 2)
        for aus in aus_normales:
            self.assertIsNone(aus['evento_calendario'])

    def test_reporte_agrupado_por_carrera_y_materia(self):
        # Reporte por carrera
        res_carrera = calcular_ausencias_dinamicas(mes=5, anio=2026, agrupar_por='carrera')
        self.assertIn(self.carrera.id, res_carrera)
        self.assertEqual(res_carrera[self.carrera.id]['nombre'], 'Tecnicatura en Programación')
        self.assertEqual(res_carrera[self.carrera.id]['codigo'], 'TPI')
        self.assertEqual(res_carrera[self.carrera.id]['esperadas'], 4)
        
        # Reporte por materia
        res_materia = calcular_ausencias_dinamicas(mes=5, anio=2026, agrupar_por='materia')
        self.assertIn(self.materia.id, res_materia)
        self.assertEqual(res_materia[self.materia.id]['nombre'], 'Matemática I')
        self.assertEqual(res_materia[self.materia.id]['codigo'], 'MAT01')
        self.assertEqual(res_materia[self.materia.id]['esperadas'], 4)

    def test_endpoint_ausencias_requiere_secretario(self):
        # Sin autenticar -> 401
        response = self.client.get('/api/reportes/ausencias?mes=5&anio=2026')
        self.assertEqual(response.status_code, 401)

    def test_endpoint_ausencias_exitoso_secretario(self):
        # Autenticar
        self.client.login(username='secretario', password='password123')
        
        # Con autenticación -> 200 y respuesta válida
        response = self.client.get('/api/reportes/ausencias?mes=5&anio=2026&agrupar_por=docente')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data['mes'], 5)
        self.assertEqual(data['anio'], 2026)
        self.assertEqual(data['agrupar_por'], 'docente')
        self.assertEqual(len(data['resultados']), 1)
        
        # Validar campos de la fila de resultados
        fila = data['resultados'][0]
        self.assertEqual(fila['id'], self.docente.id)
        self.assertEqual(fila['nombre'], 'Juan Perez')
        self.assertEqual(fila['total_clases_esperadas'], 4)
        self.assertEqual(fila['total_asistencias'], 0)
        self.assertEqual(fila['total_ausencias'], 4)
