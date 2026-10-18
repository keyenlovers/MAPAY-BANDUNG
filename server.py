
from pathlib import Path
import json

import networkx as nx
import osmnx as ox
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from geopy.geocoders import Nominatim
from pydantic import BaseModel
from shapely import wkt
from shapely.geometry import shape


# ==========================================
# 1. KONFIGURASI
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "website"
GRAPH_FILE = BASE_DIR / "jaringan_jalan_bandung.graphml"
CSV_FILE = BASE_DIR / "fasilitas_bandung.csv"
WORK_FILE = BASE_DIR / "fasilitas_work_baru.csv"
EXTRA_FILE = BASE_DIR / "fasilitas_tambahan.csv"

CATEGORIES = [
    "Housing",
    "Work",
    "Commerce",
    "Health",
    "Education",
    "Entertainment",
]

ALL_CATEGORIES = CATEGORIES + ["Lainnya"]

SPECIFIC_CATEGORIES = [
    "Semua",
    "Pendidikan",
    "Kesehatan",
    "RTH",
    "Belanja",
    "Lainnya",
]

WALK_SPEED_KMH = 3.0
BIKE_SPEED_KMH = 10.0
LIMIT_MINUTES = 15

app = FastAPI(title="MAPAY Bandung")

for file_path in [GRAPH_FILE, CSV_FILE, WEB_DIR / "index.html"]:
    if not file_path.exists():
        raise FileNotFoundError(
            f"File tidak ditemukan: {file_path}"
        )


# ==========================================
# 2. MEMUAT DATA
# ==========================================

print("Memuat jaringan jalan Bandung...")
G = ox.load_graphml(GRAPH_FILE)
G = ox.convert.to_undirected(G)

print("Memuat data fasilitas utama...")
df = pd.read_csv(
    CSV_FILE,
    dtype={"id": str}
).fillna("")


