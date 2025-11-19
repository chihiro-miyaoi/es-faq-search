import os
import sys
import json
import toml
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 設定 ---
# ルートディレクトリのパスを計算
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
PDF_DIR = os.path.join(BASE_DIR, "faq_pdfs")
CSV_FILE = os.path.join(BASE_DIR, "faq_dataset.csv")
TARGET_FOLDER_NAME = "FAQ_Data_Center" # ロボットのドライブに作るフォルダ名

def get_service():
    # secrets.toml から認証情報を読み込む
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            secrets = toml.load(f)
            creds_dict = secrets["gcp_service_account"]
            creds = Credentials.from_service_account_info(creds_dict)
            return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"エラー: secrets.toml の読み込みに失敗しました。\n{e}")
        sys.exit(1)

def create_folder(service, name):
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = service.files().create(body=file_metadata, fields='id').execute()
    return file.get('id')

def upload_file(service, filepath, folder_id):
    filename = os.path.basename(filepath)
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaFileUpload(filepath, resumable=True)
    
    print(f"アップロード中: {filename} ...", end=" ")
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print("OK")

def main():
    print("="*60)
    print("【データ移行ツール】")
    print("ローカルのデータを、Service Account自身のGoogleドライブへ転送します。")
    print("="*60)

    if not os.path.exists(PDF_DIR) or not os.path.exists(CSV_FILE):
        print("エラー: データフォルダまたはCSVが見つかりません。")
        return

    service = get_service()

    # 1. フォルダ作成
    print(f"ロボットのドライブにフォルダ '{TARGET_FOLDER_NAME}' を作成中...")
    folder_id = create_folder(service, TARGET_FOLDER_NAME)
    print(f"フォルダ作成完了 ID: {folder_id}")
    print("-" * 60)
    print(f"★重要★ このIDを secrets.toml の 'drive_folder_id' に書き写してください！")
    print("-" * 60)

    # 2. CSVアップロード
    upload_file(service, CSV_FILE, folder_id)

    # 3. PDFアップロード
    files = os.listdir(PDF_DIR)
    pdf_files = [f for f in files if f.endswith(".pdf")]
    print(f"\nPDFファイル {len(pdf_files)} 件をアップロードします...")

    for i, filename in enumerate(pdf_files):
        filepath = os.path.join(PDF_DIR, filename)
        try:
            upload_file(service, filepath, folder_id)
        except Exception as e:
            print(f"\nエラー ({filename}): {e}")

    print("\n全ての処理が完了しました！")

if __name__ == "__main__":
    main()