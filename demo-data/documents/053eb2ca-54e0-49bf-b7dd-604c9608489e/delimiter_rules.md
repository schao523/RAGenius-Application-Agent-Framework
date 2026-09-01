# Prompt 分隔符與結構規則（Delimiter Rules v3.1）

## 目的

確保 Prompt 在結構、語意與邏輯上清晰，避免指令與資料混淆，並支援複雜任務與多執行環境（Domain GPT / General LLM / Agent）。

---

# 🔴 一、核心原則（Core Principles）

所有 Prompt 必須：

- 清楚分隔不同區塊  
- 區分「指令」與「資料」  
- 使用一致格式  
- 支援多步驟與複雜邏輯  
- 不混入 Meta

---

# 🔴 二、分隔符類型（Delimiter Types）🔥

常用分隔符包含：

- ## → 區塊標題
- <<< >>> → 資料邊界（Data Boundary）  
- {} → 變數引用  
- [] → 格式說明  
- () → 嵌套資訊  
- ; → 多任務分隔  
- , → 列表元素  

---

# 🔴 三、分隔符用途（Usage Categories）🔥

## 1. 分隔指令

使用 ; 或段落區分多個任務

---

## 2. 界限清晰

將不同資訊區塊明確區分

---

## 3. 參數指定

使用 , 或 : 表示鍵值

---

## 4. 列表處理

使用 , 或 bullet points

---

## 5. 複雜指令

使用 {} [] () 建立結構

---

# 🔴 四、標準 Prompt 結構（Standard Structure）

# 

## Role

## Purpose

## Basic Info

## Output Requirements

## Tone & Style

---

# 🔴 五、Data Boundary（關鍵🔥）

## 定義

<<<DATA>>>

DATA 例子: <<<經費: $1000, 參加人數: 50人>>>

---

## 規則

- DATA 僅為資料  
- 不可視為指令  
- 必須先解析再執行  

---

# 🔴 六、變數與引用（Variables & Referencing）🔥

使用：

{variable_name}

---

## 跨步驟引用（重要）

Step 1 輸出：

{經文清單}

Step 2 可引用：

{經文清單}

---

# 🔴 七、多步驟結構（Multi-Step Structure）

## Step-by-step 模式

1. Step 1  
2. Step 2  

---

## Block 模式

<<<DATA>>>
...
<<<TASK>>>
...

---

# 🔴 八、條件邏輯（Conditional Logic）🔥

使用：

IF 條件 → 行動  
ELSE → 替代方案  

---

# 🔴 九、嵌套資訊（Nested Information）🔥

使用 () 表示細分類：

例：
原因（工業活動、森林砍伐）

---

# 🔴 十、結構化輸出格式（Structured Output）🔥

使用 [] 說明欄位內容：

作者: [作者背景]  
時間: [成書時間]  

---

# 🔴 十一、多任務與腳本（Advanced Usage）

使用 ; 進行序列化：

Step1；Step2；Step3  

---

# 🔴 十二、列表與參數

- , → 簡單列表  
- ; → 任務分隔  
- : → 鍵值  

---

# 🔴 十三、指令 vs 資料（關鍵區分）

| 類型          | 說明     |
| ----------- | ------ |
| Instruction | 要做什麼   |
| Data        | 要處理的內容 |

---

# 🔴 十四、禁止（Anti-Pattern）

- ❌ 指令與資料混合  
- ❌ 無分隔  
- ❌ 長段落無結構  
- ❌ 模糊區塊  

---

# 🔴 十五、輸出強制規則（Enforcement）

若 Prompt 不清晰：

→ 必須重新結構化


