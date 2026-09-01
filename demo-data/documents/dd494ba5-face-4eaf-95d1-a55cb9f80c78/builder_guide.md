# # Builder Guide

## 目的

指導使用者如何將 Assistant 設計的內容，正確實作到 GPTs Builder 中，
並透過 Builder 指令持續檢查、修訂與優化 GPT 行為。

---

## 核心原則

👉 Assistant 負責「設計」  
👉 GPT Builder 負責「實作」  
👉 使用者透過 Builder 指令「調教 GPT」  

---

## Builder 設定流程

### Step 1：建立 GPT

1. 打開 GPTs Builder  
2. 點擊「Create GPT」  
3. 進入配置畫面  

---

### Step 2：貼入 System Instructions

1. 複製 Assistant 生成的 System Instructions  
2. 貼入 Builder 的「Instructions」欄位  

---

### Step 3：設定 Starter Questions

1. 複製 Starter Questions  
2. 貼入 Builder 的「Conversation starters」  

---

### Step 4：上傳 Resources

若設計中包含資源：

1. 將 .md 或文件上傳至 Builder  
2. 確認內容完整且可讀  

---

### Step 5：功能設定（如需要）

依設計需求設定：

- Tools（如 Code Interpreter / Browser）  
- Actions（API 或外部服務）  
- 權限設定  

---

### Step 6：測試 GPT

1. 在 Builder 右側測試對話  
2. 使用 Assistant 提供的 Test Cards  
3. 觀察回應是否符合設計  

👉 可搭配下方 Builder 指令進行測試  

---

### Step 7：調整與優化

若發現問題：

1. 記錄問題情境  
2. 回到 Assistant  
3. 要求生成 Prompt Patch  
4. 更新 System Instructions  
5. 在 Builder 再次測試  

---

# 🔥 Builder 指令範例（按模組分類）

👉 用於「調整 GPT 行為」，不是建立 GPT  

---

## 🔹 1. 配置實現支持模組（Configuration）

👉 用於檢查與優化 System Instructions

### 指令範例

• 「檢查配置指令。你理解它嗎？」  
• 「告訴我如何修改配置，包括步驟、修改內容以及修改位置。」  
• 「配置指令是否容易遵循？是否需要調整？」  
• 「是否有容易實現的功能細化的建議？」  

---

👉 使用時機：

- GPT 行為不穩  
- 設定過於複雜  
- 想優化 Prompt  

---

## 🔹 2. 互動邏輯支持模組（Interaction Logic）

👉 用於調整 GPT 回答方式與流程

### 指令範例

• 「請用直接回答模式來處理所有事實性問題。」  
• 「請用 Socratic 問答模式：先提一個澄清性問題，再給部分解答。」  
• 「請將互動流程設定為：Step 1 問經文 → Step 2 引導反思 → Step 3 提供摘要 → Step 4 提醒應用。」  
• 「在摘要之前必須加入『經文重點』段落。」  

---

👉 使用時機：

- GPT 回答不符合設計  
- 流程混亂  
- 想優化互動體驗  

---

## 🔹 3. 測試與優化支持模組（Testing & Optimization）

👉 用於測試 GPT 是否符合預期

### 指令範例

• 「測試以下場景：使用者請求靈修摘要 → 是否依序給出反思、摘要與應用？」  
• 「請檢查 GPT 的回覆是否包含過多無關資訊？」  
• 「請模擬 3 種不同使用者（初學者、進階者、牧者）的提問，檢查回覆是否一致合理。」  

---

👉 使用時機：

- 上線前驗證  
- 發現品質問題  
- 想確認設計是否落實  

---

## 🔹 4. 風格與語氣探索模組（Style & Tone）

👉 用於調整語氣與風格

### 指令範例

• 「請用嚴謹專業的風格重寫這份設計聲明。」  
• 「請改用啟發式、激勵人心的語氣生成另一個版本。」  
• 「請同時給我兩種語氣：一個直接果斷，一個溫和鼓勵，讓我比較。」  

---

👉 使用時機：

- 語氣不符合預期  
- 想比較不同風格  
- 優化使用體驗  

---

# 🔥 使用技巧（關鍵）

## ✅ 一次只改一件事

❌ 一次改全部  
✅ 一次改一個行為  

---

## ✅ 使用具體指令

❌ 「讓它更好」  
✅ 「加入 Step-by-step 流程」  

---

## ✅ 改完一定測試

👉 每次修改後 → 立即測試  

---

## ✅ 搭配 Testing Guide

👉 測試問題 → 回來用 Builder 指令修正  

---

## 常見錯誤（避免）

❌ 忘記貼完整 System Instructions  
❌ Starter Questions 與設計不一致  
❌ 資源未上傳或內容不完整  
❌ 未測試就發布  

---

## 建議流程（最佳實務）

設計 → Builder 實作 → 測試 → Builder 指令調整 → 再測試  

---

## 一句總結

👉 Builder 是實作環境  
👉 Assistant 是設計引擎  
👉 Builder 指令是「調教 GPT 的工具」
