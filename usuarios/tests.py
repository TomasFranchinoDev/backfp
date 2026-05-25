from django.test import TestCase, Client
from django.utils import timezone
from usuarios.models import Usuario, Docente, Secretario
from asistencia.models import SolicitudEmergencia, RegistroAsistencia
from academico.models import Carrera, Materia, SlotHorario
from core.constants import EstadoSolicitud, TipoClase

class DashboardStatsTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Crear secretario (admin)
        self.secretario_user = Usuario.objects.create_user(
            username="sec123", email="sec@test.com", password="password", first_name="Juan", last_name="Perez"
        )
        self.secretario = Secretario.objects.create(user=self.secretario_user)
        
        # Crear docente
        self.docente_user = Usuario.objects.create_user(
            username="doc123", email="doc@test.com", password="password", first_name="Ana", last_name="Gomez"
        )
        self.docente = Docente.objects.create(user=self.docente_user, activo=True)

        # Crear materia y slots
        self.carrera = Carrera.objects.create(codigo="ISI", nombre="Ingeniería en Sistemas", duracion_anios=5)
        self.materia = Materia.objects.create(codigo_siu="MAT1", nombre="Matemática I", anio=1)
        
        # Slot para hoy
        self.hoy = timezone.localdate()
        self.slot_hoy = SlotHorario.objects.create(
            materia=self.materia,
            dia_semana=self.hoy.weekday(),
            hora_inicio="08:00:00",
            hora_fin="10:00:00"
        )
        
    def test_dashboard_stats_requires_secretario(self):
        # 1. Sin autenticar
        response = self.client.get("/api/auth/secretario/dashboard-stats")
        self.assertEqual(response.status_code, 401)
        
        # 2. Autenticado como docente
        self.client.login(username="doc123", password="password")
        response = self.client.get("/api/auth/secretario/dashboard-stats")
        self.assertEqual(response.status_code, 401)
        
    def test_dashboard_stats_success(self):
        # Autenticar secretario
        self.client.login(username="sec123", password="password")
        
        # Crear una emergencia pendiente
        SolicitudEmergencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot_hoy,
            fecha=self.hoy,
            nota_docente="Problema técnico con el sistema de fichaje",
            estado=EstadoSolicitud.PENDIENTE
        )
        
        # Crear un docente en aula (registro de asistencia activo sin hora_salida)
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot_hoy,
            fecha=self.hoy,
            anio=2026,
            tipo_clase=TipoClase.PRESENCIAL,
            hora_entrada=timezone.now(),
            ubicacion_validada=True
        )
        
        response = self.client.get("/api/auth/secretario/dashboard-stats")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["docentes_activos"], 1)
        self.assertEqual(data["emergencias_pendientes"], 1)
        self.assertEqual(data["clases_hoy"], 1)
        self.assertEqual(len(data["docentes_en_aula"]), 1)
        self.assertEqual(data["docentes_en_aula"][0]["docente_nombre"], "Ana Gomez")
        self.assertEqual(data["docentes_en_aula"][0]["materia_nombre"], "Matemática I")
        self.assertTrue(data["docentes_en_aula"][0]["ubicacion_validada"])
