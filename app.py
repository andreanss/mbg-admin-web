import streamlit as st
import pandas as pd
import libsql_client
from datetime import datetime, timedelta

# ==========================================
# 1. KONFIGURASI HALAMAN WEB
# ==========================================
st.set_page_config(page_title="Admin Panel MBG", page_icon="🍲", layout="wide")

# ==========================================
# 2. SISTEM KEAMANAN (LOGIN)
# ==========================================
def cek_login():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.title("🔒 Gerbang Keamanan MBG")
        st.write("Silakan masukkan kredensial Anda untuk mengakses database admin.")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("form_login"):
                email = st.text_input("📧 Email Admin")
                password = st.text_input("🔑 Password", type="password")
                submit = st.form_submit_button("Masuk ke Dashboard", use_container_width=True)
                
                if submit:
                    if email == st.secrets["ADMIN_EMAIL"] and password == st.secrets["ADMIN_PASSWORD"]:
                        st.session_state["logged_in"] = True
                        st.session_state["admin_email"] = email
                        st.rerun()
                    else:
                        st.error("❌ Email atau Password salah!")
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
# 4. CALLBACK SINKRONISASI OTOMATIS & LOG
# ==========================================
def proses_perubahan_global(key, df_sumber, nama_mode):
    """Menangkap setiap perubahan pada data_editor secara otomatis tanpa tombol Simpan"""
    state = st.session_state[key]
    
    # A. PROSES EDIT DATA (Langsung Simpan & Masuk Log)
    edited = state.get("edited_rows", {})
    for row_idx, changes in edited.items():
        row_data = df_sumber.iloc[int(row_idx)]
        id_sppg = row_data["id_sppg"]
        
        for col, new_val in changes.items():
            eksekusi_query(f"UPDATE master_sppg SET {col} = ? WHERE id_sppg = ?", [new_val, id_sppg])
            catat_log("AUTO-EDIT DATA", f"[{nama_mode}] Mengubah kolom {col} menjadi '{new_val}' pada ID SPPG: {id_sppg}")
            
    # B. PROSES TAMBAH BARIS BARU (Jika ada input baris kosong di tabel)
    added = state.get("added_rows", {})
    for row in added:
        id_sppg = row.get("id_sppg", "").strip()
        if id_sppg:
            columns = [k for k in row.keys() if row[k] != '']
            values = [row[k] for k in columns]
            if columns:
                placeholders = ", ".join(["?"] * len(values))
                query = f"INSERT INTO master_sppg ({', '.join(columns)}) VALUES ({placeholders})"
                eksekusi_query(query, values)
                catat_log("ADD DATA VIA TABLE", f"[{nama_mode}] Menambahkan data dapur baru ID SPPG: {id_sppg}")

    # C. PROSES HAPUS BARIS (Ditahan dulu untuk Konfirmasi Dialog)
    deleted = state.get("deleted_rows", [])
    if deleted:
        ids_to_delete = []
        for row_idx in deleted:
            row_data = df_sumber.iloc[int(row_idx)]
            ids_to_delete.append(row_data["id_sppg"])
        # Lempar ke session state agar dipicu oleh dialog utama di thread rendering
        st.session_state["pending_delete_ids"] = ids_to_delete

    st.cache_data.clear()

# ==========================================
# 5. MODAL KONFIRMASI DIALOG UNTUK HAPUS
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
                catat_log("DELETE DATA", f"Menghapus baris data ID SPPG: {idx} melalui interaksi tabel")
            st.success("Berhasil dihapus!")
            if "pending_delete_ids" in st.session_state:
                del st.session_state["pending_delete_ids"]
            st.cache_data.clear()
            st.rerun()
    with col2:
        if st.button("Batal", use_container_width=True):
            if "pending_delete_ids" in st.session_state:
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
    
    if not hasil.rows:
        return pd.DataFrame()
        
    baris_data = [list(row) for row in hasil.rows]
    df = pd.DataFrame(baris_data, columns=hasil.columns)
    
    if not df.empty:
        df = df.fillna('')
        df = df.astype(str)
        df['status'] = df['status'].str.strip()
        df['nama_yayasan'] = df['nama_yayasan'].str.strip()
        df['provinsi'] = df['provinsi'].str.strip()
    return df

@st.cache_data(ttl=5)
def ambil_data_log():
    hasil = eksekusi_query("SELECT waktu, admin, aksi, detail FROM log_aktivitas ORDER BY id DESC LIMIT 100")
    if not hasil.rows:
        return pd.DataFrame()
    baris_data = [list(row) for row in hasil.rows]
    return pd.DataFrame(baris_data, columns=["Waktu (WIB)", "Admin", "Aksi", "Detail"])

