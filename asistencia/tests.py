from django.test import TestCase
from django.utils import timezone
from datetime import date, time, timedelta
from usuarios.models import Usuario, Docente
from academico.models import Materia, SlotHorario
from asignaciones.models import AsignacionDocente
from calendario.models import EventoCalendario
from asistencia.models import RegistroAsistencia, SolicitudEmergencia
from core.constants import TipoClase, EstadoSolicitud
from unittest.mock import patch

class MisMateriasStatsTests(TestCase):
    def setUp(self):
        # 1. Crear usuario y docente
        self.user = Usuario.objects.create_user(username="profesor1", password="password123")
        self.docente = Docente.objects.create(user=self.user, activo=True)
        
        # 2. Crear materia
        self.materia = Materia.objects.create(codigo_siu="MAT101", nombre="Matematica I", anio=2026)
        
        # 3. Crear slot horario (Lunes de 18:00 a 20:00)
        self.slot = SlotHorario.objects.create(
            materia=self.materia,
            dia_semana=0,
            hora_inicio=time(18, 0),
            hora_fin=time(20, 0)
        )

    def test_stats_excluye_materia_inactiva(self):
        AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.materia,
            rol="titular",
            activa=True,
            fecha_inicio=date(2026, 5, 11)
        )

        self.materia.activa = False
        self.materia.save(update_fields=["activa"])

        self.client.force_login(self.user)

        response = self.client.get('/api/asistencia/mis_materias_stats')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        
    def test_stats_calculo(self):
        # Caso 1: Sin registros de asistencia.
        # La asignación empezó el Lunes 11 de Mayo de 2026.
        # Hoy es Viernes 22 de Mayo de 2026.
        # Lunes en este rango: 11/05 y 18/05. Ambos deben ser faltas (Ausente).
        fecha_inicio = date(2026, 5, 11)
        asig = AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.materia,
            rol="titular",
            activa=True,
            fecha_inicio=fecha_inicio
        )
        
        self.client.force_login(self.user)
        
        with patch('django.utils.timezone.localdate', return_value=date(2026, 5, 22)), \
             patch('django.utils.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 22, 12, 0, 0))
            
            response = self.client.get('/api/asistencia/mis_materias_stats')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]['materia_nombre'], "Matematica I")
            self.assertEqual(data[0]['asistencias'], 0)
            self.assertEqual(data[0]['asincronicas'], 0)
            self.assertEqual(data[0]['faltas'], 2)
            self.assertEqual(len(data[0]['historial']), 2)
            
            # Verificar orden descendente
            self.assertEqual(data[0]['historial'][0]['fecha'], "2026-05-18")
            self.assertEqual(data[0]['historial'][0]['estado'], "Ausente")
            self.assertEqual(data[0]['historial'][1]['fecha'], "2026-05-11")
            self.assertEqual(data[0]['historial'][1]['estado'], "Ausente")
            
        # Caso 2: Con 1 asistencia registrada (11/05) y 1 asincrónica declarada (18/05)
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=date(2026, 5, 11),
            anio=2026,
            tipo_clase=TipoClase.PRESENCIAL,
            hora_entrada=timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 5)),
            hora_salida=timezone.make_aware(timezone.datetime(2026, 5, 11, 20, 0)),
            ubicacion_validada=True
        )
        
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=date(2026, 5, 18),
            anio=2026,
            tipo_clase=TipoClase.ASINCRONICA,
            hora_entrada=None,
            hora_salida=None,
            nota="Clase virtual dada por campus"
        )
        
        with patch('django.utils.timezone.localdate', return_value=date(2026, 5, 22)), \
             patch('django.utils.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 22, 12, 0, 0))
            
            response = self.client.get('/api/asistencia/mis_materias_stats')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertEqual(data[0]['asistencias'], 1)
            self.assertEqual(data[0]['asincronicas'], 1)
            self.assertEqual(data[0]['faltas'], 0)
            
            self.assertEqual(data[0]['historial'][0]['fecha'], "2026-05-18")
            self.assertEqual(data[0]['historial'][0]['estado'], "Presente (Asíncrona)")
            self.assertEqual(data[0]['historial'][1]['fecha'], "2026-05-11")
            self.assertEqual(data[0]['historial'][1]['estado'], "Presente")

        # Caso 3: Verificar que los feriados/días bloqueados se incluyan en faltas como 'Ausente Justificada' si no se fichó
        RegistroAsistencia.objects.all().delete()
        EventoCalendario.objects.create(fecha=date(2026, 5, 18), descripcion="Feriado Nacional")
        
        with patch('django.utils.timezone.localdate', return_value=date(2026, 5, 22)), \
             patch('django.utils.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 22, 12, 0, 0))
            
            response = self.client.get('/api/asistencia/mis_materias_stats')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # 18/05 es feriado (Ausente Justificada, suma a faltas), 11/05 es falta común (Ausente).
            self.assertEqual(data[0]['asistencias'], 0)
            self.assertEqual(data[0]['faltas'], 2)
            self.assertEqual(len(data[0]['historial']), 2)
            self.assertEqual(data[0]['historial'][0]['fecha'], "2026-05-18")
            self.assertEqual(data[0]['historial'][0]['estado'], "Ausente Justificada")
            self.assertEqual(data[0]['historial'][1]['fecha'], "2026-05-11")
            self.assertEqual(data[0]['historial'][1]['estado'], "Ausente")


class DeclararClaseAsincronicaTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="profesor1", password="password123")
        self.docente = Docente.objects.create(user=self.user, activo=True)
        self.materia = Materia.objects.create(codigo_siu="MAT101", nombre="Matematica I", anio=2026)
        
        # Slot: Lunes = 0
        self.slot = SlotHorario.objects.create(
            materia=self.materia,
            dia_semana=0,
            hora_inicio=time(18, 0),
            hora_fin=time(20, 0)
        )
        
        # Asignación activa
        self.asig = AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.materia,
            rol="titular",
            activa=True,
            fecha_inicio=date(2026, 4, 1)
        )

    def test_declarar_clase_asincronica_rangos(self):
        from asistencia.services import declarar_clase_asincronica

        # Mock hoy como lunes 11 de Mayo de 2026
        with patch('django.utils.timezone.localdate', return_value=date(2026, 5, 11)):
            # 1. Exactamente hoy (Lunes 11 de Mayo)
            success, msg = declarar_clase_asincronica(
                docente_id=self.docente.id,
                slot_id=self.slot.id,
                fecha_dictado=date(2026, 5, 11),
                nota="Dictado hoy"
            )
            self.assertTrue(success)
            self.assertEqual(RegistroAsistencia.objects.count(), 1)
            RegistroAsistencia.objects.all().delete()

            # 2. Exactamente 7 días antes (Lunes 4 de Mayo)
            success, msg = declarar_clase_asincronica(
                docente_id=self.docente.id,
                slot_id=self.slot.id,
                fecha_dictado=date(2026, 5, 4),
                nota="Dictado hace una semana"
            )
            self.assertTrue(success)
            self.assertEqual(RegistroAsistencia.objects.count(), 1)
            RegistroAsistencia.objects.all().delete()

            # 3. Exactamente 7 días después (Lunes 18 de Mayo)
            success, msg = declarar_clase_asincronica(
                docente_id=self.docente.id,
                slot_id=self.slot.id,
                fecha_dictado=date(2026, 5, 18),
                nota="Planificado para próxima semana"
            )
            self.assertTrue(success)
            self.assertEqual(RegistroAsistencia.objects.count(), 1)
            RegistroAsistencia.objects.all().delete()

            # 4. Fuera de rango: 14 días antes (Lunes 27 de Abril)
            success, msg = declarar_clase_asincronica(
                docente_id=self.docente.id,
                slot_id=self.slot.id,
                fecha_dictado=date(2026, 4, 27),
                nota="Demasiado antiguo"
            )
            self.assertFalse(success)
            self.assertIn("antigüedad", msg)
            self.assertEqual(RegistroAsistencia.objects.count(), 0)

            # 5. Fuera de rango: 14 días después (Lunes 25 de Mayo)
            success, msg = declarar_clase_asincronica(
                docente_id=self.docente.id,
                slot_id=self.slot.id,
                fecha_dictado=date(2026, 5, 25),
                nota="Demasiada anticipación"
            )
            self.assertFalse(success)
            self.assertIn("anticipación", msg)
            self.assertEqual(RegistroAsistencia.objects.count(), 0)


class FichajeRichResponseTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="profesor1", password="password123", first_name="Tomas", last_name="Franchino")
        self.docente = Docente.objects.create(user=self.user, activo=True)
        self.materia = Materia.objects.create(codigo_siu="MAT101", nombre="Matematica I", anio=2026)
        self.slot = SlotHorario.objects.create(
            materia=self.materia,
            dia_semana=0,
            hora_inicio=time(18, 0),
            hora_fin=time(20, 0)
        )
        self.asig = AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.materia,
            rol="titular",
            activa=True,
            fecha_inicio=date(2026, 4, 1)
        )
        from configuracion.models import Configuracion
        from core.constants import MetodoValidacion
        self.config = Configuracion.objects.create(
            id=1,
            latitud_campus=-30.944598,
            longitud_campus=-61.558501,
            radio_gps_metros=150,
            red_wifi_campus="200.100.50.25",
            metodo_validacion_ubicacion=MetodoValidacion.GPS_O_WIFI
        )
        self.client.force_login(self.user)

    @patch('django.utils.timezone.localtime')
    def test_entrada_exitosa_devuelve_campos_ricos(self, mock_localtime):
        # Configurar hora: Lunes 11 de Mayo de 2026 a las 18:30 (dentro del slot de Lunes 18:00-20:00)
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        # Coordenadas válidas (cerca del campus)
        payload = {
            "latitud": -30.944500,
            "longitud": -61.558500,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json",
            REMOTE_ADDR="200.100.50.25"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["estado_flujo"], "exito")
        self.assertTrue(data["gps_ok"])
        self.assertTrue(data["wifi_ok"])
        self.assertEqual(data["materia"], "Matematica I")
        self.assertEqual(data["hora_fichada"], "18:30")
        self.assertEqual(data["tipo_clase"], "presencial")
        self.assertEqual(data["docente_nombre"], self.user.get_full_name())

    @patch('django.utils.timezone.localtime')
    def test_entrada_fallo_gps_pasa_por_wifi(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        # GPS fuera de rango pero IP correcta (metodo GPS_O_WIFI debe pasar)
        payload = {
            "latitud": -31.944500,
            "longitud": -61.558500,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json",
            REMOTE_ADDR="200.100.50.25"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["gps_ok"])
        self.assertTrue(data["wifi_ok"])

    @patch('django.utils.timezone.localtime')
    def test_entrada_fallo_gps_y_wifi_devuelve_error_ubicacion(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        # Ambos fallan
        payload = {
            "latitud": -31.944500,
            "longitud": -61.558500,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json",
            REMOTE_ADDR="8.8.8.8"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["estado_flujo"], "error_ubicacion")
        self.assertFalse(data["gps_ok"])
        self.assertFalse(data["wifi_ok"])

    @patch('django.utils.timezone.localtime')
    def test_entrada_fallo_gps_con_solo_gps(self, mock_localtime):
        from core.constants import MetodoValidacion
        self.config.metodo_validacion_ubicacion = MetodoValidacion.SOLO_GPS
        self.config.save()
        
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        payload = {
            "latitud": -31.944500,
            "longitud": -61.558500,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json",
            REMOTE_ADDR="200.100.50.25"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["estado_flujo"], "error_gps")
        self.assertFalse(data["gps_ok"])
        self.assertTrue(data["wifi_ok"])

    @patch('django.utils.timezone.localtime')
    def test_entrada_fallo_wifi_con_solo_wifi(self, mock_localtime):
        from core.constants import MetodoValidacion
        self.config.metodo_validacion_ubicacion = MetodoValidacion.SOLO_WIFI
        self.config.save()
        
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        payload = {
            "latitud": -30.944598,
            "longitud": -61.558501,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json",
            REMOTE_ADDR="8.8.8.8"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["estado_flujo"], "error_wifi")
        self.assertTrue(data["gps_ok"])
        self.assertFalse(data["wifi_ok"])

    @patch('django.utils.timezone.localtime')
    def test_entrada_fallo_horario_sin_clases(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 12, 0, 0))
        
        payload = {
            "latitud": -30.944598,
            "longitud": -61.558501,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["estado_flujo"], "sin_clases")

    @patch('django.utils.timezone.localtime')
    def test_entrada_duplicada(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=date(2026, 5, 11),
            anio=2026,
            tipo_clase="presencial",
            hora_entrada=timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 5)),
            ubicacion_validada=True
        )
        
        payload = {
            "latitud": -30.944598,
            "longitud": -61.558501,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["estado_flujo"], "duplicado")

    @patch('django.utils.timezone.localtime')
    def test_salida_exitosa_con_validacion(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=date(2026, 5, 11),
            anio=2026,
            tipo_clase="presencial",
            hora_entrada=timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 5)),
            ubicacion_validada=True
        )
        
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 19, 45, 0))
        
        payload = {
            "latitud": -30.944598,
            "longitud": -61.558501,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/salida',
            payload,
            content_type="application/json",
            REMOTE_ADDR="200.100.50.25"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["estado_flujo"], "exito")
        self.assertTrue(data["gps_ok"])
        self.assertTrue(data["wifi_ok"])

    @patch('django.utils.timezone.localtime')
    def test_salida_fallo_ubicacion(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=date(2026, 5, 11),
            anio=2026,
            tipo_clase="presencial",
            hora_entrada=timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 5)),
            ubicacion_validada=True
        )
        
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 19, 45, 0))
        
        payload = {
            "latitud": -31.944500,
            "longitud": -61.558500,
            "tipo_clase": "presencial"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/salida',
            payload,
            content_type="application/json",
            REMOTE_ADDR="8.8.8.8"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["estado_flujo"], "error_ubicacion")

    @patch('django.utils.timezone.localtime')
    def test_estado_hoy_sin_clases_con_proxima(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 12, 0, 0))
        
        response = self.client.get('/api/asistencia/estado_hoy')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertFalse(data["tiene_entrada_activa"])
        self.assertIsNone(data["clase_vigente"])
        self.assertIsNotNone(data["proxima_clase"])
        self.assertEqual(data["proxima_clase"]["materia_nombre"], "Matematica I")
        self.assertEqual(data["proxima_clase"]["hora_inicio"], "18:00")
        self.assertEqual(data["proxima_clase"]["fichable_desde"], "17:00")

    @patch('django.utils.timezone.localtime')
    def test_estado_hoy_clase_vigente(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        response = self.client.get('/api/asistencia/estado_hoy')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertFalse(data["tiene_entrada_activa"])
        self.assertEqual(data["clase_vigente"], "Matematica I")
        self.assertIsNone(data["proxima_clase"])

    @patch('django.utils.timezone.localtime')
    def test_entrada_virtual_sincronica_sin_ubicacion(self, mock_localtime):
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 18, 30, 0))
        
        payload = {
            "latitud": None,
            "longitud": None,
            "tipo_clase": "virtual_sincronica"
        }
        
        response = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json",
            REMOTE_ADDR="8.8.8.8"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["estado_flujo"], "exito")
        self.assertIsNone(data["gps_ok"])
        self.assertIsNone(data["wifi_ok"])
        self.assertEqual(data["tipo_clase"], "virtual_sincronica")



