# Optimization Strategy Library v1

---

## Purpose

本模組提供一套結構化的 Prompt 優化策略（Strategy Library），
支援 Optimization Module 在優化過程中：

- 系統性分析問題
- 提供高品質優化建議
- 避免隨機或表面優化
- 提升 Prompt 的穩定性與可重用性

👉 核心理念：
「優化不是修改文字，而是套用策略」

---

## Key Concepts

- Strategy-driven Optimization（策略驅動優化）
- Dual-layer Optimization（工程層 + 事工層）
- Selectable Improvements（可選優化）
- Problem → Strategy → Action Mapping（問題對應策略）

---

## Structured Content

---

### 1. Strategy Pools（策略池）

---

#### 🔹 1.1 Structure Optimization（結構優化）

**目的：提升 Prompt 清晰度與可讀性**

- STR-01 五區塊補全  
  → 補齊缺失區塊（角色 / 用途 / 基本資料 / 輸出要求 / 語氣）

- STR-02 結構重組  
  → 將混亂段落轉為清晰區塊

- STR-03 Step-by-Step 強化  
  → 將模糊指令轉為步驟流程

- STR-04 單一任務聚焦  
  → 移除多任務，保留單一核心目標

---

#### 🔹 1.2 Tone Optimization（語氣優化）

**目的：讓 Prompt 符合受眾與情境**

- TONE-01 受眾對齊  
  → 青年：激勵 / 親切  
  → 領袖：教練式 / 啟發  
  → 關懷：溫柔 / 同理  

- TONE-02 語氣一致化  
  → 避免混合語氣（如嚴肅 + 輕鬆）

- TONE-03 牧養語氣強化  
  → 加入關懷、引導與鼓勵語句

---

#### 🔹 1.3 Depth Optimization（深度優化）

**目的：提升內容屬靈深度與洞察力**

- DEPTH-01 屬靈洞察強化  
  → 加入神學或經文層次

- DEPTH-02 應用導向  
  → 將內容連結實際生活

- DEPTH-03 反思問題設計  
  → 加入引導式問題

- DEPTH-04 多層次輸出  
  → 解釋 → 洞察 → 行動

---

#### 🔹 1.4 Execution Optimization（可執行性）

**目的：確保 Prompt 可被模型準確執行**

- EXEC-01 明確輸出格式  
  → 指定輸出結構（條列 / 步驟）

- EXEC-02 降低模糊性  
  → 替換模糊詞（如「適當」「詳細」）

- EXEC-03 Few-shot 範例  
  → 提供輸出示範

- EXEC-04 條件邏輯  
  → 加入 IF / THEN（進階）

---

#### 🔹 1.5 Efficiency Optimization（效率優化）

**目的：提升訊號密度與運行效率**

- EFF-01 精簡冗長  
  → 移除重複與低價值內容

- EFF-02 Token 最小化  
  → 保留高影響資訊

- EFF-03 高訊號密度  
  → 每句話具指令價值

---

### 2. Strategy Mapping Logic（策略對應邏輯）

---

#### 問題 → 策略對應

- Structure 問題  
  → STR-01 / STR-02 / STR-03  

- Tone 問題  
  → TONE-01 / TONE-02  

- Depth 問題  
  → DEPTH-02 / DEPTH-03  

- Execution 問題  
  → EXEC-01 / EXEC-02  

- 冗長問題  
  → EFF-01  

---

### 3. Strategy → User Options（轉換為使用者選項）

---

在 Optimization Module 中：

將策略轉換為「可選優化方向」：

- A. 結構優化（Structure Optimization）
- B. 語氣優化（Tone Optimization）
- C. 深度優化（Depth Optimization）
- D. 精簡優化（Efficiency Optimization）

---

每個選項需包含：

- 修改內容  
- 修改原因  
- 預期效果  

---

### 4. Integration with Optimization Module（整合方式）

---

在 Optimization Module Step 4：

1. 根據問題診斷（Structure / Tone / Depth / Execution）
2. 從 Strategy Library 選擇對應策略
3. 組合為 2–4 個優化選項
4. 提供使用者選擇（Human-in-the-Loop）

---

## Usage Notes

- 每次優化建議應選擇「1–2 個策略組合」，避免過度複雜  
- 優先解決高影響問題（Structure > Execution > Tone > Depth）  
- 避免同時套用過多策略（保持可控性）  
- 策略應轉換為「自然語言建議」，不顯示代碼（如 STR-01）

---

## 一句總結

👉 好的優化不是「改寫 Prompt」，而是「選擇正確策略」
