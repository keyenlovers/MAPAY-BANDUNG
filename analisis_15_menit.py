
import os
import json
import ast
import pandas as pd
import osmnx as ox
import networkx as nx
import folium

from shapely import wkt
from shapely.geometry import shape


# ==========================================
# 1. PENGATURAN
# ==========================================

FILE_JALAN = "jaringan_jalan_bandung.graphml"
FILE_FASILITAS = "fasilitas_bandung.csv"

FILE_CSV_HASIL = "hasil_akses_15_menit.csv"
FILE_PETA = "hasil_peta_akses_15_menit.html"

KECEPATAN_JALAN_KAKI = 4.5  # km/jam
WAKTU_MENIT = 15
JARAK_MAKS = KECEPATAN_JALAN_KAKI * 1000 / 60 * WAKTU_MENIT

# 30 titik eksplorasi di wilayah Bandung
LATITUDES = [-6.95, -6.93, -6.91, -6.89, -6.87]
LONGITUDES = [
    107.57, 107.59, 107.61,
    107.63, 107.65, 107.67
]


# ==========================================
# 2. MEMBACA DATA
# ==========================================

print("Membaca jaringan jalan...")

if not os.path.exists(FILE_JALAN):
    raise FileNotFoundError(
        f"File {FILE_JALAN} tidak ditemukan. "
        "Pastikan script berada di folder proyek yang benar."
    )

if not os.path.exists(FILE_FASILITAS):
    raise FileNotFoundError(
        f"File {FILE_FASILITAS} tidak ditemukan."
    )

G_asli = ox.load_graphml(FILE_JALAN)

# Menggunakan jaringan dua arah untuk simulasi jalan kaki
G = ox.convert.to_undirected(G_asli)

# Pastikan setiap sisi memiliki panjang
for u, v, key, data in G.edges(keys=True, data=True):
    if "length" not in data:
        data["length"] = 1

print(f"Jumlah simpul jalan: {len(G.nodes):,}")
print(f"Jumlah sisi jalan: {len(G.edges):,}")

print("\nMembaca data fasilitas...")
df = pd.read_csv(FILE_FASILITAS)

print(f"Jumlah baris CSV: {len(df):,}")
print("Kolom CSV:", list(df.columns))


# ==========================================
# 3. MEMBACA GEOMETRY DARI CSV
# ==========================================

def ubah_geometry(nilai):
    if nilai is None:
        return None

    if not isinstance(nilai, str) and pd.isna(nilai):
        return None

    if hasattr(nilai, "geom_type"):
        return nilai

    teks = str(nilai).strip()

    if not teks or teks.lower() in ["nan", "none", "null"]:
        return None

    # Format WKT, misalnya POINT (...) atau POLYGON (...)
    try:
        geom = wkt.loads(teks)
        if not geom.is_empty:
            return geom
    except Exception:
        pass

    # Format GeoJSON
    try:
        data = json.loads(teks)
        if isinstance(data, dict):
            if "geometry" in data:
                data = data["geometry"]
            geom = shape(data)
            if not geom.is_empty:
                return geom
    except Exception:
        pass

    # Format dictionary Python
    try:
        data = ast.literal_eval(teks)
        if isinstance(data, dict):
            if "geometry" in data:
                data = data["geometry"]
            geom = shape(data)
            if not geom.is_empty:
                return geom
    except Exception:
        pass

    return None


if "geometry" in df.columns:
    df["geometry"] = df["geometry"].apply(ubah_geometry)

    df = df.dropna(subset=["geometry"]).copy()

    # Mengambil titik yang berada di dalam geometri fasilitas
    df["titik"] = df["geometry"].apply(
        lambda geom: geom.representative_point()
    )

    df["latitude"] = df["titik"].apply(lambda titik: titik.y)
    df["longitude"] = df["titik"].apply(lambda titik: titik.x)