class ConsecutiveClassesOverlapTests(TestCase):
    def setUp(self):
        # Create user and docente
        self.user = Usuario.objects.create_user(username="alejandro", password="password123", first_name="Alejandro", last_name="Aguirre")
        self.docente = Docente.objects.create(user=self.user, activo=True)
        
        # Create materias
        self.db2 = Materia.objects.create(codigo_siu="DB2", nombre="Bases de Datos II", anio=2026)
        self.calc1 = Materia.objects.create(codigo_siu="CALC1", nombre="Calculo I", anio=2026)
        
        # Slots: Lunes = 0
        # Class 1: 08:00 to 14:00
        self.slot1 = SlotHorario.objects.create(
            materia=self.db2,
            dia_semana=0,
            hora_inicio=time(8, 0),
            hora_fin=time(14, 0)
        )
        # Class 2: 14:15 to 16:00
        self.slot2 = SlotHorario.objects.create(
            materia=self.calc1,
            dia_semana=0,
            hora_inicio=time(14, 15),
            hora_fin=time(16, 0)
        )
        
        # Assign both to docente
        AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.db2,
            rol="titular",
            activa=True,
            fecha_inicio=date(2026, 4, 1)
        )
        AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.calc1,
            rol="titular",
            activa=True,
            fecha_inicio=date(2026, 4, 1)
        )
        
        # Setup campus validation settings
        from configuracion.models import Configuracion
        from core.constants import MetodoValidacion
        self.config = Configuracion.objects.create(
            id=1,
            latitud_campus=-30.944598,
            longitud_campus=-61.558501,
            radio_gps_metros=150,
            red_wifi_campus="200.100.50.25",
            metodo_validacion_ubicacion=MetodoValidacion.GPS_O_WIFI
        )
        self.client.force_login(self.user)

    @patch('django.utils.timezone.localtime')
    def test_overlap_matches_second_class_after_first_completed(self, mock_localtime):
        # 1. Mock time: Monday 11th May 2026, 14:15
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 14, 15, 0))
        
        # 2. Registramos asistencia completa para Clase 1 (Bases de Datos II) hoy
        RegistroAsistencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot1,
            fecha=date(2026, 5, 11),
            anio=2026,
            tipo_clase="presencial",
            hora_entrada=timezone.make_aware(timezone.datetime(2026, 5, 11, 8, 5, 0)),
            hora_salida=timezone.make_aware(timezone.datetime(2026, 5, 11, 13, 55, 0)),
            ubicacion_validada=True
        )
        
        # 3. Llamar a estado_hoy
        response = self.client.get('/api/asistencia/estado_hoy')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Debe sugerir Cálculo I como la clase vigente, no Bases de Datos II
        self.assertFalse(data["tiene_entrada_activa"])
        self.assertEqual(data["clase_vigente"], "Calculo I")
        self.assertIsNone(data["proxima_clase"])
        
        # 4. Fichar entrada para Cálculo I (debe tener éxito)
        payload = {
            "latitud": -30.944598,
            "longitud": -61.558501,
            "tipo_clase": "presencial"
        }
        
        response_entrada = self.client.post(
            '/api/asistencia/chequeoprofesor/entrada',
            payload,
            content_type="application/json",
            REMOTE_ADDR="200.100.50.25"
        )
        self.assertEqual(response_entrada.status_code, 200)
        data_entrada = response_entrada.json()
        self.assertTrue(data_entrada["success"])
        self.assertEqual(data_entrada["materia"], "Calculo I")


