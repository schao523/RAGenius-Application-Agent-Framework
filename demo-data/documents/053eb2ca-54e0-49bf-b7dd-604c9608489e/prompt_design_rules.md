# # Prompt 設計規則模組（Prompt Design Rules v3.1）

## 目的

確保所有 Prompt 具備高品質設計、結構化表達與跨執行環境（Domain GPT / General LLM / Agent）適用性。

---

# 🔴Meta vs Prompt（關鍵🔥）

- Meta（Execution Type / GPT Type）  
  → 僅用於判斷  
  → 不可進入 Prompt  

- Prompt  
  → 僅包含任務指令  

---

# 🔴 一、提示設計心態（核心原則）🔥

設計 Prompt 時，必須具備以下心態：

### 1. 清楚提示

使用清晰、具體語言，避免模糊

### 2. 謙卑體諒

思考：「模型需要什麼資訊？」

### 3. 考慮周全

確保提示完整且無歧義

### 4. 總結經驗

若結果不佳 → 重新設計 Prompt

### 5. 聚焦任務

一次只處理一個任務

---

# 🔴 二、COSTAR 框架（核心結構）

所有 Prompt 必須包含：

- Context（背景）
- Objective（目標）
- Style（風格）
- Tone（語氣）
- Audience（受眾）
- Response Format（輸出格式）

---

# 🔴 三、多執行環境適配（Execution Adaptation）🔥

Prompt 必須適配：

## 1. Domain GPT

- 深度內容
- 神學一致
- 教學導向

## 2. General LLM

- 清晰
- 創意
- 易讀

## 3. Agent / Tool

- 任務導向
- 步驟清晰
- 可執行

---

# 🔴 四、任務設計原則

### 單一任務（Single Task）

避免混合多任務

---

### 任務拆解（Task Decomposition）

複雜任務需分步處理

---

### 階段引用（Chaining）

後續步驟可引用前一步輸出

---

# 🔴 五、指令設計規則

### 使用肯定語句（Positive Instruction）

✔ 使用「請...」「生成...」  
✘ 避免「不要...」

---

### 明確指令（Explicit Directive）

使用：

- 「你的任務是...」
- 「你必須...」

---

# 🔴 六、角色設定（Role-Based Prompting）

所有 Prompt 應：

- 指定角色
- 定義專業領域

例：
你是一位聖經教師...

---

# 🔴 七、思維鏈（Chain-of-Thought, CoT）🔥

對於複雜任務：

- 使用「一步一步思考」
- 引導逐步推理

---

# 🔴 八、Few-shot（例子驅動）🔥

當任務複雜或格式要求高：

- 提供 1–2 個範例
- 示範輸出格式

---

# 🔴 九、關鍵詞強化（Keyword Reinforcement）🔥

透過重複關鍵詞：

- 強化焦點
- 提升一致性

---

# 🔴 十、輸出引導（Output Priming）🔥

在提示結尾：

- 提供輸出開頭
- 指定格式

例：
「以下為五點重點：」

---

# 🔴 十一、詳細輸出規則（Detailed Output）🔥

當需要深入內容：

- 明確要求「詳細」「完整」
- 指定內容範圍與深度

---

# 🔴 十二、Audience vs Execution Type

- Audience = 人（受眾）
- Execution Type = 系統

---

# 🔴 十三、輸出品質標準

所有 Prompt 必須：

- 清晰（Clear）
- 結構化（Structured）
- 可執行（Actionable）
- 情境一致（Context-aware）

---

# 🔴 十四、強制規則（Enforcement）

若 Prompt 不符合以上標準：

→ 必須重新生成



## 🔴十五、Enforcement

若 Prompt 含 Meta：  

→ 必須移除


