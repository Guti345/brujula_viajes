import streamlit as st
import api_client  # Importamos nuestro puente

import sys
import os
from datetime import date
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from back.app import schemas # Reusamos DTOs
from pydantic import ValidationError

st.header("📋 Gestión de Pacientes")

tab1, tab2 = st.tabs(["Listar", "Registrar"])

with tab1:
    if st.button("Actualizar Lista"):
        datos = api_client.get_all_pacientes()
        st.table(datos)

with tab2:
    with st.form("crear_paciente"):
        nombre = st.text_input("Nombre")
        # st.date_input devuelve un datetime.date (fecha sin hora)
        fecha_nacimiento = st.date_input(
            "Fecha de nacimiento",
            value=date(2000, 1, 1),
            min_value=date(1920, 1, 1),
            max_value=date.today(),
        )
        contacto = st.text_input("Teléfono / correo de contacto")
        referido_id = st.number_input("ID del paciente que refiere (0 = ninguno)", min_value=0, step=1)

        if st.form_submit_button("Guardar"):
            try:
                # Validación con el mismo DTO del backend antes de tocar la red
                paciente = schemas.PacienteCreate(
                    nombre=nombre,
                    fecha_nacimiento=fecha_nacimiento,
                    contacto=contacto,
                    referido_por_id=referido_id if referido_id > 0 else None,
                )
            except ValidationError as e:
                st.warning(f"⚠️ Datos inválidos: {e.errors()[0]['msg']}")
            else:
                # mode="json" convierte el date en el texto "AAAA-MM-DD", porque JSON no tiene
                # tipo fecha. FastAPI lo vuelve a convertir en date, y a_documento() en el
                # backend lo transforma en datetime para poder guardarlo en MongoDB.
                respuesta = api_client.create_paciente(paciente.model_dump(mode="json"))
                if respuesta.status_code == 201:
                    creado = respuesta.json()
                    st.success(f"✅ Paciente '{creado['nombre']}' creado con ID {creado['id']} "
                               f"(nacido el {creado['fecha_nacimiento']})")
                else:
                    st.error(f"❌ Error del servidor: {respuesta.json().get('detail')}")