# ==========================================
# 7. RENDER MANAGEMENT PANEL
# ==========================================
try:
    df_master = ambil_data_master()
    
    # Interseptor Dialog Konfirmasi jika ada antrean hapus data
    if "pending_delete_ids" in st.session_state and st.session_state["pending_delete_ids"]:
        tampilkan_konfirmasi_hapus(st.session_state["pending_delete_ids"])

    list_id_sppg = []
    if not df_master.empty:
        list_id_sppg = [x for x in df_master['id_sppg'].unique() if x.strip() != '']

    if not df_master.empty:
        tab_eksekutif, tab_johan, tab_normal, tab_alat = st.tabs([
            "📊 Dashboard", 
            "🧑‍💻 Mode Johan", 
            "🏠 Mode Normal",
            "🛠️ Alat Lanjutan"
        ])

        # --- TAB 1: DASHBOARD ---
        with tab_eksekutif:
            st.subheader("📊 Ringkasan Data Nasional")
            jml_selesai = df_master['status'].isin(['PKS', 'Selesai']).sum()
            jml_persiapan = (df_master['status'] == 'Proses Persiapan').sum()
            jml_yayasan = df_master[~df_master['status'].str.lower().isin(['dibatalkan', 'ditolak'])]['nama_yayasan'].nunique()

            col1, col2, col3 = st.columns(3)
            col1.metric("✅ Dapur Selesai / PKS", jml_selesai)
            col2.metric("⏳ Proses Persiapan", jml_persiapan)
            col3.metric("🏢 Total Yayasan Aktif", jml_yayasan)
            st.markdown("---")
            st.warning("🗺️ Peta Persebaran Dapur Dinonaktifkan Sementara untuk menjaga kecepatan sistem.")

        # --- TAB 2: MODE JOHAN ---
        with tab_johan:
            st.subheader("📋 Workbook Dapur SPPG - Gaya Johan")
            st.caption("💡 Setiap perubahan teks/status langsung tersimpan otomatis dan masuk log. Untuk menghapus baris, pilih baris lalu tekan tombol Delete pada keyboard atau ikon tong sampah di kanan bawah tabel.")
            
            list_provinsi = sorted([str(x) for x in df_master['provinsi'].unique() if str(x) != ''])
            if list_provinsi:
                provinsi_terpilih = st.selectbox("📂 Pilih Sheet Provinsi:", list_provinsi, key="sb_johan_prov")
                st.markdown(f"### 📍 Sheet: `{provinsi_terpilih}`")
                
                df_provinsi = df_master[df_master['provinsi'] == provinsi_terpilih]
                list_yayasan_di_prov = sorted([str(x) for x in df_provinsi['nama_yayasan'].unique() if str(x) != ''])
                
                for yayasan in list_yayasan_di_prov:
                    df_yayasan = df_provinsi[df_provinsi['nama_yayasan'] == yayasan]
                    df_aktif_yayasan = df_yayasan[~df_yayasan['status'].str.lower().isin(['dibatalkan', 'ditolak'])]
                    
                    total_aktif = len(df_aktif_yayasan)
                    total_dapur = len(df_yayasan)
                    slot_sisa = 10 - total_aktif
                    status_slot = f"| Sisa Slot: {slot_sisa}" if slot_sisa >= 0 else f"| ⚠️ OVERLOAD: {total_aktif}/10"

                    key_editor = f"edit_johan_{provinsi_terpilih}_{yayasan}"
                    with st.expander(f"🏢 {yayasan} ({total_dapur} Total Baris {status_slot})"):
                        st.data_editor(
                            df_yayasan,
                            column_config={
                                "id_sppg": st.column_config.TextColumn("ID SPPG", disabled=True),
                                "status": st.column_config.SelectboxColumn(
                                    "Status Dapur",
                                    options=["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"],
                                    required=True
                                )
                            },
                            use_container_width=True,
                            num_rows="dynamic", # Diubah ke dynamic agar tombol hapus muncul di baris
                            key=key_editor,
                            on_change=proses_perubahan_global,
                            args=(key_editor, df_yayasan, "MODE JOHAN")
                        )

        # --- TAB 3: MODE NORMAL ---
        with tab_normal:
            st.subheader("🏠 Mode Manajemen Normal")
            st.caption("💡 Seluruh tabel di bawah mendukung fitur auto-save & log instan, serta konfirmasi aman untuk penghapusan baris data.")
            
            subtab_per_yayasan, subtab_seluruhnya = st.tabs([
                "🏢 Tampilan 1: Kelompok Per Yayasan (Global)", 
                "🌐 Tampilan 2: Seluruh Data Master (Flat View)"
            ])
            
            with subtab_per_yayasan:
                list_yayasan_global = sorted([str(x) for x in df_master['nama_yayasan'].unique() if str(x) != ''])
                for yayasan_global in list_yayasan_global:
                    df_yayasan_global = df_master[df_master['nama_yayasan'] == yayasan_global]
                    df_aktif_global = df_yayasan_global[~df_yayasan_global['status'].str.lower().isin(['dibatalkan', 'ditolak'])]
                    
                    total_aktif_global = len(df_aktif_global)
                    total_dapur_global = len(df_yayasan_global)
                    slot_sisa_global = 10 - total_aktif_global
                    status_slot_global = f"| Sisa Slot Nasional: {slot_sisa_global}" if slot_sisa_global >= 0 else f"| ⚠️ OVERLOAD NASIONAL: {total_aktif_global}/10"
                    
                    key_editor_normal = f"edit_normal_yay_global_{yayasan_global}"
                    with st.expander(f"🏢 {yayasan_global} ({total_dapur_global} Total Baris {status_slot_global})"):
                        st.data_editor(
                            df_yayasan_global,
                            column_config={
                                "id_sppg": st.column_config.TextColumn("ID SPPG", disabled=True),
                                "status": st.column_config.SelectboxColumn(
                                    "Status Dapur",
                                    options=["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"],
                                    required=True
                                )
                            },
                            use_container_width=True,
                            num_rows="dynamic",
                            key=key_editor_normal,
                            on_change=proses_perubahan_global,
                            args=(key_editor_normal, df_yayasan_global, "NORMAL PER YAYASAN")
                        )

            with subtab_seluruhnya:
                key_editor_flat = "edit_normal_flat_view"
                st.data_editor(
                    df_master,
                    column_config={
                        "id_sppg": st.column_config.TextColumn("ID SPPG", disabled=False), # Biarkan false agar bisa input ID baru saat nambah baris
                        "status": st.column_config.SelectboxColumn(
                            "Status Dapur",
                            options=["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"],
                            required=True
                        )
                    },
                    use_container_width=True,
                    num_rows="dynamic",
                    height=500,
                    key=key_editor_flat,
                    on_change=proses_perubahan_global,
                    args=(key_editor_flat, df_master, "NORMAL FLAT VIEW")
                )

        # --- TAB 4: ALAT LANJUTAN ---
        with tab_alat:
            st.header("🛠️ Manajemen Database Master")
            col_bulk, col_hapus = st.columns(2)
            
            # FITUR BULK EDIT STATUS
            with col_bulk:
                st.subheader("🔄 Bulk Edit Status")
                st.caption("Ubah status banyak dapur sekaligus tanpa perlu edit satu per satu.")
                pilihan_status = ["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"]
                bulk_ids = st.multiselect("1. Pilih beberapa ID SPPG:", list_id_sppg)
                bulk_status = st.selectbox("2. Pilih Status Baru:", pilihan_status)
                
                if st.button("Terapkan Status Massal", type="primary"):
                    if not bulk_ids:
                        st.error("Pilih minimal 1 ID SPPG terlebih dahulu!")
                    else:
                        placeholders = ", ".join(["?"] * len(bulk_ids))
                        query = f"UPDATE master_sppg SET status = ? WHERE id_sppg IN ({placeholders})"
                        params = [bulk_status] + bulk_ids
                        try:
                            eksekusi_query(query, params)
                            catat_log("BULK UPDATE STATUS", f"Mengubah {len(bulk_ids)} ID ({', '.join(bulk_ids)}) menjadi {bulk_status} via Alat Lanjutan")
                            st.success(f"Berhasil mengupdate {len(bulk_ids)} data dapur!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal update: {e}")

            # FITUR HAPUS DATA MANUAL (YANG SUDAH OKE)
            with col_hapus:
                st.subheader("🗑️ Hapus Data Dapur")
                st.caption("Hapus permanen baris data dari database berdasarkan ID SPPG.")
                hapus_id = st.selectbox("1. Pilih ID SPPG yang ingin dihapus:", [""] + list_id_sppg)
                
                if hapus_id:
                    st.warning(f"⚠️ Peringatan: Baris data dengan ID **{hapus_id}** akan musnah permanen dari Turso!")
                    konfirmasi = st.checkbox(f"Saya sadar dan yakin ingin menghapus {hapus_id}")
                    if st.button("Hapus Permanen", type="primary"):
                        if not konfirmasi:
                            st.error("Silakan centang kotak konfirmasi terlebih dahulu!")
                        else:
                            try:
                                eksekusi_query("DELETE FROM master_sppg WHERE id_sppg = ?", [hapus_id])
                                catat_log("DELETE DATA", f"Menghapus baris data ID SPPG: {hapus_id} via Alat Lanjutan")
                                st.success(f"Data {hapus_id} berhasil dihapus dari database!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menghapus: {e}")

            st.markdown("---")
            st.subheader("📝 Log Aktivitas Sistem")
            st.caption("Menampilkan riwayat operasi Edit dan Hapus (Terbaru di atas).")
            df_log = ambil_data_log()
            if not df_log.empty:
                st.dataframe(df_log, use_container_width=True)
            else:
                st.info("Belum ada aktivitas yang terekam.")

    else:
        st.warning("Database Turso kosong.")

except Exception as e:
    st.error(f"Terjadi kesalahan sistem admin: {e}")