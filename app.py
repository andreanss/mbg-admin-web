import streamlit as st
import pandas as pd
import libsql_client

# ==========================================
# 1. KONFIGURASI HALAMAN WEB
# ==========================================
st.set_page_config(page_title="Admin Panel MBG", page_icon="🍲", layout="wide")

# ==========================================
# 2. SISTEM KEAMANAN (LOGIN)
# ==========================================
def cek_login():
    # Jika status login belum ada, set jadi False
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # Jika belum login, tampilkan form
    if not st.session_state["logged_in"]:
        st.title("🔒 Gerbang Keamanan MBG")
        st.write("Silakan masukkan kredensial Anda untuk mengakses database admin.")
        
        # Buat kotak form di tengah layar
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("form_login"):
                email = st.text_input("📧 Email Admin")
                password = st.text_input("🔑 Password", type="password")
                submit = st.form_submit_button("Masuk ke Dashboard", use_container_width=True)
                
                if submit:
                    # Cocokkan dengan data di brankas Streamlit Secrets
                    if email == st.secrets["ADMIN_EMAIL"] and password == st.secrets["ADMIN_PASSWORD"]:
                        st.session_state["logged_in"] = True
                        st.rerun() # Muat ulang halaman
                    else:
                        st.error("❌ Email atau Password salah!")
        return False
    return True

# Hentikan eksekusi kode ke bawah jika belum login
if not cek_login():
    st.stop()

# ==========================================
# 3. KONEKSI TURSO CLOUD & AMBIL DATA
# ==========================================
URL = "https://mbg-db-andreanss.aws-ap-northeast-1.turso.io"
TOKEN = st.secrets["TURSO_TOKEN"]

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

# ==========================================
# 4. RENDER APLIKASI UTAMA (SETELAH LOGIN)
# ==========================================
st.title("🎛️ Dashboard Dapur - Leuit Mangkubumi")

# Tambahkan tombol Logout di Sidebar kiri
st.sidebar.title("👤 Profil Admin")
st.sidebar.write(f"Masuk sebagai: **{st.secrets['ADMIN_EMAIL']}**")
if st.sidebar.button("🚪 Keluar (Logout)", type="primary"):
    st.session_state["logged_in"] = False
    st.rerun()

try:
    df_master = ambil_data_master()
    
    if not df_master.empty:
        tab_eksekutif, tab_johan, tab_normal = st.tabs([
            "📊 Dashboard Summary", 
            "🧑‍💻 Mode Johan", 
            "🏠 Mode Normal"
        ])

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
            st.warning("🗺️ **Peta Persebaran Dapur Dinonaktifkan Sementara.**\n\nFitur *live-geocoding* sedang dimatikan untuk menjaga performa panel admin tetap ringan dan cepat. Data koordinat lokasi sedang disiapkan di proses *backend* terpisah.")

        with tab_johan:
            st.subheader("📋 Workbook Dapur SPPG - khas Johan")
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

                    with st.expander(f"🏢 {yayasan} ({total_dapur} Total Baris {status_slot})"):
                        st.data_editor(
                            df_yayasan,
                            column_config={
                                "id_sppg": st.column_config.TextColumn("ID SPPG", disabled=True),
                                "nama_yayasan": st.column_config.TextColumn("Nama Yayasan", disabled=True),
                                "provinsi": st.column_config.TextColumn("Provinsi", disabled=True),
                                "status": st.column_config.SelectboxColumn(
                                    "Status Dapur",
                                    options=["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"],
                                    required=True
                                )
                            },
                            use_container_width=True,
                            num_rows="fixed",
                            key=f"edit_johan_{provinsi_terpilih}_{yayasan}"
                        )
                        if st.button(f"💾 Simpan Perubahan {yayasan}", key=f"btn_johan_{provinsi_terpilih}_{yayasan}"):
                            st.success(f"Perubahan data {yayasan} siap dikirim!")

        with tab_normal:
            st.subheader("🏠 Mode Manajemen Normal")
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
                    
                    with st.expander(f"🏢 {yayasan_global} ({total_dapur_global} Total Baris {status_slot_global})"):
                        st.data_editor(
                            df_yayasan_global,
                            column_config={
                                "status": st.column_config.SelectboxColumn(
                                    "Status Dapur",
                                    options=["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"],
                                    required=True
                                )
                            },
                            use_container_width=True,
                            num_rows="fixed",
                            key=f"edit_normal_yay_global_{yayasan_global}"
                        )
                        if st.button(f"💾 Simpan Data {yayasan_global}", key=f"btn_normal_yay_global_{yayasan_global}"):
                            st.success(f"Perubahan global untuk {yayasan_global} terekam!")

            with subtab_seluruhnya:
                st.data_editor(
                    df_master,
                    column_config={
                        "status": st.column_config.SelectboxColumn(
                            "Status Dapur",
                            options=["Proses Persiapan", "Penentuan KA SPPG", "PKS", "Selesai", "Dibatalkan", "Ditolak"],
                            required=True
                        )
                    },
                    use_container_width=True,
                    num_rows="dynamic",
                    height=500,
                    key="edit_normal_flat_view"
                )
                if st.button("💾 Simpan Seluruh Perubahan Database", type="primary", key="btn_normal_flat_save"):
                    st.success("Perubahan tabel besar siap ditembakkan ke Turso Cloud!")

    else:
        st.warning("Database Turso kosong.")

except Exception as e:
    st.error(f"Terjadi kesalahan sistem admin: {e}")