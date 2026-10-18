
import osmnx as ox
import pandas as pd

# Batas perkiraan wilayah studi Bandung.
# Format: (batas barat, selatan, timur, utara)
WEST, SOUTH = 107.54, -6.98
EAST, NORTH = 107.75, -6.85

# Bagi wilayah menjadi empat kotak
MID_LON = (WEST + EAST) / 2
MID_LAT = (SOUTH + NORTH) / 2

TILES = [
    (WEST, SOUTH, MID_LON, MID_LAT),
    (MID_LON, SOUTH, EAST, MID_LAT),
    (WEST, MID_LAT, MID_LON, NORTH),
    (MID_LON, MID_LAT, EAST, NORTH),
]

# Setiap tag diambil sendiri-sendiri supaya permintaan lebih kecil.
HOUSING_TAGS = [
    {"building": "house"},
    {"building": "residential"},
    {"building": "apartments"},
    {"building": "detached"},
    {"building": "semidetached_house"},
    {"building": "terrace"},
    {"building": "dormitory"},
]

WORK_TAGS = [
    {"office": True},
    {"building": "office"},
    {"building": "industrial"},
    {"man_made": "works"},
]

def ambil_kategori(tags_list, kategori):
    semua = []

    for nomor, bbox in enumerate(TILES, start=1):
        for tags in tags_list:
            print(
                f"{kategori}: bagian {nomor}/4, "
                f"tag {tags}"
            )

            try:
                gdf = ox.features_from_bbox(
                    bbox=bbox,
                    tags=tags
                )

                if gdf.empty:
                    continue

                # Simpan WKT sebelum mengubah GeoDataFrame
                geometry_wkt = gdf.geometry.to_wkt()

                data = gdf.reset_index()
                data["geometry_wkt"] = geometry_wkt.to_numpy()
                data["kategori_tambahan"] = kategori

                # Identitas OSM dipertahankan untuk deduplikasi
                semua.append(pd.DataFrame(data))

            except Exception as e:
                print(f"  Gagal: {e}")

    if not semua:
        return pd.DataFrame()

    hasil = pd.concat(
        semua,
        ignore_index=True,
        sort=False
    )

    # Satu objek OSM dapat ditemukan melalui beberapa tag.
    # Hapus duplikasi berdasarkan jenis elemen dan ID.
    if "element" in hasil.columns and "id" in hasil.columns:
        hasil = hasil.drop_duplicates(
            subset=["element", "id"]
        )

    return hasil


housing = ambil_kategori(HOUSING_TAGS, "Housing")
work = ambil_kategori(WORK_TAGS, "Work")

if not housing.empty:
    housing.to_csv(
        "tambahan_housing.csv",
        index=False
    )
    print(f"\nHousing tersimpan: {len(housing)} objek")

if not work.empty:
    work.to_csv(
        "tambahan_work.csv",
        index=False
    )
    print(f"\nWork tersimpan: {len(work)} objek")

if housing.empty and work.empty:
    print("\nBelum ada data yang berhasil diambil.")

print("\nSelesai. Data utama tidak diubah.")
