# kembarki

[english](README.md) · bahasa indonesia

## tentang project ini

kembarki artinya "mereka sama". aku bikin ini soalnya backup aku dupnya banyak bgt wkwk. file filenya ada di folder utama, tapi ternyata hal yang sama persis ada lagi di folder dalemnya. bayangin punya backups1, backups2, terus di dalemnya ada backups45 yang ga sengaja kamu paste disitu. ya gitu deh.

jadi tool ini ngecek satu folder plus semua folder di dalemnya, nyari file yang namanya sama, terus bikin report html. tinggal buka di browser, keliatan file mana yang dobel, ukurannya berapa, dan copyannya ada dimana aja.

cuma ngeliat doang, ga nyentuh apa apa. ga ngehapus, ga mindahin, ga ganti nama. bahkan filenya ga dibuka, cuma baca nama, ukuran sama tanggalnya. jadi video 10gb lebih pun langsung kelar.

## setup

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # cuma perlu kalo mau jalanin test
```

### kalo kamu pake uv package manager kayak aku, lebih mantep

```
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

atau ga usah activate segala, langsung aja `uv run kembarki.py ./folder/yang/mau/dicek`

## cara pake

### 1. cepet dan basic

```
python kembarki.py ./folder/yang/mau/dicek
```

udah gitu doang. nanti muncul `kembarki-report.html` di folder tempat kamu jalanin, tinggal buka di browser.

mau nyobain dulu sebelum dipake ke backup beneran? ada sample folder di repo ini, dalemnya 3 level dan isinya file .txt hewan hewan yang dobel dimana mana (iya, monyetnya bunyi uu aa). bahkan ada `backups45` nyelip di dalem `backups1/2024`, persis kayak kejadian aslinya.

```
python kembarki.py ./sample_folder_to_test
```

harusnya keluar 18 nama yang dobel, ada yang **same size** ada yang **size differs**.

### 2. pemakaian lanjutan

```
python kembarki.py /mnt/backup /mnt/archive -o dupes.html
python kembarki.py /mnt/backup --ignore-case --min-size 10M --exclude .git --exclude "*.tmp"
python kembarki.py /mnt/backup --layout table
python kembarki.py /mnt/backup --csv dupes.csv --json dupes.json
```

| opsi | fungsinya |
|---|---|
| `-o FILE` | tempat nyimpen report html (default `kembarki-report.html`) |
| `--layout grouped` atau `table` | tampilan awal reportnya, bisa diganti di halamannya juga |
| `--csv FILE`, `--json FILE` | report tambahan kalo mau dibuka di spreadsheet atau apa gitu |
| `--ignore-case` | `Photo.JPG` sama `photo.jpg` dianggap sama |
| `--min-size SIZE` | skip file kecil (`500K`, `10M`, `1G`) |
| `--exclude PATTERN` | skip file atau folder yang cocok, bisa dipake berkali kali |
| `--follow-symlinks` | ngikutin link, defaultnya mati |
| `-q` | ga usah nampilin progress |

## reportnya

- semua nama yang muncul lebih dari sekali, plus ukuran, tanggal sama lokasi tiap copyan
- **same size** artinya kemungkinan file yang sama, **size differs** artinya belum tentu
- yang paling makan tempat ada di paling atas
- tampilan grouped atau table, bisa ganti kapan aja
- ada kolom search, filter tipe file (video, gambar, audio, dll) sama filter same size / differs
- klik judul kolom buat sorting

catatan: sekarang masih nyocokin dari nama doang. ngecek isi file beneran (hashing) masih di backlog, liat `PLAN.md`.

## test

```
pytest
```
