# Modular Design Guide（模組化設計指南）

## 目的

本指南提供一套系統化方法，協助將 GPT System Instructions 從「單一長 Prompt」升級為「模組化架構」。

目標：

- 提升可讀性
- 提升可維護性
- 支援擴展與重用
- 降低 Token 壓力
- 提升 GPT 設計品質與穩定性

---

# 一、核心觀念（Core Concept）

## GPT ≠ Prompt

GPT 應用本質是一個「系統」，而不是一段長文字。

---

## 模組化設計的本質

👉 模組不是預先定義的清單  
👉 模組是從「任務分解」推導出來的結果  

---

## 核心公式

👉 模組 = 任務的結構化表達  
👉 流程 = 任務的執行順序  

---

# 二、三層架構（Three-Layer Architecture）

## 1. Core Instructions（核心指令層）

用途：
定義 GPT 的控制邏輯與基本行為。

---

包含：

- 角色與目標  
- 任務範圍  
- 互動總則  
- 模組啟動規則  
- 安全與限制  

---

## 流程設計原則（重要）

❗ GPT 的流程不應預先固定  

👉 流程應由「任務」與「應用場景」決定  

---

不同 GPT 可有不同流程，例如：

- 教學型 GPT：講解 → 練習 → 回饋  
- 分析型 GPT：輸入解析 → 推理 → 結論  
- 工具型 GPT：輸入 → 處理 → 輸出  

---

👉 流程屬於 Instruction Modules  
👉 不應寫死在 Core Instructions 中  

---

## 2. Instruction Modules（指令模組層）

用途：
封裝 GPT 的「行為邏輯單元」

---

## 模組的本質

👉 Instruction Module = 可執行的行為單元  

---

## 模組不是固定清單

❗ 模組由需求推導  
❗ 模組由任務分解產生  

---

## 常見模組類型（分類，而非清單）

- 輸入理解模組  
- 任務執行模組  
- 互動控制模組  
- 輸出生成模組  
- 優化與驗證模組  

---

👉 模組名稱與內容應依應用設計  

---

## 3. Knowledge Modules（知識模組層）

用途：
承載長內容與可重用知識  

---

適合內容：

- 方法論  
- 教學內容  
- 範例集合  
- 模板  
- 專業知識  

---

形式：

- 外部 .md 文件  
- Resource 引用  

---

# 三、流程生成方法（Process Derivation Method）

## Step 1：定義任務（Task Definition）

例：
「幫助使用者學習一項技能」

---

## Step 2：任務拆分（Task Decomposition）

將任務拆成步驟：

- 理解內容  
- 練習  
- 應用  
- 回饋  

---

## Step 3：流程生成（Process Construction）

將步驟串成流程：

👉 理解 → 練習 → 應用 → 回饋  

---

## 核心原則

👉 流程 = 任務的執行順序  

---

# 四、模組生成方法（Module Derivation Method）

## Step 1：定義任務

---

## Step 2：拆解子任務

---

## Step 3：映射為模組

例：

任務：
寫作教學  

子任務：

- 分析文章  
- 提供建議  
- 修改內容  

模組：

- 分析模組  
- 建議模組  
- 修改模組  

---

## 核心原則

👉 模組 = 任務分解結果  

---

# 五、模組化判斷原則

## 保留在 Core Instructions

- 行為規則  
- 決策邏輯  
- 模組觸發條件  
- 安全限制  

---

## 拆成 Instruction Modules

當內容：

- 有明確功能  
- 可獨立理解  
- 可重用  

---

## 外移為 Knowledge Modules

當內容：

- 超過 300–500 字  
- 為教學或說明  
- 可跨 GPT 使用  

---

# 六、模組化策略（Refactoring Strategies）

- 拆分（Split）  
- 合併（Merge）  
- 外移（Externalize）  
- 分層（Layering）  

---

# 七、模組化觸發條件

當出現：

- System Instructions 過長  
- 邏輯重複  
- 功能混雜  
- 難以維護  
- Token 壓力過高  

👉 應進行模組化  

---

# 八、常見錯誤（Anti-Patterns）

❌ 預設模組清單  
❌ 固定流程框架  
❌ 複製其他 GPT 模組  
❌ 行為與知識混雜  
❌ 過度集中  

---

# 九、設計黃金法則

👉 先定義需求，再設計流程  
👉 先定義任務，再生成模組  
👉 行為與知識分離  

---

# 十、架構示意

Core Instructions
├── 角色與目標
├── 行為與限制
├── 模組觸發規則
│
├── Instruction Modules（動態生成）
│
└── Resources
    ├── Modular Design Guide.md
    ├── Prompt Refactoring Patterns.md

---

# 結論

GPT 設計的關鍵不是寫更多內容，而是建立清晰的結構。

👉 從 Prompt  
👉 到 Architecture  

這是 GPT 應用成熟的核心轉變。
