# Prompt Refactoring Patterns

## 目的

提供一組精簡且高效的修訂模式，幫助優化 System Instructions 的清晰度、結構與可執行性。

---

## Pattern 1：Condense（冗長簡化）

適用：

- 重複內容
- 冗詞過多

方法：

- 合併相似句
- 移除不影響行為的描述

---

## Pattern 2：Clarify（模糊明確化）

適用：

- 指令模糊
- GPT 無法判斷行為

方法：

- 加入條件（when / if）
- 明確輸出格式

---

## Pattern 3：Structure（流程結構化）

適用：

- 長段文字
- 無清晰步驟

方法：

- 改為 step-by-step
- 使用編號

---

## Pattern 4：Decouple（耦合拆分）

適用：

- 多功能混在一起
- 模組邊界不清

方法：

- 拆為獨立 MODULE
- 分離不同責任

---

## Pattern 5：Externalize（外部化）

適用：

- 長篇說明
- 範例集合
- 方法論

方法：

- 移至 .md
- 在主指令中引用

---

## Pattern 6：Align（對齊）

適用：

- Starter Questions 與 Instructions 不一致

方法：

- 對齊觸發條件
- 對齊輸出行為

---

## Pattern 7：Standardize（標準化）

適用：

- 輸出格式不一致

方法：

- 統一輸出結構
- 建立模板

---

## 使用原則

- 優先小修，再做重構
- 不影響原功能
- 保持可讀性
- 避免過度優化

---

## 總結

好的 Prompt 修訂不是改寫，而是：
👉 提升清晰度  
👉 降低歧義  
👉 強化可執行性