else:
    # Jika CSV ternyata sudah mempunyai koordinat
    pasangan_koordinat = [
        ("latitude", "longitude"),
        ("lat", "lon"),
        ("lat", "lng"),
        ("y", "x")
    ]

    pasangan = next(
        (
            (lat, lon)
            for lat, lon in pasangan_koordinat
            if lat in df.columns and lon in df.columns
        ),
        None
    )

    if pasangan is None:
        raise ValueError(
            "CSV tidak mempunyai kolom geometry atau koordinat."
        )

    df["latitude"] = pd.to_numeric(
        df[pasangan[0]], errors="coerce"
    )
    df["longitude"] = pd.to_numeric(
        df[pasangan[1]], errors="coerce"
    )

df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

df = df.dropna(subset=["latitude", "longitude"]).copy()

# Menghapus koordinat yang tidak masuk akal untuk wilayah Bandung
df = df[
    df["latitude"].between(-7.1, -6.7)
    & df["longitude"].between(107.3, 107.9)
].copy()

if df.empty:
    raise ValueError(
        "Tidak ada koordinat fasilitas yang valid. "
        "Periksa format kolom geometry di CSV."
    )

print(f"Fasilitas dengan koordinat valid: {len(df):,}")


# ==========================================
# 4. MENGGOLONGKAN FASILITAS
# ==========================================

def teks_baris(baris):
    kolom_tags = [
        "amenity", "shop", "leisure", "healthcare",
        "building", "landuse", "office", "tourism",
        "name", "type", "category"
    ]

    nilai = []

    for kolom in kolom_tags:
        if kolom in baris.index and pd.notna(baris[kolom]):
            nilai.append(str(baris[kolom]).lower())

    return " ".join(nilai)


def kategori_fasilitas(baris):
    teks = teks_baris(baris)

    # Pendidikan
    if any(k in teks for k in [
        "school", "kindergarten", "university",
        "college", "education", "preschool"
    ]):
        return "Pendidikan"

    # Kesehatan
    if any(k in teks for k in [
        "hospital", "clinic", "doctors",
        "healthcare", "dentist", "pharmacy"
    ]):
        return "Kesehatan"

    # Ruang terbuka hijau
    if any(k in teks for k in [
        "park", "playground", "garden",
        "recreation_ground"
    ]):
        return "Ruang Terbuka"

    # Belanja dan kebutuhan harian
    if any(k in teks for k in [
        "supermarket", "convenience", "marketplace",
        "greengrocer", "department_store",
        "mall", "market", "grocery"
    ]):
        return "Belanja"

    return "Lainnya"


df["kategori"] = df.apply(kategori_fasilitas, axis=1)

print("\nJumlah fasilitas per kategori:")
print(df["kategori"].value_counts().to_string())


# ==========================================
# 5. MEMASANG FASILITAS KE JARINGAN JALAN
# ==========================================

print("\nMemetakan fasilitas ke jaringan jalan...")

df["node_jalan"] = ox.distance.nearest_nodes(
    G,
    X=df["longitude"].tolist(),
    Y=df["latitude"].tolist()
)

# Koordinat setiap simpul jalan
node_lat = nx.get_node_attributes(G, "y")
node_lon = nx.get_node_attributes(G, "x")


# ==========================================
# 6. MEMBUAT 30 TITIK SAMPEL
# ==========================================

print("\nMembuat titik sampel...")

titik_sampel = []

for lat in LATITUDES:
    for lon in LONGITUDES:
        titik_sampel.append({
            "latitude": lat,
            "longitude": lon
        })

hasil = []

for nomor, titik in enumerate(titik_sampel, start=1):
    node_awal = ox.distance.nearest_nodes(
        G,
        X=titik["longitude"],
        Y=titik["latitude"]
    )

    hasil.append({
        "id_titik": nomor,
        "latitude": titik["latitude"],
        "longitude": titik["longitude"],
        "node_awal": node_awal
    })

sampel_df = pd.DataFrame(hasil)


# ==========================================
# 7. ANALISIS JANGKAUAN 15 MENIT
# ==========================================

print("\nMenghitung jangkauan jalan kaki 15 menit...")
print(f"Asumsi jarak maksimum: {JARAK_MAKS:.0f} meter")

hasil_analisis = []

