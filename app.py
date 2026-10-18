
import os
import json

import pandas as pd
import osmnx as ox
import networkx as nx
import streamlit as st
import folium

from shapely import wkt
from shapely.geometry import shape
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium


# ==========================================
# 1. KONFIGURASI APLIKASI
# ==========================================

st.set_page_config(
    page_title="MAPAY | Bandung 15-Minute City",
    page_icon="🗺️",
    layout="wide"
)

JALAN = "jaringan_jalan_bandung.graphml"
FASILITAS = "fasilitas_bandung.csv"

st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
div[data-testid="stMetric"] {
    background: #f2f5f2;
    padding: 14px;
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)

st.title("🗺️ MAPAY")
st.subheader("Bandung 15-Minute Accessibility")
st.write(
    "Temukan fasilitas di Bandung dan periksa perkiraan "
    "jangkauannya melalui jaringan jalan."
)

st.caption(
    "Versi prototipe penelitian. Data fasilitas berasal dari "
    "OpenStreetMap dan belum tentu mencakup seluruh fasilitas."
)


# ==========================================
# 2. MEMUAT DATA
# ==========================================

@st.cache_resource
def muat_jaringan():
    if not os.path.exists(JALAN):
        raise FileNotFoundError(f"File tidak ditemukan: {JALAN}")

    graph_asli = ox.load_graphml(JALAN)
    return ox.convert.to_undirected(graph_asli)


@st.cache_data
def muat_fasilitas():
    if not os.path.exists(FASILITAS):
        raise FileNotFoundError(
            f"File tidak ditemukan: {FASILITAS}"
        )

    df = pd.read_csv(FASILITAS)

    def baca_geometri(nilai):
        if not isinstance(nilai, str):
            return None

        teks = nilai.strip()

        try:
            geom = wkt.loads(teks)
            if not geom.is_empty:
                return geom
        except Exception:
            pass

        try:
            data = json.loads(teks)
            if "geometry" in data:
                data = data["geometry"]
            geom = shape(data)
            if not geom.is_empty:
                return geom
        except Exception:
            pass

        return None

    if "geometry" not in df.columns:
        raise ValueError("Kolom geometry tidak ditemukan.")

    df["geometry"] = df["geometry"].apply(baca_geometri)
    df = df.dropna(subset=["geometry"]).copy()

    titik = df["geometry"].apply(
        lambda g: g.representative_point()
    )

    df["latitude"] = titik.apply(lambda p: p.y)
    df["longitude"] = titik.apply(lambda p: p.x)

    # Batas koordinat umum wilayah Bandung
    df = df[
        df["latitude"].between(-7.1, -6.7)
        & df["longitude"].between(107.3, 107.9)
    ].copy()

    def kategori(baris):
        def nilai(kolom):
            if kolom not in baris.index:
                return ""
            v = baris[kolom]
            return "" if pd.isna(v) else str(v).lower()

        amenity = nilai("amenity")
        shop = nilai("shop")
        leisure = nilai("leisure")
        healthcare = nilai("healthcare")
        education = nilai("education")
        school = nilai("school")
        landuse = nilai("landuse")
        building = nilai("building")

        # Kesehatan
        if (
            amenity in ["hospital", "clinic", "doctors"]
            or healthcare
            or amenity == "pharmacy"
        ):
            return "Kesehatan"

        # Pendidikan
        if (
            amenity in [
                "school", "kindergarten", "university",
                "college", "language_school"
            ]
            or education
            or school
            or building in ["school", "university", "college"]
        ):
            return "Pendidikan"

        # Ruang terbuka hijau
        if (
            leisure in [
                "park", "garden", "playground",
                "nature_reserve", "recreation_ground"
            ]
            or landuse == "grass"
        ):
            return "RTH"

        # Tempat belanja
        if shop and shop not in ["no", ""]:
            return "Belanja"

        if amenity in ["marketplace", "supermarket"]:
            return "Belanja"

        return "Lainnya"

    df["kategori"] = df.apply(kategori, axis=1)

    return df.reset_index(drop=True)


try:
    with st.spinner("Memuat jaringan jalan dan fasilitas..."):
        G = muat_jaringan()
        df = muat_fasilitas()
except Exception as e:
    st.error(f"Gagal memuat data: {e}")
    st.stop()


# ==========================================
# 3. PANEL PENCARIAN
# ==========================================

st.sidebar.header("Cari aksesibilitas")

