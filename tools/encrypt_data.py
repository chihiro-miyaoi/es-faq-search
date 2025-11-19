import os
import shutil
import zipfile
from cryptography.fernet import Fernet

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "faq_pdfs")
CSV_FILE = os.path.join(BASE_DIR, "faq_dataset.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "encrypted_data")
KEY_FILE = os.path.join(BASE_DIR, ".streamlit", "master.key")

# 分割サイズ (GitHub推奨は50MB以下)
CHUNK_SIZE = 50 * 1024 * 1024 

def main():
    print("="*60)
    print("【データ暗号化・分割ツール】")
    print("="*60)

    # 1. 出力フォルダ初期化
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    # 2. 鍵の生成（なければ作る）
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
        print("既存の暗号化キーを使用します。")
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        print("新しい暗号化キーを生成しました。")

    print(f"★重要★ このキーを secrets.toml に登録してください:\n{key.decode()}")
    print("-" * 60)

    # 3. データを一時的にZip化
    temp_zip = os.path.join(OUTPUT_DIR, "data.zip")
    print("データをZipに圧縮中...")
    with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        # CSVを追加
        z.write(CSV_FILE, arcname="faq_dataset.csv")
        # PDFを追加
        for root, _, files in os.walk(PDF_DIR):
            for file in files:
                if file.endswith(".pdf"):
                    z.write(os.path.join(root, file), arcname=f"faq_pdfs/{file}")

    # 4. Zipを暗号化
    print("Zipファイルを暗号化中...")
    f = Fernet(key)
    with open(temp_zip, "rb") as file:
        file_data = file.read()
    encrypted_data = f.encrypt(file_data)

    # 5. 分割して保存
    print(f"データを分割保存中 ({len(encrypted_data) / 1024 / 1024:.2f} MB)...")
    total_parts = 0
    for i in range(0, len(encrypted_data), CHUNK_SIZE):
        chunk = encrypted_data[i:i + CHUNK_SIZE]
        part_name = f"data.enc.{total_parts:03d}"
        with open(os.path.join(OUTPUT_DIR, part_name), "wb") as out:
            out.write(chunk)
        total_parts += 1
    
    # 一時ファイル削除
    os.remove(temp_zip)
    
    print(f"完了！ '{OUTPUT_DIR}' に {total_parts} 個のファイルを作成しました。")

if __name__ == "__main__":
    main()