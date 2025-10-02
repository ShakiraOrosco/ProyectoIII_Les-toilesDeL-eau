from django.db import models
from apps.reservas_gen.models import ReservasGen
from apps.promocion.models import Promocion

class PromocionReserva(models.Model):
    id_promo_reserva = models.AutoField(primary_key=True)
    reservas_gen = models.ForeignKey(ReservasGen, on_delete=models.CASCADE)
    promocion = models.ForeignKey(Promocion, on_delete=models.CASCADE)


    class Meta:
        db_table = 'promocionreserva'