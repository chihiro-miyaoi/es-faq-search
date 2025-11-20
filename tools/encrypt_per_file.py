import os
import shutil
from cryptography.fernet import Fernet

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "faq_pdfs")
CSV_FILE = os.path.join(BASE_DIR, "faq_dataset.csv")
# 出力先を変えます
OUTPUT_DIR = os.path.join(BASE_DIR, "encrypted_assets") 
KEY_FILE = os.path.join(BASE_DIR, ".streamlit", "master.key")

def main():
    print("="*60)
    print("【個別暗号化ツール】")
    print("ファイルを1つずつ暗号化して保存します（メモリ節約版）")
    print("="*60)

    # 1. 出力フォルダ初期化
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    os.makedirs(os.path.join(OUTPUT_DIR, "pdfs")) # PDF用のサブフォルダ

    # 2. 鍵の読み込み
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    else:
        print("エラー: master.key が見つかりません。")
        return
    
    f = Fernet(key)

    # 3. CSVの暗号化
    print("CSVを暗号化中...", end=" ")
    with open(CSV_FILE, "rb") as file:
        file_data = file.read()
    encrypted_csv = f.encrypt(file_data)
    
    with open(os.path.join(OUTPUT_DIR, "faq_dataset.csv.enc"), "wb") as file:
        file.write(encrypted_csv)
    print("OK")

    # 4. PDFの個別暗号化
    files = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")]
    print(f"PDF {len(files)} 件を暗号化中...")

    for i, filename in enumerate(files):
        src_path = os.path.join(PDF_DIR, filename)
        # 出力ファイル名: オリジナル名 + .enc
        dst_path = os.path.join(OUTPUT_DIR, "pdfs", filename + ".enc")
        
        with open(src_path, "rb") as file:
            pdf_data = file.read()
        
        encrypted_pdf = f.encrypt(pdf_data)
        
        with open(dst_path, "wb") as file:
            file.write(encrypted_pdf)
            
        if i % 100 == 0:
            print(f".", end="", flush=True)

    print(f"\n完了！ '{OUTPUT_DIR}' に保存しました。")

if __name__ == "__main__":
    main()