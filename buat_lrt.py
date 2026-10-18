
import json
from pathlib import Path

output = Path("website/lrt_bandung.geojson")
output.parent.mkdir(parents=True, exist_ok=True)

data = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "route": "NS",
                "name": "Babakan Siliwangi - Margahayu",
                "system": "Greater Bandung LRT (2030)",
                "status": "Rencana"
            },
            "geometry": {
                "type": "LineString",
                "coordinates": []
            }
        },
        {
            "type": "Feature",
            "properties": {
                "route": "EW",
                "name": "Leuwipanjang - Tegalluar",
                "system": "Greater Bandung LRT (2030)",
                "status": "Rencana"
            },
            "geometry": {
                "type": "LineString",
                "coordinates": []
            }
        }
    ]
}

output.write_text(
    json.dumps(data, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print(f"File berhasil dibuat: {output}")
print("Catatan: koordinat rute belum diisi.")
