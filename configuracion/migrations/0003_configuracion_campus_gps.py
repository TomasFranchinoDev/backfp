from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracion',
            name='latitud_campus',
            field=models.DecimalField(decimal_places=6, default=-30.944598, max_digits=9),
        ),
        migrations.AddField(
            model_name='configuracion',
            name='longitud_campus',
            field=models.DecimalField(decimal_places=6, default=-61.558501, max_digits=9),
        ),
        migrations.AddField(
            model_name='configuracion',
            name='radio_gps_metros',
            field=models.PositiveSmallIntegerField(default=150),
        ),
    ]
