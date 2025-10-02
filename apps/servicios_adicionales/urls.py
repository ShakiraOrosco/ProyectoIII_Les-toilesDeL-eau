from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import lista_servicios,crear_servicio,actualizar_servicio,eliminar_servicio,detalle_servicio, mi_perfil_servicios


urlpatterns = [
    
    # Autenticación
    path('login/', TokenObtainPairView.as_view(), name='api-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Endpoints personalizados
    path('servicios/crear/', crear_servicio, name='crear_servicio'),
    path('servicios/', lista_servicios, name='lista-servicios'),
    path('mi-perfil/', mi_perfil_servicios, name='mi-perfil-servicios'),

    path('servicios/<int:id_servicio>/', detalle_servicio, name='detalle-servicio'),
    path('servicios/<int:id_servicio>/update/', actualizar_servicio, name='actualizar-servicio'),
    path('servicios/<int:id_servicio>/delete/', eliminar_servicio, name='eliminar-servicio'),
 
]
