
import osmnx as ox
import pandas as pd
import folium

print("Membuat peta fasilitas Kota Bandung...")

# Baca data fasilitas yang sudah dikumpulkan
facilities = pd.read_csv(
    "fasilitas_bandung.csv",
    low_memory=False
)


m = folium.Map(
    location=[-6.9175, 107.6191],
    zoom_start=12,
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri"
)



# Kelompokkan fasilitas berdasarkan kategori
groups = {
    "Sekolah": folium.FeatureGroup(name="Sekolah"),
    "Kesehatan": folium.FeatureGroup(name="Fasilitas kesehatan"),
    "Taman": folium.FeatureGroup(name="Taman"),
    "Pasar dan supermarket": folium.FeatureGroup(
        name="Pasar dan supermarket"
    )
}

for _, row in facilities.iterrows():
    # Ambil koordinat dari geometri objek
    try:
        geom = row.get("geometry")
        if pd.isna(geom):
            continue

        # Geometri CSV tersimpan sebagai teks WKT
        from shapely import wkt
        geom = wkt.loads(geom)

        if geom.is_empty:
            continue

        point = geom.representative_point()
        lat, lon = point.y, point.x

        if not (-7.1 < lat < -6.7 and 107.3 < lon < 108.0):
            continue

        amenity = str(row.get("amenity", ""))
        leisure = str(row.get("leisure", ""))
        shop = str(row.get("shop", ""))

        if amenity == "school":
            group = groups["Sekolah"]
            label = "Sekolah"
        elif amenity in ["hospital", "clinic", "doctors"]:
            group = groups["Kesehatan"]
            label = "Fasilitas kesehatan"
        elif leisure == "park":
            group = groups["Taman"]
            label = "Taman"
        elif amenity == "marketplace" or shop == "supermarket":
            group = groups["Pasar dan supermarket"]
            label = "Pasar/supermarket"
        else:
            continue

        folium.CircleMarker(
            location=[lat, lon],
            radius=3,
            popup=label,
            tooltip=label,
            fill=True
        ).add_to(group)

    except Exception:
        continue

for group in groups.values():
    group.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

m.save("peta_fasilitas_bandung.html")

print("Peta berhasil dibuat!")
print("Buka file peta_fasilitas_bandung.html di browser.")
