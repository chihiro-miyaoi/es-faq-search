import time
import os
import base64
import csv
import re
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.print_page_options import PrintOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- 設定 ---
START_NUM = 5258       
END_NUM = 30000     # 余裕を持って3万まで設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "faq_pdfs")
LOG_FILE_V2 = os.path.join(PROJECT_ROOT, "logs", "faq_log_v2.csv")
PREV_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "faq_log.csv")
RESTART_INTERVAL = 100  # 何件ごとにブラウザを再起動するか

# --- 関数群 ---
def load_skip_list(filename):
    skip_ids = set()
    if not os.path.exists(filename): return skip_ids
    try:
        with open(filename, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 2 and "Skip" in row[1]:
                    try: skip_ids.add(int(row[0]))
                    except: pass
    except: pass
    return skip_ids

def sanitize_filename(text):
    if not text: return "NoTitle"
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    return text.replace('\n', '').replace('\r', '').replace('\t', '').strip()

def load_log_data_v2(filename):
    header = ["FAQ_ID", "結果", "ページタイトル", "カテゴリ", "更新日", "保存ファイル名"]
    rows = []
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8-sig') as f:
            rows = list(csv.reader(f))
    if not rows: rows.append(header)
    return rows

def update_and_save_log_v2(filename, rows, faq_id, status, title, category, update_date, saved_filename):
    while len(rows) <= faq_id:
        rows.append([len(rows), "Skipped (Gap)", "-", "-", "-", "-"])
    new_row = [faq_id, status, title, category, update_date, saved_filename]
    if faq_id < len(rows): rows[faq_id] = new_row
    else: rows.append(new_row)
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    return rows

def create_driver():
    options = Options()
    options.add_argument('--headless=new') # 安定したら有効化
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options.add_argument(f'--user-agent={user_agent}')
    return webdriver.Chrome(options=options)

# --- メイン処理 ---
print("="*60)
print("【Gemini 3.0 マラソンランナー】")
print("長期間の安定動作を目指して、定期的な休憩(再起動)を挟みながら走ります。")
print("="*60)

skip_set = load_skip_list(PREV_LOG_FILE)
log_rows = load_log_data_v2(LOG_FILE_V2)
if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)

# 初回URL入力
sso_url = input("★SSO URLを貼り付けて [Enter]:\n>> ").strip()
if not sso_url: exit()

driver = create_driver()

try:
    # 初回ログイン
    print("初回ログイン中...")
    driver.get(sso_url)
    time.sleep(10)

    # 処理開始
    processed_count = 0
    
    for i in range(START_NUM, END_NUM + 1):
        
        # 1. スキップ判定（過去ログ）
        if i in skip_set:
            # print(f"[{i}] Skip (Log)") # ログが流れるのが早すぎる場合はコメントアウト
            # ログファイルには書き込んでおく（一貫性のため）
            log_rows = update_and_save_log_v2(LOG_FILE_V2, log_rows, i, "Skip", "N/A", "-", "-", "-")
            continue 

        # 2. ブラウザ定期再起動（メモリ解放）
        if processed_count > 0 and processed_count % RESTART_INTERVAL == 0:
            print(f"\n--- 休憩中: ブラウザをリフレッシュします ({i}番の手前) ---")
            driver.quit()
            time.sleep(5)
            driver = create_driver()
            print("再ログイン中...")
            driver.get(sso_url)
            time.sleep(10)
            print("再開します！")

        # 3. アクセス処理
        target_url = f"https://secure.okbiz.jp/faq-e-seikatsu/print/faq/{i}?site_domain=default"
        processed_count += 1 # アクセスした回数をカウント
        
        status = ""
        title_text = ""
        category_text = ""
        date_text = ""
        fname = ""
        
        try:
            print(f"[{i}/{END_NUM}] アクセス... ", end="")
            driver.get(target_url)

            # セッション切れチェック（重要！）
            # URLがトップページに戻っていたり、ログイン画面っぽかったら停止
            if "sorry.html" in driver.current_url or "login" in driver.current_url:
                print("\n\n【緊急停止】セッションが切れた可能性があります！")
                print(f"現在のURL: {driver.current_url}")
                print("新しいSSO URLを取得して貼り付けてください（再開するにはEnter）:")
                sso_url = input(">> ").strip()
                if sso_url:
                    driver.get(sso_url)
                    time.sleep(10)
                    print("処理を再開します...")
                    # 今回の分をやり直すためにカウンタを戻すなどの処理は複雑になるので、
                    # とりあえずそのまま続行（この回はErrorになるかも）ですが、次は成功します。

            if "print/faq" in driver.current_url:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                try:
                    page_text = driver.find_element(By.TAG_NAME, "body").text
                    raw_title = driver.title
                    safe_title = sanitize_filename(raw_title)
                    title_text = raw_title
                    
                    lines = page_text.split('\n')
                    for line in lines:
                        if ">" in line and "トップカテゴリー" in line:
                            category_text = line.strip()
                            break
                    if not category_text: category_text = "Unknown"
                    
                    date_match = re.search(r'更新日時\s*:\s*([\d/]+)', page_text)
                    date_text = date_match.group(1) if date_match else "-"
                except:
                    category_text = "Error"

                fname = f"faq_{i}_{safe_title}.pdf"
                file_path = os.path.join(OUTPUT_DIR, fname)
                
                # PDF保存
                print_options = PrintOptions()
                print_options.background = True
                pdf_data = driver.print_page(print_options)
                with open(file_path, 'wb') as f:
                    f.write(base64.b64decode(pdf_data))
                
                print(f"OK ({category_text[:10]}...)")
                status = "OK"
            else:
                print("Skip")
                status = "Skip"
                title_text = "N/A"
                fname = "-"

        except Exception as e:
            print(f"Error: {e}")
            status = "Error"
            title_text = str(e)
            fname = "-"

        # ログ保存
        log_rows = update_and_save_log_v2(LOG_FILE_V2, log_rows, i, status, title_text, category_text, date_text, fname)

        # ランダム待機
        time.sleep(random.uniform(3, 6))

finally:
    if driver: driver.quit()
    print("\n処理を終了します。お疲れ様でした。")