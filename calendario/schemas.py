from ninja import ModelSchema
from .models import EventoCalendario

class EventoCalendarioIn(ModelSchema):
    class Meta:
        model = EventoCalendario
        fields = ['fecha', 'descripcion']

class EventoCalendarioOut(ModelSchema):
    class Meta:
        model = EventoCalendario
        fields = ['id', 'fecha', 'descripcion']