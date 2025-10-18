from django.urls import path
from . import views

urlpatterns = [
    path('reservaEvento/registrar/', views.registrar_reserva_evento, name='registrar_reserva_evento'),
    #/path('reservaEvento/servicios/', views.listar_servicios_adicionales_evento, name='listar_servicios_adicionales_evento'),
]
