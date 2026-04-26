# 台灣股市自結公告 AI 分析器

每日自動抓取上市 / 上櫃自結公告，透過 **Gemini 2.5 Flash** 分析後發送至 **Telegram**。

---

## 功能

- 每天 07:30（台灣時間）自動執行
- 同時抓取 TWSE（上市）與 TPEX（上櫃）重大公告
- 過濾出含「自結」關鍵字的公告
- 呼叫 Gemini 2.5 Flash API 產出 HTML 格式投資評分報告
- 透過 Telegram Bot 發送報告

---

## 部署步驟

### 1. Fork / Clone 此 Repo 到你的 GitHub

```bash
git clone <your-repo-url>
```

### 2. 設定 GitHub Secrets

前往 **Settings → Secrets and variables → Actions → New repository secret**，新增以下 6 個 Secret：

| Secret 名稱 | 說明 |
|---|---|
| `GEMINI_API_KEY` | Gemini API 金鑰（從 [aistudio.google.com/apikey](https://aistudio.google.com/apikey) 免費取得） |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（向 @BotFather 申請） |
| `TELEGRAM_CHAT_ID` | 你的 Telegram Chat ID（向 @userinfobot 查詢） |

#### Gmail 應用程式密碼申請方式
1. 前往 Google 帳戶 → 安全性 → 兩步驟驗證（先開啟）
2. 搜尋「應用程式密碼」→ 選「郵件」→「Windows 電腦」→ 產生
3. 複製 16 碼密碼填入 `GMAIL_APP_PASSWORD`

### 3. 啟用 GitHub Actions

推送後到 **Actions** 頁籤確認 workflow 已啟用（若顯示停用，點擊「Enable workflow」）。

### 4. 手動測試

Actions → **每日自結公告分析** → **Run workflow** 即可立即觸發。

---

## 本地執行（測試）

```bash
pip install -r requirements.txt

export GEMINI_API_KEY="AIza..."
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."

python main.py
```

---

## 檔案結構

```
.
├── main.py                          # 主程式
├── requirements.txt                 # Python 套件
└── .github/
    └── workflows/
        └── daily_report.yml         # GitHub Actions 排程設定
```

---

## 修改排程時間

編輯 `.github/workflows/daily_report.yml` 中的 `cron` 欄位（UTC 時間）：

| 台灣時間 | UTC cron |
|---|---|
| 07:30 | `30 23 * * *`（前一天） |
| 08:00 | `0 0 * * *` |
| 09:00 | `0 1 * * *` |
