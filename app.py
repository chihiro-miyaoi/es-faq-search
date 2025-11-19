def main():
    # ★デバッグ用：持っているキーの一覧を表示（値は見せない）
    st.write("現在のSecretsキー:", st.secrets.keys()) 

    if not check_password(): return
    # ...

import streamlit as st
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import os
import datetime

# --- 暗号化・圧縮対応の追加 ---
import zipfile
import shutil
from cryptography.fernet import Fernet

# --- ログ用（設定が残っていれば使用） ---
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
MODEL_NAME = "intfloat/multilingual-e5-small"
COMPANY_NAME = "生和不動産株式会社"

# データの展開先設定
# Streamlit Cloudでは /tmp が書き込み可能な一時領域です
if os.path.exists("/tmp"):
    TEMP_DIR = "/tmp/faq_data_extracted"
else:
    TEMP_DIR = "temp_data_extracted" # ローカル用

DATASET_FILE = os.path.join(TEMP_DIR, "faq_dataset.csv")
PDF_DIR = os.path.join(TEMP_DIR, "faq_pdfs")
ENCRYPTED_DIR = "encrypted_data" # GitHub上の暗号化フォルダ

# --- ページ設定 ---
st.set_page_config(
    page_title="いい生活 FAQ検索",
    page_icon="🔍",
    # layout="wide" # コメントアウトのご要望通り
)

# --- 認証情報の取得ヘルパー ---
def get_gcp_creds():
    if "gcp_service_account" in st.secrets:
        return dict(st.secrets["gcp_service_account"])
    return None

# --- スプレッドシート接続 ---
def log_to_sheet(query):
    try:
        creds_dict = get_gcp_creds()
        if not creds_dict: return

        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        if "spreadsheet_name" in st.secrets:
            sheet = client.open(st.secrets["spreadsheet_name"]).sheet1
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.append_row([now, query])
    except Exception:
        pass # ログ保存エラーはアプリの動作に影響させない

# --- ★追加: データの復号と展開 ---
@st.cache_resource
def decrypt_and_extract_data():
    # 既に展開済みならスキップ（高速化）
    if os.path.exists(DATASET_FILE) and os.path.exists(PDF_DIR):
        return True

    try:
        # 1. 分割ファイルを結合
        encrypted_data = b""
        if not os.path.exists(ENCRYPTED_DIR):
            st.error(f"暗号化データフォルダ '{ENCRYPTED_DIR}' が見つかりません。")
            return False

        parts = sorted([f for f in os.listdir(ENCRYPTED_DIR) if f.startswith("data.enc.")])
        if not parts:
            st.error("暗号化データが見つかりません。")
            return False
        
        for part in parts:
            with open(os.path.join(ENCRYPTED_DIR, part), "rb") as f:
                encrypted_data += f.read()
        
        # 2. 復号
        if "decryption_key" not in st.secrets:
            st.error("復号キー(decryption_key)がSecretsに設定されていません。")
            return False
            
        key = st.secrets["decryption_key"]
        f = Fernet(key)
        decrypted_data = f.decrypt(encrypted_data)
        
        # 3. Zip展開
        # フォルダをクリーンにする
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)
            
        zip_path = os.path.join(TEMP_DIR, "data.zip")
        with open(zip_path, "wb") as f:
            f.write(decrypted_data)
            
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(TEMP_DIR)
            
        return True
    except Exception as e:
        st.error(f"データ展開エラー: {e}")
        return False

# --- データロード ---
@st.cache_resource
def load_data_and_model():
    # 復号処理を実行
    if not decrypt_and_extract_data():
        return None, None, None
    
    # CSV読み込み
    try:
        df = pd.read_csv(DATASET_FILE, encoding='utf-8-sig')
    except Exception as e:
        st.error(f"CSV読み込みエラー: {e}")
        return None, None, None
    
    # 検索用テキスト作成
    df['search_text'] = (
        df['カテゴリ'].fillna('') + " " + 
        df['タイトル'].fillna('') + " " + 
        df['タイトル'].fillna('') + " " + 
        df['本文(Content)'].fillna('')
    )
    
    model = SentenceTransformer(MODEL_NAME)
    
    # ベクトル化（メモリ上で計算）
    docs = df['search_text'].tolist()
    doc_embeddings = model.encode(["passage: " + str(doc) for doc in docs], show_progress_bar=True)
            
    return df, model, doc_embeddings

# --- UI系関数 ---
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
    </style>
    <div class="footer">© {COMPANY_NAME} - Internal Knowledge Search System</div>
    """, unsafe_allow_html=True)

def format_category_display(category_text):
    if not isinstance(category_text, str): return "-"
    parts = category_text.split(' > ')
    exclude = ["トップカテゴリー", "いい生活デスクトップアプリ ～画面・機能から探す～"]
    cleaned = [p for p in parts if p.strip() not in exclude and p.strip()]
    if len(cleaned) > 1: cleaned.pop()
    return " > ".join(cleaned)

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True
        
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 社内ログイン")
        st.markdown(f"**{COMPANY_NAME} 専用システム**", unsafe_allow_html=True)
        pwd = st.text_input("パスワード", type="password")
        if pwd:
            # パスワード確認 (secrets優先)
            correct_password = st.secrets.get("app_password", "eseikatsu2025")
            if pwd == correct_password:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        inject_custom_css()
    return False

def logout():
    st.session_state["password_correct"] = False
    st.rerun()

# --- メイン処理 ---
def main():
    if not check_password(): return

    inject_custom_css()
    
    with st.sidebar:
        st.markdown(f"### 🏢 {COMPANY_NAME}")
        if st.button("ログアウト", icon="🚪"): logout()
        st.markdown("---")

    st.title("いい生活 FAQ検索")
    st.markdown("質問したい内容を文章で入力すると、関連するマニュアルを探し出します。")

    with st.spinner("システムを起動中... (データの復号・展開)"):
        df, model, doc_embeddings = load_data_and_model()

    if df is None:
        st.error("データの準備ができませんでした。")
        return

    with st.sidebar:
        st.header("絞り込み")
        all_cats = df['カテゴリ'].dropna().apply(format_category_display).unique()
        roots = sorted(list(set([c.split(' > ')[0] for c in all_cats if c])))
        selected_root = st.selectbox("ツール選択", ["すべて"] + roots)

    query = st.text_input("質問を入力してください", placeholder="例: 画像を加工したい")

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
                    
                    # PDFボタン (展開済みフォルダから取得)
                    pdf_path = os.path.join(PDF_DIR, row['元ファイル名'])
                    
                    if os.path.exists(pdf_path):
                        with open(pdf_path, "rb") as f:
                            pdf_bytes = f.read()
                        st.download_button(
                            label="PDFを見る",
                            data=pdf_bytes,
                            file_name=row['元ファイル名'],
                            mime="application/pdf",
                            key=f"dl_{row['FAQ_ID']}"
                        )
                    else:
                        st.caption("PDFなし")
            
            st.markdown("---")
            hits += 1
            if hits >= 10: break
        
        if hits == 0:
            st.warning("関連するFAQが見つかりませんでした。")

if __name__ == "__main__":
    main()