def normalize_ids(data):
    if {"element", "id"}.issubset(data.columns):
        data["element"] = (
            data["element"]
            .astype(str)
            .str.lower()
            .str.strip()
        )
        data["id"] = (
            data["id"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.strip()
        )
    return data


df = normalize_ids(df)

# Muat data Work lama jika tersedia.
if WORK_FILE.exists():
    df_work = pd.read_csv(
        WORK_FILE,
        dtype={"id": str}
    ).fillna("")

    df_work = normalize_ids(df_work)

    if (
        {"element", "id"}.issubset(df.columns)
        and {"element", "id"}.issubset(df_work.columns)
    ):
        existing_ids = set(zip(df["element"], df["id"]))

        mask = ~df_work.apply(
            lambda row: (
                row["element"], row["id"]
            ) in existing_ids,
            axis=1,
        )

        df_work = df_work.loc[mask].copy()

        df = pd.concat(
            [df, df_work],
            ignore_index=True,
            sort=False,
        )

        print(
            f"Data Work baru ditambahkan: {len(df_work)}"
        )
    else:
        print(
            "Peringatan: kolom identitas Work tidak lengkap."
        )

# Muat fasilitas tambahan.
if EXTRA_FILE.exists():
    df_extra = pd.read_csv(
        EXTRA_FILE,
        dtype={"id": str}
    ).fillna("")

    df_extra = normalize_ids(df_extra)

    if (
        {"element", "id"}.issubset(df.columns)
        and {"element", "id"}.issubset(df_extra.columns)
    ):
        existing_ids = set(zip(df["element"], df["id"]))

        mask = ~df_extra.apply(
            lambda row: (
                row["element"], row["id"]
            ) in existing_ids,
            axis=1,
        )

        df_extra = df_extra.loc[mask].copy()

        df = pd.concat(
            [df, df_extra],
            ignore_index=True,
            sort=False,
        )

        print(
            "Fasilitas tambahan baru ditambahkan: "
            f"{len(df_extra)}"
        )
    else:
        print(
            "Peringatan: kolom identitas fasilitas "
            "tambahan tidak lengkap."
        )
else:
    print("fasilitas_tambahan.csv tidak ditemukan.")

df = df.fillna("")
print(f"Total baris data gabungan: {len(df)}")

geolocator = Nominatim(
    user_agent="mapay_bandung_student_project"
)


# ==========================================
# 3. MEMBACA GEOMETRI
# ==========================================

def get_geometry(value):
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        if value.lstrip().startswith("{"):
            data = json.loads(value)

            if data.get("type") == "Feature":
                data = data.get("geometry")

            if not data:
                return None

            return shape(data)

        return wkt.loads(value)

    except Exception:
        return None


# ==========================================
# 4. MEMBACA TAG DAN KATEGORI
# ==========================================

def tag(row, column):
    value = row.get(column, "")

    if pd.isna(value):
        return ""

    return str(value).strip().lower()


def categorize(row):
    amenity = tag(row, "amenity")
    shop = tag(row, "shop")
    leisure = tag(row, "leisure")
    healthcare = tag(row, "healthcare")
    education = tag(row, "education")
    building = tag(row, "building")
    landuse = tag(row, "landuse")
    office = tag(row, "office")
    tourism = tag(row, "tourism")
    sport = tag(row, "sport")
    workplace = tag(row, "workplace")

    imported_category = tag(row, "category")

    if imported_category == "pendidikan":
        return "Education"

    if imported_category == "kesehatan":
        return "Health"

    if imported_category == "rth":
        return "Entertainment"

    if imported_category == "belanja":
        return "Commerce"

    text = " ".join(
        str(row.get(column, ""))
        for column in row.index
        if column != "geometry"
    ).lower()

    # KESEHATAN
    if (
        amenity in {
            "hospital", "clinic", "doctors",
            "dentist", "pharmacy"
        }
        or healthcare not in {"", "no", "none"}
        or any(word in text for word in [
            "rumah sakit", "puskesmas",
            "klinik", "apotek", "dokter"
        ])
    ):
        return "Health"

    # PENDIDIKAN
    if (
        amenity in {
            "school", "kindergarten", "university",
            "college", "language_school", "childcare"
        }
        or education not in {"", "no", "none"}
        or building in {"school", "university", "college"}
        or any(word in text for word in [
            "sekolah", "kampus", "universitas",
            "pendidikan", "perguruan tinggi"
        ])
    ):
        return "Education"

    # HUNIAN
    if (
        landuse == "residential"
        or building in {
            "residential", "apartments", "house",
            "detached", "semidetached_house",
            "terrace", "dormitory", "bungalow"
        }
        or any(word in text for word in [
            "perumahan", "permukiman", "residential",
            "apartemen", "apartment", "kost", "kos-kosan"
        ])
    ):
        return "Housing"

    # TEMPAT KERJA
    if (
        office not in {"", "no", "none"}
        or workplace not in {"", "no", "none"}
        or building in {"office", "industrial"}
        or landuse in {"commercial", "industrial"}
        or any(word in text for word in [
            "perkantoran", "kantor", "office",
            "industrial", "kawasan industri",
            "coworking", "co-working"
        ])
    ):
        return "Work"

    # PERDAGANGAN
    if (
        shop not in {"", "no", "none"}
        or amenity in {"marketplace", "supermarket"}
        or any(word in text for word in [
            "supermarket", "marketplace",
            "shopping_mall", "department_store",
            "convenience", "pasar", "mall", "mal",
            "toko", "belanja"
        ])
    ):
        return "Commerce"

    # HIBURAN DAN REKREASI
    if (
        leisure in {
            "park", "garden", "playground",
            "nature_reserve", "recreation_ground",
            "sports_centre", "stadium", "fitness_centre",
            "water_park", "pitch", "golf_course"
        }
        or tourism in {
            "museum", "gallery", "attraction",
            "theme_park", "zoo"
        }
        or amenity in {
            "cinema", "theatre", "arts_centre",
            "community_centre", "nightclub",
            "library", "social_centre"
        }
        or sport not in {"", "no", "none"}
        or any(word in text for word in [
            "taman", "rekreasi", "hiburan",
            "bioskop", "museum", "galeri",
            "teater", "kebun binatang",
            "tempat wisata"
        ])
    ):
        return "Entertainment"

    return "Lainnya"


# ==========================================
# KATEGORI SPESIFIK — VERSI BARU
# ==========================================

def specific_category(row, main_category):
    imported_category = tag(row, "category")

    imported_mapping = {
        "pendidikan": "Pendidikan",
        "kesehatan": "Kesehatan",
        "rth": "RTH",
        "belanja": "Belanja",
        "lainnya": "Lainnya",
    }

    # Prioritaskan kategori dari CSV tambahan.
    if imported_category in imported_mapping:
        return imported_mapping[imported_category]

    amenity = tag(row, "amenity")
    shop = tag(row, "shop")
    leisure = tag(row, "leisure")
    healthcare = tag(row, "healthcare")
    education = tag(row, "education")
    building = tag(row, "building")
    landuse = tag(row, "landuse")

    # Pendidikan
    if (
        amenity in {
            "school", "kindergarten", "university",
            "college", "language_school", "childcare"
        }
        or education not in {"", "no", "none"}
        or building in {"school", "university", "college"}
    ):
        return "Pendidikan"

    # Kesehatan
    if (
        amenity in {
            "hospital", "clinic", "doctors",
            "dentist", "pharmacy"
        }
        or healthcare not in {"", "no", "none"}
    ):
        return "Kesehatan"

    # Ruang terbuka hijau
    if (
        leisure in {
            "park", "garden", "nature_reserve",
            "recreation_ground"
        }
        or landuse == "recreation_ground"
    ):
        return "RTH"

    # Perdagangan dan belanja
    if (
        shop not in {"", "no", "none"}
        or amenity in {"marketplace", "supermarket"}
    ):
        return "Belanja"

    if main_category == "Lainnya":
        return "Lainnya"

    return None


# ==========================================
# 5. MEMPROSES FASILITAS
# ==========================================

facilities = []


# ==========================================
# 5. MEMPROSES FASILITAS — VERSI LEBIH CEPAT
# ==========================================

import numpy as np

facilities = []
print("Mengolah koordinat fasilitas...")

invalid_geometry = 0
outside_area = 0
unmatched_road = 0

valid_rows = []
valid_lons = []
valid_lats = []

# Tahap 1: baca geometri dan kumpulkan koordinat.
for _, row in df.iterrows():
    geom = get_geometry(str(row.get("geometry", "")))

    if geom is None or geom.is_empty:
        invalid_geometry += 1
        continue

    point = geom.representative_point()
    lon, lat = point.x, point.y

    if not (
        -7.1 <= lat <= -6.7
        and 107.3 <= lon <= 107.9
    ):
        outside_area += 1
        continue

    valid_rows.append((row, lat, lon))
    valid_lons.append(lon)
    valid_lats.append(lat)

print(f"Koordinat valid: {len(valid_rows)}")
print("Mencari node jalan secara berkelompok...")

# Tahap 2: cari node jalan sekaligus.
try:
    nearest_nodes = ox.distance.nearest_nodes(
        G,
        X=np.asarray(valid_lons),
        Y=np.asarray(valid_lats),
    )

    # Tahap 3: susun data fasilitas.
    for (row, lat, lon), node in zip(valid_rows, nearest_nodes):
        raw_name = row.get("name", "") or row.get("nama", "")
        name = str(raw_name).strip() or "Fasilitas tanpa nama"

        main_category = categorize(row)

        facilities.append({
            "name": name,
            "category": main_category,
            "specific_category": specific_category(
                row, main_category
            ),
            "lat": lat,
            "lon": lon,
            "node": node.item() if hasattr(node, "item") else node,
        })

except Exception as e:
    raise RuntimeError(
        f"Gagal mencocokkan koordinat ke jaringan jalan: {e}"
    ) from e

if not facilities:
    raise RuntimeError(
        "Tidak ada fasilitas dengan koordinat yang berhasil dibaca."
    )

print(f"Total baris CSV gabungan: {len(df)}")
print(f"Total fasilitas diproses: {len(facilities)}")
print(f"Geometri tidak terbaca: {invalid_geometry}")
print(f"Di luar batas wilayah: {outside_area}")
print(f"Gagal dicocokkan ke jalan: {unmatched_road}")

print("\n=== JUMLAH PER KATEGORI ===")
for category in ALL_CATEGORIES:
    total = sum(
        1 for item in facilities
        if item["category"] == category
    )
    print(f"{category}: {total}")

print("\n=== DAFTAR FASILITAS KESEHATAN ===")
health_facilities = [
    item for item in facilities
    if item["category"] == "Health"
]

for item in health_facilities:
    print(
        f'{item["name"]} | '
        f'{item["lat"]:.6f}, {item["lon"]:.6f}'
    )

print(f"Total fasilitas kesehatan: {len(health_facilities)}")

print("\n=== KANDIDAT TAG KESEHATAN YANG BELUM TERKLASIFIKASI ===")

health_tags = {
    "hospital", "clinic", "doctors", "dentist",
    "pharmacy", "health_post", "nursing_home"
}

candidate_count = 0

for _, row in df.iterrows():
    amenity = tag(row, "amenity")
    healthcare = tag(row, "healthcare")

    name = str(
        row.get("name", "") or row.get("nama", "")
    ).strip()

    text = " ".join(
        str(row.get(column, ""))
        for column in row.index
        if column != "geometry"
    ).lower()

    looks_health_related = (
        amenity in health_tags
        or healthcare not in {"", "no", "none"}
        or any(word in text for word in [
            "rumah sakit", "puskesmas",
            "klinik", "apotek", "dokter"
        ])
    )

    if looks_health_related and categorize(row) != "Health":
        candidate_count += 1
        print(
            f"Periksa: {name or 'Tanpa nama'} | "
            f"amenity={amenity} | healthcare={healthcare}"
        )

print(
    "Kandidat kesehatan yang belum masuk Health:",
    candidate_count
)


if not facilities:
    raise RuntimeError(
        "Tidak ada fasilitas dengan koordinat yang berhasil dibaca."
    )

print(f"Total baris CSV gabungan: {len(df)}")
print(f"Total fasilitas diproses: {len(facilities)}")
print(f"Geometri tidak terbaca: {invalid_geometry}")
print(f"Di luar batas wilayah: {outside_area}")
print(f"Gagal dicocokkan ke jalan: {unmatched_road}")

print("\n=== JUMLAH PER KATEGORI ===")

for category in ALL_CATEGORIES:
    total = sum(
        1 for item in facilities
        if item["category"] == category
    )
    print(f"{category}: {total}")

print("\n=== DAFTAR FASILITAS KESEHATAN ===")

health_facilities = [
    item for item in facilities
    if item["category"] == "Health"
]

for item in health_facilities:
    print(
        f'{item["name"]} | '
        f'{item["lat"]:.6f}, {item["lon"]:.6f}'
    )

print(
    f"Total fasilitas kesehatan: {len(health_facilities)}"
)

# Pemeriksaan kandidat fasilitas kesehatan.
print(
    "\n=== KANDIDAT TAG KESEHATAN "
    "YANG BELUM TERKLASIFIKASI ==="
)

health_tags = {
    "hospital", "clinic", "doctors", "dentist",
    "pharmacy", "health_post", "nursing_home"
}

candidate_count = 0

for _, row in df.iterrows():
    amenity = tag(row, "amenity")
    healthcare = tag(row, "healthcare")

    name = str(
        row.get("name", "") or row.get("nama", "")
    ).strip()

    text = " ".join(
        str(row.get(column, ""))
        for column in row.index
        if column != "geometry"
    ).lower()

    looks_health_related = (
        amenity in health_tags
        or healthcare not in {"", "no", "none"}
        or any(word in text for word in [
            "rumah sakit", "puskesmas",
            "klinik", "apotek", "dokter"
        ])
    )

    if (
        looks_health_related
        and categorize(row) != "Health"
    ):
        candidate_count += 1

        print(
            f"Periksa: {name or 'Tanpa nama'} | "
            f"amenity={amenity} | "
            f"healthcare={healthcare}"
        )

print(
    "Kandidat kesehatan yang belum masuk Health:",
    candidate_count,
)


# ==========================================
# 6. WEBSITE DAN MODEL REQUEST
# ==========================================

app.mount(
    "/static",
    StaticFiles(directory=WEB_DIR),
    name="static",
)


class AnalyzeRequest(BaseModel):
    lat: float
    lon: float
    mode: str = "walk"
    category: str = "Semua"


@app.get("/")
def home():
    return FileResponse(
        WEB_DIR / "index.html"
    )


# ==========================================
# API ANALISIS AKSES 15 MENIT
# ==========================================

@app.post("/api/analyze")
def analyze_access(request: AnalyzeRequest):
    # Validasi moda perjalanan
    mode = request.mode.lower()

    if mode not in {"walk", "bike"}:
        raise HTTPException(
            status_code=400,
            detail="Moda perjalanan harus walk atau bike."
        )

    speed_kmh = 3.0 if mode == "walk" else 10.0
    limit_minutes = 15
    limit_distance_m = speed_kmh * 1000 * limit_minutes / 60

    # Cari node jalan terdekat dari titik awal
    try:
        origin_node = ox.distance.nearest_nodes(
            G,
            X=request.lon,
            Y=request.lat,
        )

        # Hitung jarak melalui jaringan jalan, bukan garis lurus
        distances = nx.single_source_dijkstra_path_length(
            G,
            source=origin_node,
            cutoff=limit_distance_m,
            weight="length",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menghitung jaringan jalan: {e}",
        )

    selected_category = request.category.strip()
    results = []

    for item in facilities:
        # Filter berdasarkan kategori spesifik
        specific = item.get("specific_category")
        main = item.get("category")

        if (
            selected_category != "Semua"
            and selected_category not in {specific, main}
        ):
            continue

        # Ambil jarak dari jaringan jalan ke node fasilitas
        facility_node = item.get("node")
        distance_m = distances.get(facility_node)

        # Abaikan fasilitas yang tidak terjangkau dalam batas 15 menit
        if distance_m is None:
            continue

        minutes = distance_m / (speed_kmh * 1000 / 60)

        results.append({
            "name": item["name"],
            "category": specific or main or "Lainnya",
            "specific_category": specific,
            "lat": item["lat"],
            "lon": item["lon"],
            "minutes": round(minutes, 1),
            "distance_m": round(distance_m, 1),
        })

    # Urutkan dari fasilitas yang paling dekat
    results.sort(key=lambda item: item["distance_m"])

    # Hitung jumlah per kategori
    counts = {}
    for item in results:
        category = item["category"]
        counts[category] = counts.get(category, 0) + 1

    return {
        "mode": mode,
        "speed_kmh": speed_kmh,
        "limit_minutes": limit_minutes,
        "total": len(results),
        "counts": counts,
        "facilities": results,
    }



# ==========================================
# 7. STATUS API
# ==========================================

@app.get("/api/health")
def health():
    counts = {
        category: sum(
            1 for item in facilities
            if item["category"] == category
        )
        for category in ALL_CATEGORIES
    }

    specific_counts = {
        category: sum(
            1 for item in facilities
            if item["specific_category"] == category
        )
        for category in SPECIFIC_CATEGORIES
        if category != "Semua"
    }

    return {
        "status": "ok",
        "nodes": G.number_of_nodes(),
        "facilities": len(facilities),
        "categories": CATEGORIES,
        "counts": counts,
        "specific_counts": specific_counts,
    }


# ==========================================
# 8. DATA FASILITAS UNTUK PETA
# ==========================================

@app.get("/api/facilities")
def get_facilities():
    return [
        {
            "name": item["name"],
            "category": item["category"],
            "specific_category": item["specific_category"],
            "lat": item["lat"],
            "lon": item["lon"],
        }
        for item in facilities
    ]


# ==========================================
# AUTOCOMPLETE DARI DATABASE MAPAY
# ==========================================

@app.get("/api/suggest")
def suggest_places(q: str):
    query = q.strip().casefold()

    if len(query) < 2:
        return {"results": []}

    matches = []

    for place in facilities:
        name = str(place.get("name", "")).strip()

        if not name or name == "Fasilitas tanpa nama":
            continue

        name_lower = name.casefold()

        # Utamakan nama yang diawali teks pencarian
        if name_lower.startswith(query):
            score = 0
        elif query in name_lower:
            score = 1
        else:
            continue

        matches.append({
            "score": score,
            "name": name,
            "address": place.get("category", "Fasilitas"),
            "lat": float(place["lat"]),
            "lon": float(place["lon"]),
        })

    matches.sort(key=lambda item: (item["score"], item["name"].casefold()))

    results = [
        {key: value for key, value in item.items() if key != "score"}
        for item in matches[:5]
    ]

    return {"results": results}



# ==========================================
# 9. PENCARIAN TEMPAT / ALAMAT MAPAY
# ==========================================

@app.get("/api/geocode")
def geocode(q: str):
    query = q.strip()

    if len(query) < 2:
        raise HTTPException(
            status_code=400,
            detail="Ketik nama tempat atau alamat yang ingin dicari."
        )

    # Variasi pencarian: nama tempat dan alamat
    queries = [
        f"{query}, Bandung, Indonesia",
        f"{query}, Kota Bandung, Jawa Barat, Indonesia",
    ]

    results = []
    seen = set()

    for search_query in queries:
        try:
            found = geolocator.geocode(
                search_query,
                exactly_one=False,
                limit=5,
                timeout=15,
                country_codes="id",
            )
        except Exception:
            continue

        if not found:
            continue

        for item in found:
            key = (
                round(item.latitude, 5),
                round(item.longitude, 5),
            )

            if key in seen:
                continue

            seen.add(key)
            results.append({
                "lat": item.latitude,
                "lon": item.longitude,
                "address": item.address,
            })

        if len(results) >= 5:
            break

    if not results:
        raise HTTPException(
            status_code=404,
            detail=(
                "Tempat belum ditemukan. Coba nama tempat "
                "yang lebih dikenal atau pilih titik di peta."
            ),
        )

    # Sementara kembalikan hasil pertama.
    # Langkah berikutnya: tampilkan kandidat sebagai pilihan di frontend.
    return results[0]




import requests

# ==========================================
# 10. SARAN PENCARIAN TEMPAT MAPAY
# ==========================================

@app.get("/api/suggest")
def suggest_places(q: str):
    query = q.strip()

    if len(query) < 2:
        return {"results": []}

    try:
        response = requests.get(
            "https://photon.komoot.io/api/",
            params={
                "q": query,
                "lat": -6.9175,
                "lon": 107.6191,
                "limit": 5,
                "lang": "en",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as e:
        print("ERROR PHOTON:", repr(e))
        raise HTTPException(
            status_code=503,
            detail="Pencarian tempat sedang tidak tersedia."
        )

    results = []

    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        coordinates = feature.get("geometry", {}).get(
            "coordinates", []
        )

        if len(coordinates) < 2:
            continue

        # Utamakan hasil yang berada di Bandung
        city = (
            properties.get("city")
            or properties.get("county")
            or ""
        )

        state = properties.get("state", "")
        country = properties.get("country", "")

        if (
            "bandung" not in
            f"{city} {state}".lower()
        ):
            continue

        name = properties.get("name") or properties.get("street")

        if not name:
            continue

        address_parts = [
            properties.get("street"),
            properties.get("district"),
            city,
            state,
        ]

        address = ", ".join(
            dict.fromkeys(
                part for part in address_parts
                if part and part != name
            )
        ) or country

        results.append({
            "name": name,
            "address": address,
            "lat": coordinates[1],
            "lon": coordinates[0],
        })

    return {"results": results[:5]}
