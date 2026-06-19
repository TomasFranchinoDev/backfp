from .models import Carrera, Materia, MateriaCarrera, SlotHorario
from django.db.models import Max


def materia_to_out(materia: Materia) -> dict:
    carreras = [
        {
            'id': vinculo.carrera.id,
            'codigo': vinculo.carrera.codigo,
            'nombre': vinculo.carrera.nombre,
        }
        for vinculo in materia.carreras_asociadas.all()
    ]

    # Fecha de desactivación: max valido_hasta de los slots cerrados
    desactivada_en = None
    if not materia.activa:
        desactivada_en = SlotHorario.objects.filter(
            materia=materia, valido_hasta__isnull=False
        ).aggregate(max_fecha=Max('valido_hasta'))['max_fecha']

    return {
        'id': materia.id,
        'codigo_siu': materia.codigo_siu,
        'nombre': materia.nombre,
        'anio': materia.anio,
        'activa': materia.activa,
        'carreras': carreras,
        'desactivada_en': desactivada_en,
    }



def sincronizar_carreras_materia(materia: Materia, carreras_ids: list[int], usuario) -> None:
    ids_unicos = list(dict.fromkeys(carreras_ids))
    carreras_validas = set(Carrera.objects.filter(id__in=ids_unicos).values_list('id', flat=True))

    if len(carreras_validas) != len(ids_unicos):
        raise ValueError('Una o más carreras seleccionadas no existen.')

    actuales = set(
        MateriaCarrera.objects.filter(materia=materia).values_list('carrera_id', flat=True)
    )
    nuevos = carreras_validas - actuales
    eliminar = actuales - carreras_validas

    if eliminar:
        MateriaCarrera.objects.filter(materia=materia, carrera_id__in=eliminar).delete()

    for carrera_id in nuevos:
        MateriaCarrera.objects.create(
            materia=materia,
            carrera_id=carrera_id,
            anio_plan=materia.anio,
            creado_por=usuario,
        )

    MateriaCarrera.objects.filter(materia=materia).update(
        anio_plan=materia.anio,
        modificado_por=usuario,
    )


def obtener_materia_con_carreras(materia_id: int) -> Materia:
    return (
        Materia.objects.prefetch_related('carreras_asociadas__carrera')
        .filter(id=materia_id)
        .first()
    )
