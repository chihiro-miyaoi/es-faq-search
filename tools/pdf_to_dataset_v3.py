import os
import re
import csv
import pdfplumber

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
INPUT_PDF_DIR = os.path.join(PROJECT_ROOT, "faq_pdfs")    # PDFが入っているフォルダ
INPUT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "faq_log_v2.csv")    # メタデータが入っているCSV
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "faq_dataset.csv")    # 成果物

# --- テキスト整形関数 ---
def clean_text_body(text, title_to_remove):
    if not text:
        return ""
    
    # 1. 表記の正規化
    text = text.replace("︓", ":").replace("？", "?")
    
    # 2. 日本語間の謎スペース除去
    pattern_gap = r'(?<=[ぁ-んァ-ン一-龥])\s+(?=[ぁ-んァ-ン一-龥])'
    text = re.sub(pattern_gap, '', text)
    
    # 3. 「回答」による分割
    if "回答" in text:
        parts = text.split("回答", 1)
        if len(parts[1].strip()) > 0:
            text = parts[1]
    
    # 4. 行ごとのノイズ除去
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # パンくずリストやメタデータの残骸を除去
        if ">" in line or line.startswith("カテゴリー") or "戻る No" in line:
            continue
            
        # フッター検知
        if "株式会社いい⽣活" in line and "サポートセンター" in line:
            break 
            
        cleaned_lines.append(line)
    
    text = "".join(cleaned_lines)

    # 5. タイトル重複削除
    # ここで渡される title_to_remove は、カテゴリから抽出した「完全なタイトル」になっているはずなので、
    # クリーニングの精度も向上します。
    if title_to_remove:
        # タイトルに含まれる記号やスペースも正規化してからマッチング
        clean_title_pattern = re.sub(pattern_gap, '', title_to_remove.strip())
        
        # 文頭にタイトルがあれば削除
        if text.startswith(clean_title_pattern):
            text = text[len(clean_title_pattern):].strip()

    return text

def main():
    # 1. メタデータの読み込み
    print(f"メタデータ '{INPUT_LOG_FILE}' を読み込んでいます...")
    metadata = {}
    
    try:
        with open(INPUT_LOG_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('FAQ_ID'): continue
                
                faq_id = int(row['FAQ_ID'])
                raw_title = row.get('ページタイトル', '')
                category_full = row.get('カテゴリ', '')
                date_text = row.get('更新日', '-')

                # ★ここに改良ロジックを適用★
                # カテゴリ（パンくずリスト）の一番右側を取得してタイトルとする
                final_title = raw_title # デフォルトは元のタイトル
                
                if category_full and " > " in category_full:
                    # " > " で分割して最後の要素を取得
                    extracted_title = category_full.split(" > ")[-1].strip()
                    
                    # 抽出できた場合、こちらを採用（ただし短すぎる場合は警戒）
                    if len(extracted_title) > 1:
                        final_title = extracted_title
                
                # 念のためサイト名の削除（カテゴリ抽出に失敗した場合の保険）
                final_title = final_title.replace(" | いい生活サポートサイト", "").strip()

                metadata[faq_id] = {
                    'title': final_title,
                    'category': category_full,
                    'date': date_text
                }
                
    except Exception as e:
        print(f"警告: ログファイル読み込みエラー ({e})")
        print("メタデータなしで処理を続行します。")

    # 2. PDF処理
    data_rows = []
    
    if not os.path.exists(INPUT_PDF_DIR):
        print(f"エラー: フォルダ '{INPUT_PDF_DIR}' が見つかりません。")
        return

    files = os.listdir(INPUT_PDF_DIR)
    pdf_files = [f for f in files if f.endswith(".pdf")]
    pdf_files.sort(key=lambda x: int(re.search(r'faq_(\d+)_', x).group(1)) if re.search(r'faq_(\d+)_', x) else 0)

    print(f"全 {len(pdf_files)} 件のPDFを処理します...")
    print("-" * 50)

    success_count = 0
    
    for filename in pdf_files:
        match = re.match(r'faq_(\d+)_(.+)\.pdf', filename)
        if not match: continue
            
        faq_id = int(match.group(1))
        
        # メタデータ取得
        info = metadata.get(faq_id)
        
        if info:
            final_title = info['title']
            final_category = info['category']
            final_date = info['date']
        else:
            # ログにない場合
            final_title = match.group(2)
            final_category = "Unknown"
            final_date = "-"

        # PDF本文抽出
        full_text = ""
        try:
            file_path = os.path.join(INPUT_PDF_DIR, filename)
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        full_text += extracted + "\n"
            
            # クレンジング実行
            final_body = clean_text_body(full_text, final_title)
            
            data_rows.append([faq_id, final_title, final_category, final_date, final_body, filename])
            success_count += 1
            
            if success_count % 100 == 0:
                print(f"... {success_count} 件 完了")

        except Exception as e:
            print(f"スキップ: {filename} ({e})")

    # 3. CSV保存
    print("-" * 50)
    print(f"処理完了。データセット '{OUTPUT_FILE}' を作成しています...")
    
    header = ["FAQ_ID", "タイトル", "カテゴリ", "更新日", "本文(Content)", "元ファイル名"]
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)

    print(f"完了！")
    print(f"処理件数: {success_count} 件")
    print(f"出力先: {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    main()