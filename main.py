"""
台灣股市自結公告 AI 分析器
每日自動抓取上市/上櫃自結公告，透過 Gemini 分析後傳送至 Telegram 與 Gmail。
"""

import os
import re
import smtplib
import requests
import google.generativeai as genai
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 設定 ──────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
GMAIL_USER         = os.environ["GMAIL_USER"]          # 寄件人 Gmail
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]  # Gmail 應用程式密碼
GMAIL_TO           = os.environ["GMAIL_TO"]            # 收件人信箱

# 自結關鍵字（主旨 + 說明 含其一即算命中）
KEYWORDS = [
    "臺灣證券交易所股份有限公司通知辦理",
    "財團法人中華民國證券櫃檯買賣中心通知辦理",
]

SYSTEM_PROMPT = """你是一位專業的台灣股票分析師。請根據以下公告內容，提供簡潔明瞭、具邏輯與可驗證的投資評分報告。

【輸出格式（務必遵守）】
請「只輸出」一個 HTML 區塊（不要使用 Markdown、不要使用```）。請用 <table> 產生表格，並含 <thead> 與 <tbody>。
表格欄位依序為：公司名稱、公司代號、評分等級、關鍵財數、評分理由、風險提醒、資料來源(附註上市或是上櫃)、驗證依據。

請務必使用純 HTML，並加上簡單的 inline style，範例如下（請照此結構輸出）：
<table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:14px;">
  <thead>
    <tr>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">公司名稱</th>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">公司代號</th>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">評分等級</th>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">關鍵財數</th>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">評分理由</th>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">風險提醒</th>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">資料來源</th>
      <th style="border:1px solid #ddd;background:#f6f7f8;padding:8px;">驗證依據</th>
    </tr>
  </thead>
  <tbody>
    <!-- 每家公司一列 -->
  </tbody>
</table>

表格後面請附上兩段 <p>：
1) <p><b>整體市場觀察：</b>…（不超過 4 行）</p>
2) <p><i>投資風險聲明：本分析僅供參考，並非投資建議。股票投資具風險，請審慎評估自身風險承受能力。</i></p>

【評分機制】
- 🔴 營收大漲：營收大幅成長且獲利顯著改善、虧轉盈或 EPS 大幅提升
- 🟠 獲利良好：營收穩定成長、獲利表現良好或持續改善
- 🟡 表現一般：營收與獲利平穩，無明顯利多或利空
- 🟢 需要小心：營收下滑、獲利惡化、盈轉虧或財務警訊

【評分標準】
- 營收年增率 > 20% 且獲利改善 → 🔴 或 🟠
- 虧轉盈且營收成長 → 🔴
- 營收成長但獲利下滑 → 🟡
- 營收下滑且盈轉虧 → 🟢
- EPS 衰退超過 50% → 🟢

【重要規則】
1. 括弧內數字代表負數，如 (0.01) = -0.01。
2. 若公告有提到月營收或月獲利情形，請以「月營收與月獲利」為主要依據，其次為季營收與季獲利。
3. 分析內容應以公告中明確數據為依據，不得主觀推測。
4. 評語須簡潔、專業、不冗長。
"""


# ── 1. 抓取公告 ───────────────────────────────────────────────────────────────

def fetch_announcements() -> list[dict]:
    """抓取上市 + 上櫃重大公告並合併。"""
    urls = {
        "上市": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
        "上櫃": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O",
    }
    all_items = []
    for market, url in urls.items():
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data:
                item["__market__"] = market
            all_items.extend(data)
            print(f"[fetch] {market}: {len(data)} 筆")
        except Exception as e:
            print(f"[fetch] {market} 失敗: {e}")
    return all_items


# ── 2. 過濾自結公告 ────────────────────────────────────────────────────────────

def extract_company_name(text: str) -> str:
    m = re.search(r"公司名稱[:：]\s*([^\n\r]+)", text)
    return m.group(1).strip() if m else ""


