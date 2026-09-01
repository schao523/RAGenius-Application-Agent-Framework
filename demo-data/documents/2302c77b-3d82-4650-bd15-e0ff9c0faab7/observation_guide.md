# 📘 External Resource: 細察事實觀察的項目 (Observation Guide)

## 📖 Resource Purpose

This resource provides a **complete, 17-item observation checklist** for the *細察事實 (Observation)* step in the Inductive Bible Study method.  

It enables the **Bible Teacher GPT** to automatically select suitable “observation items” and **formulate contextualized questions** based on the Bible verse or passage under study.

---

## 🔍 Observation Items (細察事實觀察的項目)

1. **文體 (Genre)** — 經文的文學形式（敘事、詩歌、比喻、預言等）。  
2. **人物 (Character)** — 主要與陪襯人物的角色、性格與動機。  
3. **時間 (Time)** — 事件發生的時序與歷史背景。  
4. **地點 (Place)** — 事件發生的地理與象徵性位置。  
5. **情況或場景 (Situation / Scene)** — 故事的背景與場合。  
6. **評語 (Comment)** — 作者在敘事中插入的個人詮釋或解釋。  
7. **強調語句 (Emphasis)** — 重複、對比、語法結構上強調重點的句子。  
8. **引用語 (Quotation)** — 明引與暗用的經文或故事。  
9. **問句 (Question)** — 用問句激發思考或傳達強調。  
10. **命令 (Command)** — 命令或勸導性語句，通常為行動導向。  
11. **應許 (Promise)** — 神的應許（有條件／無條件）。  
12. **警告 (Warning)** — 反面的命令或對錯誤行動的警戒。  
13. **例證 (Illustration)** — 作者引用的歷史事件或日常經驗作為說明。  
14. **神學性的觀念 (Theological Concept)** — 具神學深度的詞語或概念。  
15. **關鍵字 (Key Word)** — 對理解經文意義具重大影響的字或短語。  
16. **象徵性用語 (Figurative Language)** — 用象徵或比喻描述觀念的詞語。  
17. **難解的用語 (Difficult Term)** — 專有名詞、地名或歷史用語需要特別研究。  

---

## 🧠 How the Teacher Uses This Resource

When a user begins a **Bible passage study**, the Teacher GPT should:  

1. **Identify Context**  
   
   - 根據經文的內容與文體，從此資源中挑選相關的觀察項目。  

2. **Generate Questions**  
   
   - 對於每個選定的項目，生成啟發式問題，例如：  
     - 「這段經文的主要人物是誰？他們的行動揭示了什麼？」  
     - 「這裡的地點有沒有象徵性的意義？」  
     - 「有沒有重複出現的關鍵字或強調語句？」  

3. **Guide User Interaction**  
   
   - 在使用者回答後，教師 GPT 會：  
     - 若回答不完整 → 提出追問或補充提示。  
     - 若回答正確 → 詢問是否想繼續探索其他觀察項目或進入下一步（認清關係）。  

---

## ⚙️ Builder Configuration

**Resource Name:**  
`細察事實觀察的項目 (Observation Checklist)`

**Resource Type:**  
Reference Document

**Purpose Tag:**  
Used by the *Bible Teacher GPT* during the *Observation (細察事實)* step to form study questions.

**Access Behavior:**  

- Read-only reference for generating observation-based questions.  
- Accessible when conversation context includes:  
  - Keywords: “細察事實”, “觀察”, “經文”, “查經”。
