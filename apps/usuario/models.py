from django.db import models
from django.contrib.auth.models import User

class Usuario(models.Model):
    user= models.OneToOneField(User, on_delete=models.CASCADE, related_name='usuario')
    id_usuario = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=15)
    app_paterno = models.CharField(max_length=15, null=True, blank=True)
    app_materno = models.CharField(max_length=15, null=True, blank=True)
    ci = models.BigIntegerField(unique=True)
    telefono = models.IntegerField()
    email = models.EmailField(max_length=50)
    password = models.CharField(max_length=20)
    estado = models.CharField(max_length=1)
    rol = models.CharField(max_length=30)   # reemplazo de FK rol

    class Meta:
        db_table = 'usuario'

    def __str__(self):
        return f"{self.nombre} {self.app_paterno or ''}"
