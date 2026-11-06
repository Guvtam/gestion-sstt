"""Errores de aplicación sin códigos HTTP ni dependencias de presentación."""


class ErrorOperacionODT(Exception):
    pass


class DatosODTInvalidos(ErrorOperacionODT):
    pass


class ODTNoEncontrada(ErrorOperacionODT):
    pass


class ODTBloqueada(ErrorOperacionODT):
    pass


class VerificacionCoordinadorFallida(ErrorOperacionODT):
    pass
