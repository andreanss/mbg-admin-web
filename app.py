import streamlit as st
import pandas as pd
import libsql_client
import time
from datetime import datetime, timedelta

# ==========================================
# 1. KONFIGURASI HALAMAN WEB
# ==========================================
st.set_page_config(page_title="LEUIT JAYA JAYA JAYA!", page_icon="🍲", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
        [data-testid="collapsedControl"] {
            display: flex;
            align-items: center;
            background-color: #ff4b4b;
            border-radius: 5px;
            padding: 5px 15px;
            margin-top: 10px;
            margin-left: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            transition: 0.3s;
            width: auto;
        }
        [data-testid="collapsedControl"] svg {
            display: none;
        }
        [data-testid="collapsedControl"]::after {
            content: "➔ 🔍 Buka Pencarian";
            font-weight: bold;
            font-size: 14px;
            color: white;
        }
        [data-testid="collapsedControl"]:hover {
            background-color: #e03e3e;
            cursor: pointer;
        }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SISTEM KEAMANAN & ANTI-HACKING
# ==========================================
PILIHAN_STATUS = ["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"]

def cek_login():
    if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
    if "failed_attempts" not in st.session_state: st.session_state["failed_attempts"] = 0
    if "lockout_until" not in st.session_state: st.session_state["lockout_until"] = None
    
    # Menyelaraskan semua filter agar konsisten
    if "f_status" not in st.session_state: st.session_state["f_status"] = PILIHAN_STATUS
    if "j_status" not in st.session_state: st.session_state["j_status"] = PILIHAN_STATUS
    if "n_status" not in st.session_state: st.session_state["n_status"] = PILIHAN_STATUS
    
    if "trigger_js_tab" not in st.session_state: st.session_state["trigger_js_tab"] = False
    if "prev_search" not in st.session_state: st.session_state["prev_search"] = ""

    if not st.session_state["logged_in"]:
        st.title("🔒 Gerbang Keamanan MBG")
        st.write("Silakan masukkan kredensial Anda untuk mengakses database admin.")
        
        if st.session_state["lockout_until"]:
            if datetime.now() < st.session_state["lockout_until"]:
                sisa_waktu = (st.session_state["lockout_until"] - datetime.now()).seconds
                menit, detik = divmod(sisa_waktu, 60)
                st.error(f"🚫 Akses diblokir sementara karena terlalu banyak percobaan gagal. Silakan coba lagi dalam {menit} menit {detik} detik.")
                st.stop()
            else:
                st.session_state["failed_attempts"] = 0
                st.session_state["lockout_until"] = None

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("form_login"):
                username = st.text_input("👤 Username / Email")
                password = st.text_input("🔑 Password", type="password")
                submit = st.form_submit_button("Masuk ke Dashboard", use_container_width=True)
                
                if submit:
                    if username in st.secrets["users"] and password == st.secrets["users"][username]:
                        st.session_state["logged_in"] = True
                        st.session_state["admin_email"] = username
                        st.session_state["failed_attempts"] = 0
                        st.rerun()
                    else:
                        time.sleep(2)
                        st.session_state["failed_attempts"] += 1
                        
                        if st.session_state["failed_attempts"] >= 3:
                            st.session_state["lockout_until"] = datetime.now() + timedelta(minutes=5)
                            st.error("🚫 Akses diblokir! Anda telah gagal 3x berturut-turut.")
                            st.rerun()
                        else:
                            sisa = 3 - st.session_state["failed_attempts"]
                            st.error(f"❌ Username atau Password salah! (Sisa percobaan: {sisa})")
        return False
    return True

if not cek_login():
    st.stop()

# ==========================================
# 3. KONEKSI TURSO & FUNGSI DATABASE
# ==========================================
URL = "https://mbg-db-andreanss.aws-ap-northeast-1.turso.io"
TOKEN = st.secrets["TURSO_TOKEN"]

def eksekusi_query(query, params=[]):
    client = libsql_client.create_client_sync(url=URL, auth_token=TOKEN)
    hasil = client.execute(query, params)
    client.close()
    return hasil

def waktu_wib():
    return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")

def inisialisasi_log():
    eksekusi_query("""
        CREATE TABLE IF NOT EXISTS log_aktivitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            waktu DATETIME,
            admin TEXT,
            aksi TEXT,
            detail TEXT
        )
    """)

def catat_log(aksi, detail):
    admin = st.session_state.get("admin_email", "Unknown")
    eksekusi_query(
        "INSERT INTO log_aktivitas (waktu, admin, aksi, detail) VALUES (?, ?, ?, ?)",
        [waktu_wib(), admin, aksi, detail]
    )

inisialisasi_log()

# ==========================================
# 4. CALLBACK SINKRONISASI OTOMATIS
# ==========================================
def proses_perubahan_global(key, df_sumber, nama_mode):
    state = st.session_state[key]
    
    edited = state.get("edited_rows", {})
    for row_idx, changes in edited.items():
        row_data = df_sumber.iloc[int(row_idx)]
        id_sppg = row_data["id_sppg"]
        for col, new_val in changes.items():
            eksekusi_query(f"UPDATE master_sppg SET {col} = ? WHERE id_sppg = ?", [new_val, id_sppg])
            catat_log("AUTO-EDIT DATA", f"[{nama_mode}] Mengubah '{col}' menjadi '{new_val}' pada ID SPPG: {id_sppg}")
            
    added = state.get("added_rows", {})
    for row in added:
        id_sppg = row.get("id_sppg", "").strip()
        if id_sppg:
            columns = [k for k in row.keys() if row[k] != '']
            values = [row[k] for k in columns]
            if columns:
                placeholders = ", ".join(["?"] * len(values))
                eksekusi_query(f"INSERT INTO master_sppg ({', '.join(columns)}) VALUES ({placeholders})", values)
                catat_log("ADD DATA", f"[{nama_mode}] Tambah ID SPPG baru: {id_sppg}")

    deleted = state.get("deleted_rows", [])
    if deleted:
        ids_to_delete = []
        for row_idx in deleted:
            row_data = df_sumber.iloc[int(row_idx)]
            ids_to_delete.append(row_data["id_sppg"])
        st.session_state["pending_delete_ids"] = ids_to_delete

    st.cache_data.clear()

# ==========================================
# 5. MODAL KONFIRMASI HAPUS
# ==========================================
@st.dialog("⚠️ Konfirmasi Penghapusan Permanen")
def tampilkan_konfirmasi_hapus(list_id):
    st.write("Apakah Anda yakin ingin menghapus permanent baris data dengan ID SPPG berikut?")
    for idx in list_id:
        st.markdown(f"- **`{idx}`**")
    st.error("Peringatan: Data yang terhapus dari Turso Cloud tidak dapat dikembalikan!")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Ya, Hapus Sekarang", type="primary", use_container_width=True):
            for idx in list_id:
                eksekusi_query("DELETE FROM master_sppg WHERE id_sppg = ?", [idx])
                catat_log("DELETE DATA", f"Menghapus baris data ID SPPG: {idx}")
            st.success("Berhasil dihapus!")
            del st.session_state["pending_delete_ids"]
            st.cache_data.clear()
            st.rerun()
    with col2:
        if st.button("Batal", use_container_width=True):
            del st.session_state["pending_delete_ids"]
            st.cache_data.clear()
            st.rerun()

# ==========================================
# 6. DATA FETCHING
# ==========================================
@st.cache_data(ttl=5)
def ambil_data_master():
    client = libsql_client.create_client_sync(url=URL, auth_token=TOKEN)
    hasil = client.execute("SELECT * FROM master_sppg")
    client.close()
    if not hasil.rows: return pd.DataFrame()
    baris_data = [list(row) for row in hasil.rows]
    df = pd.DataFrame(baris_data, columns=hasil.columns)
    if not df.empty:
        df = df.fillna('').astype(str)
        df['status'] = df['status'].str.strip()
        df['nama_yayasan'] = df['nama_yayasan'].str.strip()
        df['provinsi'] = df['provinsi'].str.strip()
    return df

@st.cache_data(ttl=5)
def ambil_data_log():
    hasil = eksekusi_query("SELECT waktu, admin, aksi, detail FROM log_aktivitas ORDER BY id DESC LIMIT 100")
    if not hasil.rows: return pd.DataFrame()
    return pd.DataFrame([list(row) for row in hasil.rows], columns=["Waktu (WIB)", "Admin", "Aksi", "Detail"])

# ==========================================
# 7. HEADER & RENDER APLIKASI
# ==========================================
col_title, col_logout = st.columns([8.5, 1.5])
with col_title:
    st.title("🎛️ Dapur MBG - LEUIT GROUP")
with col_logout:
    st.write("")
    with st.popover("⚙️ Setting", use_container_width=True):
        st.markdown(f"👤 **{st.session_state.get('admin_email', '')}**")
        st.markdown("---")
        st.info("💡 **Ganti Tema:** Klik ikon titik tiga `⋮` di pojok kanan atas layar browser, lalu pilih **Settings** ➔ **Theme**.")
        if st.button("🚪 Keluar (Logout)", type="primary", use_container_width=True):
            st.session_state.clear()
            st.rerun()

st.sidebar.title("🔍 Pencarian Global")
st.sidebar.caption("Ketik area, nama yayasan, atau ID SPPG untuk memfilter seluruh data.")
kata_kunci = st.sidebar.text_input("🔎 Masukkan kata kunci...").strip()

# LOGIKA AUTO-RESET FILTER JIKA ADA PENCARIAN BARU
if kata_kunci != st.session_state["prev_search"]:
    st.session_state["f_status"] = PILIHAN_STATUS
    st.session_state["j_status"] = PILIHAN_STATUS
    st.session_state["n_status"] = PILIHAN_STATUS
    st.session_state["prev_search"] = kata_kunci

try:
    df_master = ambil_data_master()
    
    if not df_master.empty and kata_kunci:
        mask = pd.Series([False] * len(df_master))
        for col in df_master.columns:
            mask = mask | df_master[col].astype(str).str.contains(kata_kunci, case=False, na=False)
        df_master = df_master[mask]

    if "pending_delete_ids" in st.session_state and st.session_state["pending_delete_ids"]:
        tampilkan_konfirmasi_hapus(st.session_state["pending_delete_ids"])

    list_id_sppg = [x for x in df_master['id_sppg'].unique() if x.strip() != ''] if not df_master.empty else []

    tab_eksekutif, tab_johan, tab_normal, tab_alat, tab_import = st.tabs([
        "📊 Dashboard", "🧑‍💻 Mode Johan", "🏠 Mode Normal", "🛠️ Bulk Edit dan Log", "📥 Import Scraping"
    ])

    # --- TAB 1: DASHBOARD ---
    with tab_eksekutif:
        if not df_master.empty:
            st.subheader("📊 Summary")
            jml_selesai = df_master['status'].isin(['PKS', 'Selesai']).sum()
            jml_persiapan = (df_master['status'] == 'Proses Persiapan').sum()
            jml_yayasan = df_master[~df_master['status'].str.lower().isin(['dibatalkan', 'ditolak'])]['nama_yayasan'].nunique()

            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("✅ Dapur Selesai / PKS", jml_selesai)
                if st.button("Lihat Detail Selesai/PKS ➔", use_container_width=True):
                    st.session_state["f_status"] = ["PKS", "Selesai"]
                    st.session_state["j_status"] = ["PKS", "Selesai"]
                    st.session_state["n_status"] = ["PKS", "Selesai"]
                    st.session_state["trigger_js_tab"] = True
                    st.rerun()
                    
            with col2:
                st.metric("⏳ Proses Persiapan", jml_persiapan)
                if st.button("Lihat Detail Persiapan ➔", use_container_width=True):
                    st.session_state["f_status"] = ["Proses Persiapan"]
                    st.session_state["j_status"] = ["Proses Persiapan"]
                    st.session_state["n_status"] = ["Proses Persiapan"]
                    st.session_state["trigger_js_tab"] = True
                    st.rerun()
                    
            with col3:
                st.metric("🏢 Total Yayasan Aktif", jml_yayasan)
                if st.button("Tampilkan Semua Data", use_container_width=True):
                    st.session_state["f_status"] = PILIHAN_STATUS
                    st.session_state["j_status"] = PILIHAN_STATUS
                    st.session_state["n_status"] = PILIHAN_STATUS
                    st.toast("🔄 Filter tabel dikembalikan ke semua status!", icon="🔄")
            
            st.markdown("---")
            
            col_dash1, col_dash2 = st.columns(2)
            
            with col_dash1:
                st.subheader("🏢 Sisa Slot Yayasan (Terbanyak)")
                semua_yayasan = df_master[df_master['nama_yayasan'] != '']['nama_yayasan'].unique()
                df_active = df_master[~df_master['status'].str.lower().isin(['dibatalkan', 'ditolak'])]
                terisi_dict = df_active['nama_yayasan'].value_counts().to_dict()
                
                data_slot = []
                for y in semua_yayasan:
                    terisi = terisi_dict.get(y, 0)
                    sisa = 10 - terisi
                    if sisa > 0:
                        data_slot.append({"Nama Yayasan": y, "Sisa Slot Kosong": sisa})
                
                if data_slot:
                    df_slots = pd.DataFrame(data_slot).sort_values(by='Sisa Slot Kosong', ascending=False).reset_index(drop=True)
                    st.dataframe(df_slots, use_container_width=True)
                else:
                    st.success("Semua yayasan pada pencarian ini sudah terisi penuh (10 slot).")

            with col_dash2:
                st.subheader("📍 Rincian Status per Provinsi")
                prov_list = []
                for prov in df_master[df_master['provinsi'] != '']['provinsi'].unique():
                    df_prov = df_master[df_master['provinsi'] == prov]
                    jml_persiapan_prov = (df_prov['status'] == 'Proses Persiapan').sum()
                    jml_selesai_prov = df_prov['status'].isin(['PKS', 'Selesai']).sum()
                    
                    if jml_persiapan_prov > 0 or jml_selesai_prov > 0:
                        prov_list.append({
                            "Provinsi": prov,
                            "Persiapan": jml_persiapan_prov,
                            "Selesai / PKS": jml_selesai_prov
                        })
                
                if prov_list:
                    df_prov_stat = pd.DataFrame(prov_list).sort_values(by="Provinsi").reset_index(drop=True)
                    st.dataframe(df_prov_stat, use_container_width=True)
                else:
                    st.info("Belum ada data dengan status tersebut di pencarian ini.")
        else:
            st.warning("Data tidak ditemukan atau Database Turso kosong. Silakan periksa kata kunci pencarian atau import data terlebih dahulu.")

    if not df_master.empty:
        # --- TAB 2: MODE JOHAN ---
        with tab_johan:
            st.subheader("📋 Workbook Dapur SPPG - Style Johan")
            col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
            j_filter_status = col_f1.multiselect("🔍 Tampilkan Status:", PILIHAN_STATUS, key="j_status")
            j_sort = col_f2.radio("⬇️ Urutkan Yayasan:", ["A - Z", "Z - A"], horizontal=True, key="j_sort")
            j_sort_isi = col_f3.radio("↕️ Urut Isi Tabel:", ["Default", "Status A-Z"], horizontal=True, key="j_sort_isi")
            st.markdown("---")

            list_provinsi = sorted([str(x) for x in df_master['provinsi'].unique() if str(x) != ''])
            if list_provinsi:
                provinsi_terpilih = st.selectbox("📂 Pilih Sheet Provinsi:", list_provinsi, key="sb_johan_prov")
                df_provinsi = df_master[df_master['provinsi'] == provinsi_terpilih]
                
                list_yayasan_di_prov = sorted([str(x) for x in df_provinsi['nama_yayasan'].unique() if str(x) != ''])
                if j_sort == "Z - A":
                    list_yayasan_di_prov.reverse()
                
                for yayasan in list_yayasan_di_prov:
                    df_yayasan = df_provinsi[df_provinsi['nama_yayasan'] == yayasan]
                    df_yayasan_filtered = df_yayasan[df_yayasan['status'].isin(j_filter_status)].reset_index(drop=True)
                    
                    if df_yayasan_filtered.empty: continue
                    if j_sort_isi == "Status A-Z": df_yayasan_filtered = df_yayasan_filtered.sort_values(by="status", ascending=True).reset_index(drop=True)
                    
                    total_dapur = len(df_yayasan)
                    key_editor = f"edit_johan_{provinsi_terpilih}_{yayasan}"
                    with st.expander(f"🏢 {yayasan} ({len(df_yayasan_filtered)} ditampilkan dari {total_dapur} total)"):
                        st.data_editor(
                            df_yayasan_filtered,
                            column_config={"id_sppg": st.column_config.TextColumn("ID SPPG", disabled=True),
                                           "status": st.column_config.SelectboxColumn("Status", options=PILIHAN_STATUS, required=True)},
                            use_container_width=True, num_rows="dynamic", key=key_editor,
                            on_change=proses_perubahan_global, args=(key_editor, df_yayasan_filtered, "MODE JOHAN")
                        )

        # --- TAB 3: MODE NORMAL ---
        with tab_normal:
            st.subheader("🏠 Mode Manajemen Normal")
            subtab_per_yayasan, subtab_seluruhnya = st.tabs(["🏢 Per Yayasan", "🌐 Data Master (Flat View)"])
            
            with subtab_per_yayasan:
                col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
                n_filter_status = col_f1.multiselect("🔍 Tampilkan Status:", PILIHAN_STATUS, key="n_status")
                n_sort = col_f2.radio("⬇️ Urutkan Yayasan:", ["A - Z", "Z - A"], horizontal=True, key="n_sort")
                n_sort_isi = col_f3.radio("↕️ Urut Isi Tabel:", ["Default", "Status A-Z"], horizontal=True, key="n_sort_isi")
                st.markdown("---")

                list_yayasan_global = sorted([str(x) for x in df_master['nama_yayasan'].unique() if str(x) != ''])
                if n_sort == "Z - A": list_yayasan_global.reverse()
                
                for yay_global in list_yayasan_global:
                    df_yayasan_global = df_master[df_master['nama_yayasan'] == yay_global]
                    df_yayasan_filtered = df_yayasan_global[df_yayasan_global['status'].isin(n_filter_status)].reset_index(drop=True)
                    
                    if df_yayasan_filtered.empty: continue
                    if n_sort_isi == "Status A-Z": df_yayasan_filtered = df_yayasan_filtered.sort_values(by="status", ascending=True).reset_index(drop=True)
                    
                    key_editor_normal = f"edit_normal_yay_global_{yay_global}"
                    with st.expander(f"🏢 {yay_global} ({len(df_yayasan_filtered)} ditampilkan)"):
                        st.data_editor(
                            df_yayasan_filtered,
                            column_config={"id_sppg": st.column_config.TextColumn("ID SPPG", disabled=True),
                                           "status": st.column_config.SelectboxColumn("Status", options=PILIHAN_STATUS, required=True)},
                            use_container_width=True, num_rows="dynamic", key=key_editor_normal,
                            on_change=proses_perubahan_global, args=(key_editor_normal, df_yayasan_filtered, "NORMAL PER YAYASAN")
                        )

            with subtab_seluruhnya:
                col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
                flat_filter = col_f1.multiselect("🔍 Status:", PILIHAN_STATUS, key="f_status")
                flat_sort_col = col_f2.selectbox("⬇️ Urutkan Kolom:", ["ID SPPG", "Nama Yayasan", "Provinsi", "Status"], key="f_sort_col")
                flat_sort_order = col_f3.radio("Arah:", ["A - Z", "Z - A"], horizontal=True, key="f_sort_order")
                
                col_map = {"ID SPPG": "id_sppg", "Nama Yayasan": "nama_yayasan", "Provinsi": "provinsi", "Status": "status"}
                df_flat = df_master[df_master['status'].isin(flat_filter)]
                df_flat = df_flat.sort_values(by=col_map[flat_sort_col], ascending=(flat_sort_order == "A - Z")).reset_index(drop=True)

                key_editor_flat = "edit_normal_flat_view"
                st.data_editor(
                    df_flat,
                    column_config={"id_sppg": st.column_config.TextColumn("ID SPPG", disabled=False),
                                   "status": st.column_config.SelectboxColumn("Status", options=PILIHAN_STATUS, required=True)},
                    use_container_width=True, height=500, num_rows="dynamic", key=key_editor_flat,
                    on_change=proses_perubahan_global, args=(key_editor_flat, df_flat, "NORMAL FLAT VIEW")
                )

        # --- TAB 4: ALAT LANJUTAN ---
        with tab_alat:
            st.header("🛠️ Manajemen Database Master")
            col_bulk, col_hapus = st.columns(2)
            
            with col_bulk:
                st.subheader("🔄 Bulk Edit Status")
                bulk_ids = st.multiselect("1. Pilih beberapa ID SPPG:", list_id_sppg)
                bulk_status = st.selectbox("2. Pilih Status Baru:", PILIHAN_STATUS)
                if st.button("Terapkan Status Massal", type="primary"):
                    if not bulk_ids: st.error("Pilih minimal 1 ID SPPG!")
                    else:
                        placeholders = ", ".join(["?"] * len(bulk_ids))
                        eksekusi_query(f"UPDATE master_sppg SET status = ? WHERE id_sppg IN ({placeholders})", [bulk_status] + bulk_ids)
                        catat_log("BULK UPDATE STATUS", f"Mengubah {len(bulk_ids)} ID menjadi {bulk_status}")
                        st.success(f"Berhasil mengupdate {len(bulk_ids)} data dapur!")
                        st.cache_data.clear(); st.rerun()

            with col_hapus:
                st.subheader("🗑️ Hapus Data Dapur")
                hapus_id = st.selectbox("1. Pilih ID SPPG yang ingin dihapus:", [""] + list_id_sppg)
                if hapus_id:
                    st.warning(f"⚠️ Peringatan: Baris data dengan ID **{hapus_id}** akan musnah!")
                    konfirmasi = st.checkbox("Saya sadar dan yakin ingin menghapus permanen.")
                    if st.button("Hapus Permanen", type="primary"):
                        if not konfirmasi: st.error("Silakan centang kotak konfirmasi!")
                        else:
                            eksekusi_query("DELETE FROM master_sppg WHERE id_sppg = ?", [hapus_id])
                            catat_log("DELETE DATA MANUAL", f"Menghapus baris data ID SPPG: {hapus_id}")
                            st.success(f"Data {hapus_id} berhasil dihapus!")
                            st.cache_data.clear(); st.rerun()

            st.markdown("---")
            st.subheader("📝 Log Aktivitas Sistem")
            df_log = ambil_data_log()
            if not df_log.empty: st.dataframe(df_log, use_container_width=True)
            else: st.info("Belum ada aktivitas yang terekam.")

    # --- TAB 5: IMPORT DATA SCRAPING ---
    with tab_import:
        st.header("📥 Import Data Hasil Scraping")
        st.info("Fitur ini dirancang khusus untuk memproses data keluaran *scraper* Anda. Upload file CSV atau Excel di sini untuk mendistribusikannya secara massal ke dalam database Turso tanpa perlu melalui VS Code.")
        
        file_upload = st.file_uploader("📂 Pilih File Data (Format didukung: .csv, .xlsx)", type=["csv", "xlsx"])
        
        if file_upload is not None:
            try:
                if file_upload.name.endswith('.csv'):
                    df_import = pd.read_csv(file_upload)
                else:
                    df_import = pd.read_excel(file_upload)
                
                df_import = df_import.fillna('').astype(str)
                
                st.write(f"🔍 **Preview Data:** Ditemukan {len(df_import)} baris siap di-import.")
                st.dataframe(df_import.head(10), use_container_width=True)
                
                kolom_file = list(df_import.columns)
                
                if "id_sppg" not in kolom_file:
                    st.error("⚠️ Proses ditolak: Kolom 'id_sppg' tidak ditemukan di dalam file. Pastikan nama header kolom di file hasil scraping Anda sudah benar.")
                else:
                    st.warning("Pastikan header/nama kolom di file sama persis dengan yang ada di database. Data yang ID-nya sudah ada kemungkinan akan mengalami penolakan (Duplicate Key) dari Turso jika dikonfigurasi unik.")
                    if st.button("🚀 Mulai Import Massal ke Database", type="primary"):
                        with st.spinner("⏳ Sedang menembakkan data hasil scraping ke server Turso..."):
                            sukses = 0
                            gagal = 0
                            
                            for index, row in df_import.iterrows():
                                id_sppg = row.get("id_sppg", "").strip()
                                if id_sppg:
                                    kolom_terisi = [k for k in kolom_file if row[k] != '']
                                    nilai_terisi = [row[k] for k in kolom_terisi]
                                    
                                    if kolom_terisi:
                                        placeholders = ", ".join(["?"] * len(nilai_terisi))
                                        query = f"INSERT INTO master_sppg ({', '.join(kolom_terisi)}) VALUES ({placeholders})"
                                        
                                        try:
                                            eksekusi_query(query, nilai_terisi)
                                            sukses += 1
                                        except Exception as e:
                                            gagal += 1
                                            
                            catat_log("IMPORT BULK SCRAPING", f"Upload file {file_upload.name} | Sukses: {sukses} baris | Gagal/Duplikat: {gagal} baris")
                            
                            if sukses > 0:
                                st.success(f"🎉 Selesai! Sebanyak {sukses} data berhasil di-import.")
                            if gagal > 0:
                                st.error(f"⚠️ Ditemukan {gagal} baris yang gagal di-import (Kemungkinan ID SPPG bentrok / sudah ada sebelumnya).")
                                
                            time.sleep(2.5)
                            st.cache_data.clear()
                            st.rerun()
                            
            except Exception as e:
                st.error(f"Terjadi kegagalan saat membaca file: {e}")

# ==========================================
# 8. SIHIR JAVASCRIPT UNTUK KLIK OTOMATIS
# ==========================================
if st.session_state.get("trigger_js_tab", False):
    js_pindah_tab = """
    <script>
        const parentDoc = window.parent.document;
        function clickTabByText(text) {
            const tabs = parentDoc.querySelectorAll('button[data-baseweb="tab"]');
            for (let i = 0; i < tabs.length; i++) {
                if (tabs[i].innerText.includes(text)) {
                    tabs[i].click();
                    return true;
                }
            }
            return false;
        }
        
        clickTabByText("Mode Normal");
        
        setTimeout(() => {
            clickTabByText("Data Master (Flat View)");
        }, 200);
    </script>
    """
    st.components.v1.html(js_pindah_tab, height=0, width=0)
    st.session_state["trigger_js_tab"] = False

except Exception as e:
    st.error(f"Terjadi kesalahan sistem admin: {e}")