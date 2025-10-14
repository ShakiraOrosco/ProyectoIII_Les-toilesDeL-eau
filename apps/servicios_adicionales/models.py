from django.db import models

class ServiciosAdicionales(models.Model):
    id_servicios_adicionales = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=30)
    descripcion = models.CharField(max_length=100, null=True, blank=True)
    precio = models.DecimalField(max_digits=5, decimal_places=2)
    tipo = models.CharField(max_length=1)
    estado = models.CharField(max_length=1)

    class Meta:
        db_table = 'servicios_adicionales'
    def __str__(self):
        return self.nombre
