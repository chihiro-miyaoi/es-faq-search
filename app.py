import streamlit as st
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import os
import io
import datetime
from cryptography.fernet import Fernet
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
MODEL_NAME = "intfloat/multilingual-e5-small"
COMPANY_NAME = "生和不動産株式会社"
ENCRYPTED_DIR = "encrypted_assets"

# ★ここにマニュアルのリンクを登録してください
MANUAL_LINKS = {
    "基本操作マニュアル": "https://drive.google.com/drive/folders/1mi0cHCJIAzKrLNrGrpq5Q4IDtuodBO12?usp=drive_link",
    "お問い合わせアプリ": "https://essupport.pocketpost.life/",
}

# --- ページ設定 ---
st.set_page_config(
    page_title="いい生活 FAQ検索",
    page_icon="🔍",
    # layout="wide"
)

# --- 暗号化キー取得 ---
def get_fernet():
    if "decryption_key" not in st.secrets:
        st.error("復号キーが設定されていません。")
        return None
    return Fernet(st.secrets["decryption_key"])

def decrypt_file_to_bytes(filepath):
    if not os.path.exists(filepath): return None
    try:
        f = get_fernet()
        if f is None: return None
        with open(filepath, "rb") as file:
            encrypted_data = file.read()
        return f.decrypt(encrypted_data)
    except Exception as e:
        print(f"復号エラー: {e}")
        return None

# --- データロード ---
@st.cache_resource
def load_data_and_model():
    csv_enc_path = os.path.join(ENCRYPTED_DIR, "faq_dataset.csv.enc")
    if not os.path.exists(csv_enc_path):
        st.error("データファイルが見つかりません")
        return None, None, None
        
    csv_bytes = decrypt_file_to_bytes(csv_enc_path)
    if csv_bytes is None:
        st.error("データの復号に失敗しました")
        return None, None, None

    df = pd.read_csv(io.BytesIO(csv_bytes), encoding='utf-8-sig')
    
    df['search_text'] = (
        df['カテゴリ'].fillna('') + " " + 
        df['タイトル'].fillna('') + " " + 
        df['タイトル'].fillna('') + " " + 
        df['本文(Content)'].fillna('')
    )
    
    model = SentenceTransformer(MODEL_NAME)
    docs = df['search_text'].tolist()
    doc_embeddings = model.encode(["passage: " + str(doc) for doc in docs], show_progress_bar=True)
    
    return df, model, doc_embeddings

# --- PDF取得 ---
def get_pdf_data(original_filename):
    enc_path = os.path.join(ENCRYPTED_DIR, "pdfs", original_filename + ".enc")
    return decrypt_file_to_bytes(enc_path)

# --- UI・認証系 ---
def inject_custom_css():
    st.markdown(f"""
    <style>
        .footer {{
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #f0f2f6; color: #333;
            text-align: center; padding: 10px; font-size: 12px;
            border-top: 1px solid #ddd; z-index: 999;
        }}
        .block-container {{ padding-bottom: 60px; }}
        /* サイドバーのリンクボタンを見やすく */
        .stLinkButton a {{
            text-decoration: none;
            font-weight: bold;
        }}
    </style>
    <div class="footer">© 2025 {COMPANY_NAME}</div>
    """, unsafe_allow_html=True)

def format_category_display(category_text):
    if not isinstance(category_text, str): return "-"
    parts = category_text.split(' > ')
    exclude = ["トップカテゴリー", "いい生活デスクトップアプリ ～画面・機能から探す～"]
    cleaned = [p for p in parts if p.strip() not in exclude and p.strip()]
    if len(cleaned) > 1: cleaned.pop()
    return " > ".join(cleaned)

def check_password():
    if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 社内ログイン")
        st.markdown(f"**{COMPANY_NAME} 専用サービス**", unsafe_allow_html=True)
        pwd = st.text_input("パスワード", type="password")
        if pwd:
            if pwd == st.secrets.get("app_password", "eseikatsu2025"):
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        inject_custom_css()
    return False

def logout():
    st.session_state["password_correct"] = False
    st.rerun()

def log_to_sheet(query):
    try:
        if "gcp_service_account" in st.secrets and "spreadsheet_name" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
            client = gspread.authorize(creds)
            sheet = client.open(st.secrets["spreadsheet_name"]).sheet1
            sheet.append_row([datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), query])
    except: pass

# --- メイン処理 ---
def main():
    if not check_password(): return

    inject_custom_css()
    
    # --- サイドバー ---
    with st.sidebar:
        st.markdown(f"### 🏢 {COMPANY_NAME}")
        
        # ★マニュアルリンク集 (Streamlit 1.27以降の link_button を使用)
        if MANUAL_LINKS:
            st.markdown("##### 📘 操作マニュアル")
            for name, url in MANUAL_LINKS.items():
                # ドライブのアイコンっぽく
                st.link_button(f"📄 {name}", url)
        
        st.markdown("---")
        if st.button("ログアウト", icon="🚪"): logout()
        st.markdown("---")

    st.title("いい生活 FAQ検索")

    # データロード
    with st.spinner("サービスを起動中..."):
        df, model, doc_embeddings = load_data_and_model()

    if df is None: return

    # --- 絞り込み機能（初期値設定） ---
    with st.sidebar:
        st.header("絞り込み")
        all_cats = df['カテゴリ'].dropna().apply(format_category_display).unique()
        roots = sorted(list(set([c.split(' > ')[0] for c in all_cats if c])))
        
        options = ["すべて"] + roots
        
        # デフォルト値を「いい生活デスクトップアプリ」にする
        default_index = 0
        target_tool = "いい生活デスクトップアプリ"
        if target_tool in options:
            default_index = options.index(target_tool)
            
        selected_root = st.selectbox("ツール選択", options, index=default_index)

    # --- メインコンテンツ ---
    query = st.text_input("質問を入力してください", placeholder="例: 新しく賃貸借契約を登録したい, 入出金を一括で消し込みたい など")

    if query:
        log_to_sheet(query)
        
        query_embedding = model.encode(["query: " + query])
        similarities = cosine_similarity(query_embedding, doc_embeddings)[0]
        top_indices = np.argsort(similarities)[::-1]
        
        st.markdown("---")
        st.subheader(f"「{query}」の検索結果")

        hits = 0
        for index in top_indices:
            score = similarities[index]
            if score < 0.78: continue

            row = df.iloc[index]
            display_cat = format_category_display(row['カテゴリ'])
            
            # フィルタリング
            if selected_root != "すべて" and not display_cat.startswith(selected_root):
                continue

            with st.container():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"### 📄 {row['タイトル']}")
                    st.caption(f"**カテゴリ:** {display_cat} | **更新日:** {row['更新日']}")
                    st.info(str(row['本文(Content)'])[:150] + "...")
                
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("PDF取得", key=f"btn_{row['FAQ_ID']}"):
                        with st.spinner("PDFを復号中..."):
                            pdf_bytes = get_pdf_data(row['元ファイル名'])
                            if pdf_bytes:
                                st.download_button(
                                    label="💾 保存/表示",
                                    data=pdf_bytes,
                                    file_name=row['元ファイル名'],
                                    mime="application/pdf",
                                    key=f"dl_{row['FAQ_ID']}"
                                )
                            else:
                                st.error("ファイルなし")
            
            st.markdown("---")
            hits += 1
            if hits >= 10: break
        
        if hits == 0: st.warning("関連するFAQが見つかりませんでした。")

if __name__ == "__main__":
    main()