def filter_self_reports(items: list[dict]) -> list[dict]:
    """只保留含自結關鍵字的公告。"""
    results = []
    for item in items:
        subject = item.get("主旨") or item.get("Subject") or ""
        content = item.get("說明") or item.get("Content") or ""
        combined = f"{subject} {content}"

        matched = next((kw for kw in KEYWORDS if kw in combined), None)
        if not matched:
            continue

        date = (
            item.get("Date") or item.get("發言日期") or item.get("事實發生日") or ""
        )
        results.append({
            "公司代號":   item.get("SecuritiesCompanyCode") or item.get("公司代號") or "",
            "公司名稱":   item.get("CompanyName") or item.get("公司名稱") or extract_company_name(content),
            "出表日期":   date,
            "主旨":       subject.strip(),
            "說明":       content.strip(),
            "類型":       matched,
            "市場":       item.get("__market__", ""),
        })

    print(f"[filter] 命中自結公告: {len(results)} 筆")
    return results


# ── 3. 組出 AI 輸入文本 ────────────────────────────────────────────────────────

def build_ai_input(reports: list[dict]) -> str:
    parts = []
    for i, r in enumerate(reports, 1):
        desc = (r["說明"] or "")[:1000]
        if len(r["說明"]) > 1000:
            desc += "..."
        code = r["公司代號"]
        link = (
            f"https://mopsov.twse.com.tw/mops/web/ezsearch?keyword4={code}"
            if code else ""
        )
        parts.append(
            f"【第 {i} 家】\n"
            f"公司代號：{code}\n"
            f"公司名稱：{r['公司名稱']}\n"
            f"出表日期：{r['出表日期']}\n"
            f"市場：{r['市場']}\n"
            f"類型：{r['類型']}\n"
            f"主旨：{r['主旨']}\n"
            f"說明：{desc}\n"
            f"🔗 公告連結：{link}\n"
            "-----------------------------"
        )
    return "\n\n".join(parts)


# ── 4. 呼叫 Gemini ─────────────────────────────────────────────────────────────

def analyze_with_gemini(ai_input: str) -> str:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name="models/gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    response = model.generate_content(
        "請分析下列公告資料，並依上述規則與格式產出簡潔、明確、具驗證依據的分析報告：\n\n"
        + ai_input
    )
    return response.text


# ── 5. 傳送 Telegram ───────────────────────────────────────────────────────────

def send_telegram(text: str, date_str: str) -> None:
    """Telegram 只支援純文字，移除 HTML 標籤後傳送。"""
    plain = re.sub(r"<[^>]+>", "", text)
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    msg = f"{date_str} - AI 上市、櫃自結分析報告\n\n{plain}"

    # Telegram 訊息上限 4096 字，超過切割
    max_len = 4000
    chunks = [msg[i : i + max_len] for i in range(0, len(msg), max_len)]

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in chunks:
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
            timeout=30,
        )
        if not resp.ok:
            print(f"[telegram] 傳送失敗: {resp.text}")
        else:
            print("[telegram] 傳送成功")


# ── 6. 傳送 Gmail ──────────────────────────────────────────────────────────────

def send_gmail(html_content: str, date_str: str) -> None:
    subject = f"{date_str} - AI 上市、櫃自結分析報告"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_TO
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, GMAIL_TO, msg.as_string())
    print("[gmail] 傳送成功")


# ── 主程式 ─────────────────────────────────────────────────────────────────────

def main():
    date_str = datetime.now().strftime("%Y/%m/%d")
    print(f"[start] {date_str}")

    raw = fetch_announcements()
    reports = filter_self_reports(raw)

    if not reports:
        no_data_msg = "<p>今天沒有自結相關公告。</p>"
        send_telegram("今天沒有自結相關公告。", date_str)
        send_gmail(no_data_msg, date_str)
        print("[done] 無自結公告，已發送通知。")
        return

    ai_input = build_ai_input(reports)
    print(f"[claude] 送出 {len(reports)} 筆，輸入長度 {len(ai_input)} 字元")

    result_html = analyze_with_gemini(ai_input)
    print("[claude] 分析完成")

    send_telegram(result_html, date_str)
    send_gmail(result_html, date_str)
    print("[done] 全部完成。")


if __name__ == "__main__":
    main()
