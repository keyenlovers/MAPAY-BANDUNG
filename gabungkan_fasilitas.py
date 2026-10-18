
import pandas as pd
from pathlib import Path

# Baca data asli dan data tambahan
file_asli = Path("fasilitas_bandung.csv")
file_tambahan = Path("fasilitas_tambahan_housing_work.csv")

asli = pd.read_csv(file_asli, dtype={"id": str})
tambahan = pd.read_csv(file_tambahan, dtype={"id": str})

# Samakan format ID agar duplikasi dapat diperiksa
for df in [asli, tambahan]:
    df["element"] = df["element"].astype(str).str.lower().str.strip()
    df["id"] = df["id"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

# Hanya tambahkan objek yang belum ada di data asli
id_asli = set(zip(asli["element"], asli["id"]))
mask_baru = ~tambahan.apply(
    lambda row: (row["element"], row["id"]) in id_asli,
    axis=1
)
tambahan_baru = tambahan.loc[mask_baru].copy()

# Simpan terpisah agar data asli tetap aman
tambahan_baru.to_csv("fasilitas_work_baru.csv", index=False)

print("Data asli:", len(asli))
print("Data tambahan awal:", len(tambahan))
print("Data tambahan baru:", len(tambahan_baru))
print("File tersimpan: fasilitas_work_baru.csv")
print("\nContoh nama tempat:")
kolom_nama = "name"
if kolom_nama in tambahan_baru.columns:
    print(tambahan_baru[kolom_nama].dropna().head(10).to_string(index=False))

