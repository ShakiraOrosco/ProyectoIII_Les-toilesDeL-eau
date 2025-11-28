from django.urls import path
from .views import (
    # 🔹 FUNCIONES EXISTENTES (NO CAMBIAR)
    subir_comprobante,
    registrar_reserva_hotel, 
    obtener_tarifa_hotel,
    
    # 🔹 NUEVAS FUNCIONES
    lista_reservas_hotel,
    detalle_reserva_hotel,
    actualizar_reserva_hotel,
    eliminar_reserva_hotel,
    reservas_por_estado,
    reservas_por_cliente,
    habitaciones_disponibles
)
from . import views
urlpatterns = [
    # ==============================================
    # 🔹 URLs EXISTENTES (NO CAMBIAR)
    # ==============================================
    path('reservaHotel/registrar/', registrar_reserva_hotel, name='registrar_reserva_hotel'),
    path('reservaHotel/subir_comprobante/<int:id_reserva_gen>/', subir_comprobante, name='subir_comprobante'),
    path('reservaHotel/tarifa/', obtener_tarifa_hotel, name='obtener_tarifa_hotel'),
    
    # ==============================================
    # 🔹 NUEVAS URLs
    # ==============================================
    
    # 🔹 GET endpoints
    path('reservaHotel/reservas/', lista_reservas_hotel, name='lista_reservas_hotel'),
    path('reservaHotel/reservas/<int:id_reserva>/', detalle_reserva_hotel, name='detalle_reserva_hotel'),
    path('reservaHotel/reservas/estado/<str:estado>/', reservas_por_estado, name='reservas_por_estado'),
    path('reservaHotel/reservas/cliente/<int:cliente_id>/', reservas_por_cliente, name='reservas_por_cliente'),
    path('reservaHotel/habitaciones/disponibles/', habitaciones_disponibles, name='habitaciones_disponibles'),
    
    # 🔹 PUT endpoint
    path('reservaHotel/reservas/<int:id_reserva>/actualizar/', actualizar_reserva_hotel, name='actualizar_reserva_hotel'),
    
    # 🔹 DELETE endpoint
    path('reservaHotel/reservas/<int:id_reserva>/eliminar/', eliminar_reserva_hotel, name='eliminar_reserva_hotel'),
    # Check-in / Check-out
    path('reservaHotel/<int:id_reserva>/check-in/', views.realizar_check_in, name='realizar_check_in'),
    path('reservaHotel/<int:id_reserva>/check-out/', views.realizar_check_out, name='realizar_check_out'),
    path('reservaHotel/<int:id_reserva>/check-in/cancelar/', views.cancelar_check_in, name='cancelar_check_in'),
    path('reservaHotel/pendientes-check-in/', views.reservas_pendientes_check_in, name='reservas_pendientes_check_in'),
    path('reservaHotel/pendientes-check-out/', views.reservas_pendientes_check_out, name='reservas_pendientes_check_out'),
    path('reservaHotel/finalizadas/', views.reservas_finalizadas, name='reservas_finalizadas'),

#🔹 Reservas canceladas
    path('reservaHotel/canceladas/', views.reservas_canceladas, name='reservas_canceladas'),

]