class ConsecutiveShortClassesOrderTests(TestCase):
    def setUp(self):
        # Create user and docente
        self.user = Usuario.objects.create_user(username="tomas", password="password123", first_name="Tomas", last_name="Franchino")
        self.docente = Docente.objects.create(user=self.user, activo=True)
        
        # Create 3 materias
        self.m1 = Materia.objects.create(codigo_siu="M1", nombre="Clase Uno", anio=2026)
        self.m2 = Materia.objects.create(codigo_siu="M2", nombre="Clase Dos", anio=2026)
        self.m3 = Materia.objects.create(codigo_siu="M3", nombre="Clase Tres", anio=2026)
        
        # Slots: Lunes = 0
        # Class 1: 16:00 to 16:05
        self.slot1 = SlotHorario.objects.create(
            materia=self.m1,
            dia_semana=0,
            hora_inicio=time(16, 0),
            hora_fin=time(16, 5)
        )
        # Class 2: 16:05 to 16:10
        self.slot2 = SlotHorario.objects.create(
            materia=self.m2,
            dia_semana=0,
            hora_inicio=time(16, 5),
            hora_fin=time(16, 10)
        )
        # Class 3: 16:10 to 16:15
        self.slot3 = SlotHorario.objects.create(
            materia=self.m3,
            dia_semana=0,
            hora_inicio=time(16, 10),
            hora_fin=time(16, 15)
        )
        
        # Assign all to docente
        for m in [self.m1, self.m2, self.m3]:
            AsignacionDocente.objects.create(
                docente=self.docente,
                materia=m,
                rol="titular",
                activa=True,
                fecha_inicio=date(2026, 4, 1)
            )
            
        # Setup campus validation settings
        from configuracion.models import Configuracion
        from core.constants import MetodoValidacion
        self.config = Configuracion.objects.create(
            id=1,
            latitud_campus=-30.944598,
            longitud_campus=-61.558501,
            radio_gps_metros=150,
            red_wifi_campus="200.100.50.25",
            metodo_validacion_ubicacion=MetodoValidacion.GPS_O_WIFI
        )
        self.client.force_login(self.user)

    @patch('django.utils.timezone.localtime')
    def test_chronological_order_consecutive_short_classes(self, mock_localtime):
        # 1. At 16:00, all 3 are within the 60-min tolerance window.
        # But Clase Uno starts first, so it must be selected.
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 16, 0, 0))
        
        response = self.client.get('/api/asistencia/estado_hoy')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["clase_vigente"], "Clase Uno")
        
        # Fichar entrada Clase Uno
        payload = {
            "latitud": -30.944598,
            "longitud": -61.558501,
            "tipo_clase": "presencial"
        }
        res = self.client.post('/api/asistencia/chequeoprofesor/entrada', payload, content_type="application/json", REMOTE_ADDR="200.100.50.25")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["materia"], "Clase Uno")
        
        # 2. At 16:02, we sign out of Clase Uno
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 16, 2, 0))
        res = self.client.post('/api/asistencia/chequeoprofesor/salida', payload, content_type="application/json", REMOTE_ADDR="200.100.50.25")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["materia"], "Clase Uno")
        
        # 3. At 16:03, Clase Uno is finished. Clase Dos and Clase Tres windows match.
        # It must select Clase Dos.
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 16, 3, 0))
        response = self.client.get('/api/asistencia/estado_hoy')
        self.assertEqual(response.json()["clase_vigente"], "Clase Dos")
        
        # Fichar entrada Clase Dos
        res = self.client.post('/api/asistencia/chequeoprofesor/entrada', payload, content_type="application/json", REMOTE_ADDR="200.100.50.25")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["materia"], "Clase Dos")
        
        # 4. At 16:04, we sign out of Clase Dos
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 16, 4, 0))
        res = self.client.post('/api/asistencia/chequeoprofesor/salida', payload, content_type="application/json", REMOTE_ADDR="200.100.50.25")
        self.assertEqual(res.status_code, 200)
        
        # 5. At 16:06, Clase Dos is finished. Only Clase Tres matches.
        mock_localtime.return_value = timezone.make_aware(timezone.datetime(2026, 5, 11, 16, 6, 0))
        response = self.client.get('/api/asistencia/estado_hoy')
        self.assertEqual(response.json()["clase_vigente"], "Clase Tres")
        
        # Fichar entrada Clase Tres
        res = self.client.post('/api/asistencia/chequeoprofesor/entrada', payload, content_type="application/json", REMOTE_ADDR="200.100.50.25")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["materia"], "Clase Tres")


