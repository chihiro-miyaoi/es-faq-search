import streamlit as st
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import os
import io
import datetime
# --- 暗号化対応 ---
from cryptography.fernet import Fernet
# --- ログ用 ---
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
MODEL_NAME = "intfloat/multilingual-e5-small"
COMPANY_NAME = "生和不動産株式会社"
ENCRYPTED_DIR = "encrypted_assets" # 新しいフォルダ名（個別暗号化用）

# --- ページ設定 ---
st.set_page_config(
    page_title="いい生活 FAQ検索",
    page_icon="🔍",
    # layout="wide"
)

# --- 認証情報の取得ヘルパー ---
def get_gcp_creds():
    if "gcp_service_account" in st.secrets:
        return dict(st.secrets["gcp_service_account"])
    return None

# --- 復号ヘルパー関数 ---
def get_fernet():
    if "decryption_key" not in st.secrets:
        st.error("復号キーが設定されていません。")
        return None
    return Fernet(st.secrets["decryption_key"])

def decrypt_file_to_bytes(filepath):
    """暗号化ファイルを読み込んで復号し、バイト列として返す"""
    if not os.path.exists(filepath):
        return None
    try:
        f = get_fernet()
        if f is None: return None
        
        with open(filepath, "rb") as file:
            encrypted_data = file.read()
        return f.decrypt(encrypted_data)
    except Exception as e:
        # 復号エラーはログに出すが、アプリは止めない
        print(f"復号エラー ({filepath}): {e}")
        return None

# --- データロード (CSVのみ復号) ---
@st.cache_resource
def load_data_and_model():
    # 1. CSVの復号
    # 個別暗号化されたCSVを探す
    csv_enc_path = os.path.join(ENCRYPTED_DIR, "faq_dataset.csv.enc")
    
    if not os.path.exists(csv_enc_path):
        st.error(f"データファイルが見つかりません: {csv_enc_path}")
        return None, None, None
        
    csv_bytes = decrypt_file_to_bytes(csv_enc_path)
    if csv_bytes is None:
        st.error("CSVの復号に失敗しました。キーが正しいか確認してください。")
        return None, None, None

    # メモリ上のバイト列からDataFrameを作成
    try:
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding='utf-8-sig')
    except Exception as e:
        st.error(f"CSV読み込みエラー: {e}")
        return None, None, None
    
    # 2. 検索テキスト作成
    df['search_text'] = (
        df['カテゴリ'].fillna('') + " " + 
        df['タイトル'].fillna('') + " " + 
        df['タイトル'].fillna('') + " " + 
        df['本文(Content)'].fillna('')
    )
    
    # 3. AIモデルロード & ベクトル化
    # 起動時にメモリ上で計算（ファイルキャッシュは使わない）
    model = SentenceTransformer(MODEL_NAME)
    docs = df['search_text'].tolist()
    doc_embeddings = model.encode(["passage: " + str(doc) for doc in docs], show_progress_bar=True)
    
    return df, model, doc_embeddings

# --- PDF取得 (オンデマンド復号) ---
def get_pdf_data(original_filename):
    """ボタンが押された時に、そのPDFだけを復号して返す"""
    # 暗号化ファイル名 = 元ファイル名 + .enc
    # encrypted_assets/pdfs/xxxx.pdf.enc を探す
    enc_path = os.path.join(ENCRYPTED_DIR, "pdfs", original_filename + ".enc")
    return decrypt_file_to_bytes(enc_path)

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
        pass # ログ保存エラーは無視

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
    <div class="footer">© {COMPANY_NAME}</div>
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
        st.markdown(f"### ■ {COMPANY_NAME}")
        if st.button("ログアウト"): logout()
        st.markdown("---")

    st.title("いい生活 FAQ検索")
    st.markdown("質問したい内容を文章で入力すると、関連するマニュアルを探し出します。")

    # データロード (起動時のみ実行)
    with st.spinner("システムを起動中... (軽量モード)"):
        df, model, doc_embeddings = load_data_and_model()

    if df is None:
        return # エラーメッセージはload_data内で表示済み

    with st.sidebar:
        st.header("絞り込み")
        all_cats = df['カテゴリ'].dropna().apply(format_category_display).unique()
        roots = sorted(list(set([c.split(' > ')[0] for c in all_cats if c])))
        selected_root = st.selectbox("ツール選択", ["すべて"] + roots)

    query = st.text_input("質問を入力してください", placeholder="例: 新しく賃貸借契約を登録したい。")

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
                    
                    # ★ここがポイント：ボタンを押した瞬間だけ復号する
                    # keyにIDを含めることで、ボタンを個別に識別
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
                                st.error("ファイルが見つかりません")
            
            st.markdown("---")
            hits += 1
            if hits >= 10: break
        
        if hits == 0:
            st.warning("関連するFAQが見つかりませんでした。")

if __name__ == "__main__":
    main()