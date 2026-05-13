import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
import geopandas as gpd
from streamlit_folium import st_folium

# =========================
# CONFIG STREAMLIT
# =========================
st.set_page_config(page_title="Cobertura vs Ventas", layout="wide")
st.title("📡 Análisis de Cobertura vs Ventas")

# =========================
# CACHE LECTURA ARCHIVOS
# =========================
@st.cache_data
def cargar_datos():
    ventas = pd.read_excel("data/ventas.xlsx")
    antenas = pd.read_excel("data/antenas.xlsx")
    return ventas, antenas

ventas, antenas = cargar_datos()

# =========================
# LIMPIEZA INICIAL
# =========================
ventas["LOGIN"] = ventas["LOGIN"].astype(str).str.strip()

ventas["REQUESTDATE"] = pd.to_datetime(
    ventas["REQUESTDATE"],
    dayfirst=True,
    errors="coerce"
)

antenas["Fecha de Activación"] = pd.to_datetime(
    antenas["Fecha de Activación"],
    errors="coerce"
)

# =========================
# LIMPIEZA COORDENADAS
# =========================
def limpiar_coordenadas(df, lat="LATITUDE", lon="LONGITUDE"):

    for c in [lat, lon]:

        df[c] = (
            df[c]
            .astype(str)
            .str.replace("'", "", regex=False)
            .str.strip()
            .replace("", pd.NA)
        )

        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=[lat, lon])

    return df

ventas = limpiar_coordenadas(ventas)
antenas = limpiar_coordenadas(antenas)

# =========================
# CACHE GEOPROCESAMIENTO
# =========================
@st.cache_data
def procesar_geodatos(ventas, antenas):

    ventas_gdf = gpd.GeoDataFrame(
        ventas,
        geometry=gpd.points_from_xy(
            ventas["LONGITUDE"],
            ventas["LATITUDE"]
        ),
        crs="EPSG:4326"
    ).to_crs(epsg=32718)

    antenas_gdf = gpd.GeoDataFrame(
        antenas,
        geometry=gpd.points_from_xy(
            antenas["LONGITUDE"],
            antenas["LATITUDE"]
        ),
        crs="EPSG:4326"
    ).to_crs(epsg=32718)

    ventas_ant = gpd.sjoin_nearest(
        ventas_gdf,
        antenas_gdf[["ID_ANTENA", "geometry"]],
        how="left",
        distance_col="distancia_m"
    )

    ventas_ant = ventas_ant[
        ventas_ant["distancia_m"] <= 2000
    ]

    return ventas_gdf, antenas_gdf, ventas_ant

ventas_gdf, antenas_gdf, ventas_ant = procesar_geodatos(
    ventas,
    antenas
)

# =========================
# RESUMEN ANTENAS
# =========================
ventas_resumen = (
    ventas_ant.groupby("ID_ANTENA")
    .size()
    .reset_index(name="ventas_2km")
)

resumen_antenas = antenas.merge(
    ventas_resumen,
    on="ID_ANTENA",
    how="left"
)

resumen_antenas["ventas_2km"] = (
    resumen_antenas["ventas_2km"]
    .fillna(0)
    .astype(int)
)

# =========================
# ESTADO ANTENA
# =========================
def estado_antena(ventas):

    if ventas < 10:
        return "🔴"

    elif ventas < 50:
        return "🟡"

    else:
        return "🟢"

resumen_antenas["Estado"] = (
    resumen_antenas["ventas_2km"]
    .apply(estado_antena)
)

# =========================
# FILTRO DEPARTAMENTO
# =========================
departamentos = sorted(
    antenas["Departamento"]
    .dropna()
    .unique()
)

depto_seleccionado = st.selectbox(
    "Departamento",
    departamentos
)

antenas_filtradas = antenas[
    antenas["Departamento"] == depto_seleccionado
]

# =========================
# SELECTOR ANTENA
# =========================
antena_seleccionada = st.selectbox(
    "Seleccionar antena",
    antenas_filtradas["ID_ANTENA"].sort_values()
)

fila_antena = antenas.loc[
    antenas["ID_ANTENA"] == antena_seleccionada
].iloc[0]

lat_antena = fila_antena["LATITUDE"]
lon_antena = fila_antena["LONGITUDE"]

# =========================
# MAPA
# =========================
m = folium.Map(
    location=[lat_antena, lon_antena],
    zoom_start=14,
    tiles="OpenStreetMap"
)

# =========================
# HEATMAP VENTAS
# =========================
ventas_heat = ventas.dropna(
    subset=["LATITUDE", "LONGITUDE"]
)

HeatMap(
    ventas_heat[
        ["LATITUDE", "LONGITUDE"]
    ].values.tolist(),
    radius=15,
    blur=20
).add_to(m)

# =========================
# CAPA ANTENAS
# =========================
antenas_map = antenas_gdf.to_crs(epsg=4326)

for _, row in antenas_map.iterrows():

    total = int(
        resumen_antenas.loc[
            resumen_antenas["ID_ANTENA"] == row["ID_ANTENA"],
            "ventas_2km"
        ].values[0]
    )

    if total < 10:
        aro_color = "red"

    elif total < 50:
        aro_color = "orange"

    else:
        aro_color = "green"

    popup = f"""
    <b>ID Antena:</b> {row['ID_ANTENA']}<br>
    <b>Departamento:</b> {row['Departamento']}<br>
    <b>Provincia:</b> {row['Provincia']}<br>
    <b>Distrito:</b> {row['Distrito']}<br>
    <b>Cluster:</b> {row['Cluster']}<br>
    <b>Tipo de Venta:</b> {row['Tipo_Venta']}<br>
    <b>Acción:</b> {row['Acción']}<br>
    <b>Fecha Activación:</b> {
        row['Fecha de Activación'].date()
        if pd.notna(row['Fecha de Activación'])
        else '-'
    }<br>
    <b>Ventas 2 km:</b> {total}
    """

    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x],
        radius=6,
        color="blue",
        fill=True,
        fill_opacity=0.9,
        popup=popup
    ).add_to(m)

    folium.Circle(
        location=[row.geometry.y, row.geometry.x],
        radius=2000,
        color=aro_color,
        fill=False,
        opacity=0.4
    ).add_to(m)

# =========================
# LEYENDA
# =========================
legend_html = """
<div style="
    position: fixed;
    bottom: 40px;
    left: 40px;
    width: 260px;
    z-index:9999;
    background-color: white;
    padding: 12px;
    border: 2px solid #555;
    border-radius: 6px;
    font-size: 14px;
">
<b>📍 Ventas en radio 2 km</b><br>
<span style="color:red;">●</span> &nbsp; Menos de 10 ventas<br>
<span style="color:orange;">●</span> &nbsp; 10 – 49 ventas<br>
<span style="color:green;">●</span> &nbsp; 50 o más ventas<br><br>
<b>🟦 Antenas</b>
</div>
"""

m.get_root().html.add_child(
    folium.Element(legend_html)
)

# =========================
# MOSTRAR MAPA
# =========================
st_folium(
    m,
    width=1500,
    height=650,
    returned_objects=[]
)

# =========================
# TABLA FINAL
# =========================
st.subheader("📊 Resumen de Antenas (2 km)")

st.dataframe(
    resumen_antenas.sort_values(
        "ventas_2km",
        ascending=False
    ),
    use_container_width=True
)