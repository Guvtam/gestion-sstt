from django.urls import path
from . import views
app_name = "contratistas"
urlpatterns = [path("", views.listado, name="listado"), path("nuevo/", views.editar, name="nuevo"), path("<int:pk>/editar/", views.editar, name="editar"), path("<int:pk>/equivalencias/", views.equivalencias, name="equivalencias"), path("<int:pk>/equivalencias/<int:equivalencia_id>/eliminar/", views.eliminar_equivalencia, name="eliminar_equivalencia")]
