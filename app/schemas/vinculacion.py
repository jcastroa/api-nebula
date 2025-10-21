# Modelos Pydantic
from pydantic import BaseModel, Field
from typing import Optional





class CompletarVinculacionRequest(BaseModel):
    session_id: str
    code: str


class SeleccionarNumeroRequest(BaseModel):
    session_id: str
    phone_number_id: str = Field(..., description="ID del número seleccionado por el usuario")