class EmergenciasHistorialTests(TestCase):
    def setUp(self):
        from usuarios.models import Usuario, Docente, Secretario
        
        # Crear secretario (admin)
        self.secretario_user = Usuario.objects.create_user(
            username="sec_admin", email="sec@test.com", password="password", first_name="Juan", last_name="Perez"
        )
        self.secretario = Secretario.objects.create(user=self.secretario_user)
        
        # Crear docente
        self.docente_user = Usuario.objects.create_user(
            username="doc_prof", email="doc@test.com", password="password", first_name="Ana", last_name="Gomez"
        )
        self.docente = Docente.objects.create(user=self.docente_user, activo=True)

        # Crear materia y slot
        self.materia = Materia.objects.create(codigo_siu="MAT1", nombre="Matemática I", anio=1)
        self.slot = SlotHorario.objects.create(
            materia=self.materia,
            dia_semana=0,
            hora_inicio="08:00:00",
            hora_fin="10:00:00"
        )
        self.hoy = date(2026, 5, 11)

    def test_historial_requires_secretario(self):
        # 1. Sin autenticar
        response = self.client.get("/api/asistencia/admin/emergencias/historial")
        self.assertEqual(response.status_code, 401)
        
        # 2. Autenticado como docente
        self.client.force_login(self.docente_user)
        response = self.client.get("/api/asistencia/admin/emergencias/historial")
        self.assertEqual(response.status_code, 401)

    def test_historial_retorna_solo_resueltas(self):
        # Autenticar secretario
        self.client.force_login(self.secretario_user)
        
        # 1. Emergencia pendiente (no debe salir en el historial)
        SolicitudEmergencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=self.hoy,
            nota_docente="Pendiente de revisar",
            estado=EstadoSolicitud.PENDIENTE
        )
        
        # 2. Emergencia aprobada
        e_aprobada = SolicitudEmergencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=self.hoy,
            nota_docente="Problema con el proyector",
            estado=EstadoSolicitud.APROBADA,
            nota_secretaria="Se justifica la falta",
            revisado_por=self.secretario,
            revisado_en=timezone.now()
        )
        
        # 3. Emergencia rechazada
        e_rechazada = SolicitudEmergencia.objects.create(
            docente=self.docente,
            slot_horario=self.slot,
            fecha=self.hoy,
            nota_docente="Teclado roto",
            estado=EstadoSolicitud.RECHAZADA,
            nota_secretaria="No corresponde justificar",
            revisado_por=self.secretario,
            revisado_en=timezone.now()
        )
        
        response = self.client.get("/api/asistencia/admin/emergencias/historial")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 2)
        
        # Deben venir en orden descendente de fecha/revisado_en
        self.assertEqual(data[0]["id"], e_rechazada.id)
        self.assertEqual(data[1]["id"], e_aprobada.id)
        
        # Verificar campos devueltos
        self.assertEqual(data[0]["docente_nombre"], "Ana Gomez")
        self.assertEqual(data[0]["materia_nombre"], "Matemática I")
        self.assertEqual(data[0]["estado"], "rechazada")
        self.assertEqual(data[0]["nota_docente"], "Teclado roto")
        self.assertEqual(data[0]["nota_secretaria"], "No corresponde justificar")
        self.assertEqual(data[0]["revisado_por_nombre"], "Juan Perez")
        self.assertIsNotNone(data[0]["revisado_en"])
