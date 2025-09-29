from django.db import models

class Rol(models.Model):
    nombre = models.CharField(max_length=15)
    descripcion = models.CharField(max_length=200, null=True, blank=True)

class Usuario(models.Model):
    nombre = models.CharField(max_length=15)
    app_paterno = models.CharField(max_length=15)
    app_materno = models.CharField(max_length=15, null=True, blank=True)
    ci = models.BigIntegerField(unique=True)
    telefono = models.IntegerField()
    email = models.CharField(max_length=50)
    password = models.CharField(max_length=20)
    estado = models.CharField(max_length=1)
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE)
