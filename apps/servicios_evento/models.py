from django.db import models
from apps.reservas_evento.models import ReservasEvento
from apps.servicios_adicionales.models import ServiciosAdicionales

class ServiciosEvento(models.Model):
    id_servicios_evento = models.AutoField(primary_key=True)
    reservas_evento = models.ForeignKey(ReservasEvento, on_delete=models.CASCADE)
    servicios_adicionales = models.ForeignKey(ServiciosAdicionales, on_delete=models.CASCADE)

    class Meta:
        db_table = 'servicios_evento'