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
    """Fungsi pembantu untuk menembak query ke Turso"""
    client = libsql_client.create_client_sync(url=URL, auth_token=TOKEN)
    hasil = client.execute(query, params)
    client.close()
    return hasil

def waktu_wib():
    """Mengambil waktu sekarang di zona WIB (UTC+7)"""
    return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")

def inisialisasi_log():
    """Membuat tabel log di Turso jika belum ada"""
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
    """Merekam aktivitas ke dalam tabel log"""
    admin = st.session_state.get("admin_email", "Unknown")
    eksekusi_query(
        "INSERT INTO log_aktivitas (waktu, admin, aksi, detail) VALUES (?, ?, ?, ?)",
        [waktu_wib(), admin, aksi, detail]
    )

# Jalankan inisialisasi tabel log saat web dimuat
inisialisasi_log()

@st.cache_data(ttl=5)
def ambil_data_master():
    hasil = eksekusi_query("SELECT * FROM master_sppg")
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
# 4. RENDER APLIKASI UTAMA
# ==========================================
st.title("🎛️ Admin Panel - Program MBG")

st.sidebar.title("👤 Profil Admin")
st.sidebar.write(f"Masuk sebagai: **{st.session_state.get('admin_email', '')}**")
if st.sidebar.button("🚪 Keluar (Logout)", type="primary"):
    st.session_state["logged_in"] = False
    st.rerun()

try:
    df_master = ambil_data_master()
    list_id_sppg = []
    if not df_master.empty:
        list_id_sppg = [x for x in df_master['id_sppg'].unique() if x.strip() != '']

    if not df_master.empty:
        # Menambahkan Tab 4 untuk Alat Lanjutan
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

        # --- TAB 2 & 3: MODE VIEW ---
        with tab_johan:
            st.info("💡 Mode ini saat ini berfokus sebagai Viewer. Untuk mengedit status banyak ID sekaligus, silakan gunakan tab **🛠️ Alat Lanjutan**.")
            # Menampilkan dataframe simpel per provinsi
            list_provinsi = sorted([str(x) for x in df_master['provinsi'].unique() if str(x) != ''])
            if list_provinsi:
                provinsi_terpilih = st.selectbox("📂 Pilih Sheet Provinsi:", list_provinsi)
                df_provinsi = df_master[df_master['provinsi'] == provinsi_terpilih]
                st.dataframe(df_provinsi, use_container_width=True)

        with tab_normal:
            st.info("💡 Menampilkan seluruh tabel database master.")
            st.dataframe(df_master, use_container_width=True, height=500)

        # --- TAB 4: ALAT LANJUTAN (HAPUS, BULK EDIT, LOG) ---
        with tab_alat:
            st.header("🛠️ Manajemen Database Master")
            
            col_bulk, col_hapus = st.columns(2)
            
            # FITUR 1: BULK EDIT
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
                        # Buat query dinamis sesuai jumlah ID
                        placeholders = ", ".join(["?"] * len(bulk_ids))
                        query = f"UPDATE master_sppg SET status = ? WHERE id_sppg IN ({placeholders})"
                        params = [bulk_status] + bulk_ids
                        
                        try:
                            eksekusi_query(query, params)
                            # Catat ke Log
                            catat_log("BULK UPDATE STATUS", f"Mengubah {len(bulk_ids)} ID ({', '.join(bulk_ids)}) menjadi {bulk_status}")
                            st.success(f"Berhasil mengupdate {len(bulk_ids)} data dapur!")
                            st.cache_data.clear() # Bersihkan cache agar web langsung terupdate
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal update: {e}")

            # FITUR 2: HAPUS DATA
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
                                # Catat ke Log
                                catat_log("DELETE DATA", f"Menghapus baris data ID SPPG: {hapus_id}")
                                st.success(f"Data {hapus_id} berhasil dihapus dari database!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menghapus: {e}")

            st.markdown("---")
            
            # FITUR 3: LOG AKTIVITAS
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