alamat = st.sidebar.text_input(
    "Lokasi awal",
    placeholder="Contoh: Gedung Sate, Bandung"
)

st.sidebar.caption(
    "Masukkan alamat atau nama tempat yang bisa ditemukan "
    "oleh layanan pencarian lokasi."
)

kategori_pilihan = st.sidebar.selectbox(
    "Kategori tujuan",
    ["Kesehatan", "Pendidikan", "RTH", "Belanja"]
)

moda = st.sidebar.radio(
    "Moda perjalanan",
    ["Jalan kaki", "Sepeda"]
)

durasi = st.sidebar.select_slider(
    "Batas waktu perjalanan",
    options=[5, 10, 15, 20, 30],
    value=15,
    format_func=lambda x: f"{x} menit"
)

st.sidebar.info(
    "Asumsi awal: jalan kaki 4,5 km/jam dan sepeda "
    "12 km/jam. Ini estimasi, bukan waktu perjalanan langsung."
)

cari = st.sidebar.button(
    "🔎 Analisis akses",
    type="primary",
    use_container_width=True
)


# ==========================================
# 4. PETA DASAR
# ==========================================

pusat = [-6.9147, 107.6098]

peta = folium.Map(
    location=pusat,
    zoom_start=12,
    tiles="OpenStreetMap",
    control_scale=True
)

# Data fasilitas dapat ditampilkan per kategori
warna = {
    "Kesehatan": "red",
    "Pendidikan": "blue",
    "RTH": "green",
    "Belanja": "orange"
}

lapisan = folium.FeatureGroup(
    name="Fasilitas Bandung",
    show=True
)

df_tampil = df[df["kategori"] != "Lainnya"]

for _, f in df_tampil.iterrows():
    nama = f.get("name", None)
    if pd.isna(nama) or not nama:
        nama = "Nama fasilitas belum tersedia"

    folium.CircleMarker(
        location=[f["latitude"], f["longitude"]],
        radius=4,
        color=warna.get(f["kategori"], "gray"),
        fill=True,
        fill_opacity=0.75,
        tooltip=str(nama),
        popup=(
            f"<b>{nama}</b><br>"
            f"Kategori: {f['kategori']}"
        )
    ).add_to(lapisan)

lapisan.add_to(peta)
folium.LayerControl().add_to(peta)


# ==========================================
# 5. HITUNG RUTE SAAT DIMINTA
# ==========================================

