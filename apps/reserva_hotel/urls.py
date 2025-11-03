from django.urls import path
from .views import (
    #crear_reserva,
    #listar_reservas_hotel,
    #obtener_reserva_hotel,
    #actualizar_reserva_hotel,
    #eliminar_reserva_hotel,
    subir_comprobante
)
from .views import registrar_reserva_hotel, obtener_tarifa_hotel 


urlpatterns = [
    #path('reservaHotel/crear/', crear_reserva, name='crear_reserva'),
    #path('reservaHotel/', lista_reservas, name='lista_reservas'),
    #path('reservaHotel/<int:id_reserva>/', detalle_reserva, name='detalle_reserva'),
    #path('reservaHotel/<int:id_reserva>/update/', actualizar_reserva, name='actualizar_reserva'),
    #path('reservaHotel/<int:id_reserva>/delete/', eliminar_reserva, name='eliminar_reserva'),
    path('reservaHotel/registrar/', registrar_reserva_hotel, name='registrar_reserva_hotel'),
    path('reservaHotel/subir_comprobante/<int:id_reserva_gen>/', subir_comprobante, name='subir_comprobante'),
    path('reservaHotel/tarifa/', obtener_tarifa_hotel, name='obtener_tarifa_hotel'),
]
