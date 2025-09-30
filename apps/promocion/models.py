from django.db import models

class Promocion(models.Model):
    id_promocion = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=30)
    descripcion = models.CharField(max_length=200)
    descuento = models.DecimalField(max_digits=5, decimal_places=2)
    fecha_ini = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=1)


    class Meta:
        db_table = 'promocion'
    def __str__(self):
        return self.nombre