if cari:
    if not alamat.strip():
        st.warning("Masukkan lokasi awal terlebih dahulu.")
    else:
        try:
            with st.spinner("Mencari lokasi..."):
                geolocator = Nominatim(
                    user_agent="mapay_bandung_school_research"
                )

                lokasi = geolocator.geocode(
                    alamat + ", Bandung, Indonesia",
                    timeout=15
                )

            if lokasi is None:
                st.error(
                    "Lokasi tidak ditemukan. Coba gunakan nama "
                    "tempat atau alamat yang lebih spesifik."
                )
            else:
                lat_awal = lokasi.latitude
                lon_awal = lokasi.longitude

                # Pastikan titik awal berada di sekitar wilayah studi
                if not (
                    -7.1 <= lat_awal <= -6.7
                    and 107.3 <= lon_awal <= 107.9
                ):
                    st.error(
                        "Lokasi yang ditemukan berada di luar "
                        "batas wilayah analisis Bandung."
                    )
                    st.stop()

                node_awal = ox.distance.nearest_nodes(
                    G, X=lon_awal, Y=lat_awal
                )

                # Kecepatan asumsi
                kecepatan = (
                    4.5 if moda == "Jalan kaki" else 12.0
                )

                jarak_batas = (
                    kecepatan * 1000 / 60 * durasi
                )

                with st.spinner("Menghitung akses melalui jaringan jalan..."):
                    jarak_node = nx.single_source_dijkstra_path_length(
                        G,
                        source=node_awal,
                        cutoff=jarak_batas,
                        weight="length"
                    )

                df_kategori = df[
                    df["kategori"] == kategori_pilihan
                ].copy()

                df_kategori["node"] = ox.distance.nearest_nodes(
                    G,
                    X=df_kategori["longitude"].tolist(),
                    Y=df_kategori["latitude"].tolist()
                )

                # Jarak dihitung melalui jaringan jalan
                df_kategori["jarak_meter"] = (
                    df_kategori["node"].map(jarak_node)
                )

                terjangkau = df_kategori[
                    df_kategori["jarak_meter"].notna()
                ].copy()

                terjangkau = terjangkau.sort_values(
                    "jarak_meter"
                )

                # Tandai lokasi awal
                folium.Marker(
                    [lat_awal, lon_awal],
                    tooltip="Lokasi awal",
                    popup="Lokasi awal",
                    icon=folium.Icon(
                        color="blue", icon="home"
                    )
                ).add_to(peta)

                # Gambar rute ke fasilitas terdekat
                if not terjangkau.empty:
                    tujuan = terjangkau.iloc[0]
                    node_tujuan = tujuan["node"]

                    rute = nx.shortest_path(
                        G,
                        source=node_awal,
                        target=node_tujuan,
                        weight="length"
                    )

                    koordinat_rute = [
                        [G.nodes[n]["y"], G.nodes[n]["x"]]
                        for n in rute
                    ]

                    folium.PolyLine(
                        koordinat_rute,
                        color="#1769ff",
                        weight=6,
                        opacity=0.85,
                        tooltip="Rute jaringan jalan"
                    ).add_to(peta)

                    folium.Marker(
                        [
                            tujuan["latitude"],
                            tujuan["longitude"]
                        ],
                        tooltip=str(
                            tujuan.get("name", "Tujuan terdekat")
                        ),
                        popup=(
                            f"<b>{tujuan.get('name', 'Fasilitas')}</b>"
                            f"<br>Kategori: {kategori_pilihan}"
                            f"<br>Jarak jaringan: "
                            f"{tujuan['jarak_meter']:.0f} meter"
                        ),
                        icon=folium.Icon(
                            color="green", icon="flag"
                        )
                    ).add_to(peta)

                # Simpan hasil untuk ditampilkan
                st.session_state["mapay_hasil"] = {
                    "alamat": alamat,
                    "kategori": kategori_pilihan,
                    "moda": moda,
                    "durasi": durasi,
                    "jarak_batas": jarak_batas,
                    "terjangkau": terjangkau,
                    "lat": lat_awal,
                    "lon": lon_awal,
                    "peta": peta
                }

        except Exception as e:
            st.error(f"Analisis gagal: {e}")


# ==========================================
# 6. HASIL ANALISIS
# ==========================================

hasil = st.session_state.get("mapay_hasil")

if hasil:
    st.subheader("Hasil analisis aksesibilitas")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Fasilitas terjangkau",
        len(hasil["terjangkau"])
    )

    col2.metric(
        "Batas waktu",
        f"{hasil['durasi']} menit"
    )

    col3.metric(
        "Moda",
        hasil["moda"]
    )

    if len(hasil["terjangkau"]) > 0:
        st.success(
            f"Ditemukan {len(hasil['terjangkau'])} objek "
            f"kategori {hasil['kategori']} dalam jangkauan "
            f"model {hasil['durasi']} menit."
        )

        st.write("Fasilitas terdekat berdasarkan jarak jaringan:")

        tampil = hasil["terjangkau"].head(10).copy()

        kolom_nama = (
            "name" if "name" in tampil.columns else "id"
        )

        tampil["Jarak (meter)"] = (
            tampil["jarak_meter"].round(0).astype(int)
        )

        tampil["Estimasi waktu (menit)"] = (
            tampil["jarak_meter"] /
            (4.5 * 1000 / 60
             if hasil["moda"] == "Jalan kaki"
             else 12.0 * 1000 / 60)
        ).round(1)

        st.dataframe(
            tampil[
                [
                    kolom_nama,
                    "Jarak (meter)",
                    "Estimasi waktu (menit)"
                ]
            ].rename(columns={kolom_nama: "Nama fasilitas"}),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning(
            "Tidak ditemukan fasilitas kategori ini dalam "
            "jangkauan model. Periksa data dan jaringan jalan."
        )

    peta = hasil["peta"]
    peta.location = [hasil["lat"], hasil["lon"]]
    peta.zoom_start = 14

else:
    st.info(
        "Masukkan lokasi awal di panel kiri, pilih kategori, "
        "kemudian tekan Analisis akses."
    )


# ==========================================
# 7. TAMPILKAN PETA
# ==========================================

st.subheader("Peta interaktif Bandung")

st_folium(
    peta,
    width=None,
    height=600,
    key="mapay_map"
)

st.caption(
    "Sumber peta: OpenStreetMap. Hasil merupakan estimasi "
    "berbasis data dan asumsi model, bukan navigasi real-time."
)
