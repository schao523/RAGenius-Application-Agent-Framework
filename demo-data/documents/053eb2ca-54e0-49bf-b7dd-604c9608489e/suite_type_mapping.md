# Suite Type Mapping v1

---

## Purpose

本模組用於判斷使用者需求應對應的「AI 工具套餐（Suite Type）」。

此判斷為 Tool Selection Engine 的前置步驟。

👉 核心原則：
Prompt 決定「做什麼」
Suite 決定「用哪個系統做」

---

## Available Suite Types

根據 AI 工具套餐體系：

1. 牧者套餐（Pastoral Leadership Suite）
2. 門徒裝備套餐（Discipleship Formation Suite）
3. 教學套餐（Teaching & Curriculum Suite）
4. 關懷與陪伴套餐（Care & Pastoral Support Suite）
5. 家庭與兒童成長套餐（Family Formation Suite）
6. 宣教與內容創作套餐（Mission & Creative Studio Suite）
7. 工具設計套餐（AI Tool Designer Suite）

---

## Mapping Logic

根據「使用情境（Use Case）」判斷 Suite：

---

### 1. 牧者套餐

適用情境：

- 講章準備
- 神學整理
- 領導決策
- 教會治理

關鍵特徵：

- 領導 / 講道 / 神學

---

### 2. 門徒裝備套餐

適用情境：

- 查經
- 門徒訓練
- 靈修裝備
- 小組成長

關鍵特徵：

- 聖經學習
- 靈命成長

---

### 3. 教學套餐

適用情境：

- 課程設計
- 主日學
- 教學活動
- 教材開發

關鍵特徵：

- 教學 / 課程 / 教育

---

### 4. 關懷與陪伴套餐

適用情境：

- 輔導
- 探訪
- 情緒支持
- 屬靈陪伴

關鍵特徵：

- 關懷 / 陪伴 / 輔導

---

### 5. 家庭與兒童成長套餐

適用情境：

- 親子教育
- 家庭建造
- 兒童主日學

關鍵特徵：

- 家庭 / 兒童 / 親子

---

### 6. 宣教與內容創作套餐

適用情境：

- 福音內容
- 社群媒體
- 影片 / 動畫
- 宣教設計

關鍵特徵：

- 創作 / 宣教 / 媒體

---

### 7. 工具設計套餐

適用情境：

- GPT 設計
- AI 應用開發
- 系統建構

關鍵特徵：

- 工具 / 系統 / 技術

---

## Selection Rules

1. 必須選擇「最主要」的一個 Suite
2. 不得同時選擇多個 Suite（避免混亂）
3. 優先判斷「使用目的」，不是表面內容
4. 若不明確 → 問 1 個問題後再判斷

---

## Fallback Rule

若無法判斷：

👉 預設使用：
門徒裝備套餐（Discipleship Formation Suite）

---

## 一句總結

👉 Suite Type = 使用者「要完成的事工系統」
