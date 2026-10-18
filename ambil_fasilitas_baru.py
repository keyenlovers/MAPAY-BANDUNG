
import requests
import pandas as pd
import time
from shapely.geometry import Point

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Batas wilayah Bandung dan sekitarnya
BBOX = " -7.1,107.3,-6.7,107.9 "

KATEGORI = {
    "Pendidikan": [
        'nwr["amenity"~"^(school|kindergarten|college|university)$"]'
    ],
    "Kesehatan": [
        'nwr["amenity"~"^(hospital|clinic|doctors|dentist|pharmacy)$"]',
        'nwr["healthcare"]'
    ],
    "RTH": [
        'nwr["leisure"~"^(park|garden|recreation_ground)$"]'
    ],
    "Belanja": [
        'nwr["shop"]',
        'nwr["amenity"~"^(marketplace|supermarket)$"]'
    ],
    "Lainnya": [
        'nwr["amenity"="library"]',
        'nwr["amenity"="community_centre"]',
        'nwr["office"]'
    ]
}

session = requests.Session()
session.headers.update({
    "User-Agent": "MAPAYBandung/1.0 (school research project)"
})

semua_data = []

for kategori, filter_list in KATEGORI.items():
    for filter_osm in filter_list:
        query = f"""
        [out:json][timeout:60];
        (
          {filter_osm}({BBOX});
        );
        out center tags;
        """

        print(f"Mengambil kategori {kategori}: {filter_osm}")

        for percobaan in range(3):
            try:
                response = session.post(
                    OVERPASS_URL,
                    data={"data": query},
                    timeout=(20, 100)
                )
                response.raise_for_status()
                hasil = response.json()
                break
            except (requests.RequestException, ValueError) as e:
                print(f"Percobaan {percobaan + 1} gagal: {e}")
                hasil = None
                if percobaan < 2:
                    time.sleep(5 * (percobaan + 1))

        if hasil is None:
            print(f"Melewati filter ini: {kategori}")
            continue

        for item in hasil.get("elements", []):
            tags = item.get("tags", {})
            nama = tags.get("name") or tags.get("name:id")

            # Abaikan objek tanpa nama agar hasil lebih berguna
            if not nama:
                continue

            if "lat" in item and "lon" in item:
                lat, lon = item["lat"], item["lon"]
            elif "center" in item:
                lat = item["center"]["lat"]
                lon = item["center"]["lon"]
            else:
                continue

            semua_data.append({
                "element": item["type"],
                "id": item["id"],
                "name": nama,
                "category": kategori,
                "geometry": Point(lon, lat).wkt,
                "latitude": lat,
                "longitude": lon
            })

        print(f"Data terkumpul sementara: {len(semua_data)}")
        time.sleep(2)

if semua_data:
    df = pd.DataFrame(semua_data)
    df = df.drop_duplicates(subset=["element", "id"])
    df.to_csv("fasilitas_tambahan.csv", index=False, encoding="utf-8-sig")

    print("\nSELESAI!")
    print(f"Jumlah objek unik: {len(df)}")
    print(df["category"].value_counts())
    print("File tersimpan: fasilitas_tambahan.csv")
else:
    print("\nBelum ada data yang berhasil diambil.")
    print("Coba lagi nanti atau gunakan sumber data alternatif.")