for _, sampel in sampel_df.iterrows():
    node_awal = sampel["node_awal"]

    # Menghitung jarak terpendek melalui jaringan jalan
    jarak_node = nx.single_source_dijkstra_path_length(
        G,
        source=node_awal,
        cutoff=JARAK_MAKS,
        weight="length"
    )

    node_terjangkau = set(jarak_node.keys())

    # Hitung fasilitas yang simpul jalannya terjangkau
    fasilitas_terjangkau = df[
        df["node_jalan"].isin(node_terjangkau)
    ]

    hitung = fasilitas_terjangkau["kategori"].value_counts()

    hasil_analisis.append({
        "id_titik": int(sampel["id_titik"]),
        "latitude": sampel["latitude"],
        "longitude": sampel["longitude"],
        "asumsi_waktu_menit": WAKTU_MENIT,
        "asumsi_kecepatan_kmh": KECEPATAN_JALAN_KAKI,
        "jangkauan_jalan_meter": round(JARAK_MAKS),
        "jumlah_node_terjangkau": len(node_terjangkau),
        "pendidikan": int(hitung.get("Pendidikan", 0)),
        "kesehatan": int(hitung.get("Kesehatan", 0)),
        "ruang_terbuka": int(hitung.get("Ruang Terbuka", 0)),
        "belanja": int(hitung.get("Belanja", 0)),
        "fasilitas_lainnya": int(hitung.get("Lainnya", 0)),
        "total_fasilitas": len(fasilitas_terjangkau)
    })

    print(
        f"Titik {int(sampel['id_titik']):02d}/"
        f"{len(sampel_df)} selesai"
    )

hasil_df = pd.DataFrame(hasil_analisis)

hasil_df.to_csv(FILE_CSV_HASIL, index=False, encoding="utf-8-sig")

print(f"\nHasil CSV disimpan: {FILE_CSV_HASIL}")


# ==========================================
# 8. MEMBUAT PETA INTERAKTIF
# ==========================================

print("\nMembuat peta interaktif...")

peta = folium.Map(
    location=[-6.91, 107.61],
    zoom_start=12,
    tiles="OpenStreetMap"
)


# Warna berdasarkan total fasilitas terjangkau
maks_fasilitas = max(
    1, hasil_df["total_fasilitas"].max()
)

for _, baris in hasil_df.iterrows():
    total = int(baris["total_fasilitas"])

    if total == 0:
        warna = "red"
    elif total < maks_fasilitas / 2:
        warna = "orange"
    else:
        warna = "green"

    popup_html = f"""
    <b>Titik sampel {int(baris['id_titik'])}</b><br>
    Total fasilitas terjangkau: {total}<br>
    Pendidikan: {int(baris['pendidikan'])}<br>
    Kesehatan: {int(baris['kesehatan'])}<br>
    Ruang terbuka: {int(baris['ruang_terbuka'])}<br>
    Belanja: {int(baris['belanja'])}<br>
    Lainnya: {int(baris['fasilitas_lainnya'])}<br>
    Jarak maksimum: {int(baris['jangkauan_jalan_meter'])} meter
    """

    folium.CircleMarker(
        location=[baris["latitude"], baris["longitude"]],
        radius=8,
        color=warna,
        fill=True,
        fill_opacity=0.75,
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=f"Titik {int(baris['id_titik'])}: {total} fasilitas"
    ).add_to(peta)

folium.LayerControl().add_to(peta)

peta.save(FILE_PETA)


# ==========================================
# 9. RINGKASAN HASIL
# ==========================================

print("\n" + "=" * 45)
print("ANALISIS SELESAI")
print("=" * 45)

print(f"Jumlah titik sampel: {len(hasil_df)}")
print(f"Jumlah fasilitas yang dianalisis: {len(df)}")
print(
    "Rata-rata fasilitas terjangkau per titik: "
    f"{hasil_df['total_fasilitas'].mean():.2f}"
)
print(
    "Titik dengan fasilitas terjangkau terbanyak: "
    f"{int(hasil_df.loc[hasil_df['total_fasilitas'].idxmax(), 'id_titik'])}"
)
print(
    "Titik dengan fasilitas terjangkau paling sedikit: "
    f"{int(hasil_df.loc[hasil_df['total_fasilitas'].idxmin(), 'id_titik'])}"
)

print(f"\nFile hasil tabel: {FILE_CSV_HASIL}")
print(f"File hasil peta: {FILE_PETA}")
print("\nBuka file HTML peta melalui browser.")
