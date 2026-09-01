# Suite → Tool Mapping v1

---

## Purpose

定義每個 Suite Type 對應的工具集合（Tool Pool），
供 Tool Selection Engine 使用。

👉 所有工具選擇必須來自此表，不得自由生成。

---

## Structure

每個 Suite 包含：

- Tool Pool（完整工具集合）
- Core Candidates（核心候選）
- Supporting Candidates（支援候選）

---

## 1. 牧者套餐（Pastoral Leadership Suite）

Tool Pool：

- 講章優化教練
- 酷聖經教師
- 酷教會事工指令設計師
- 酷領導力教練

Core Candidates：

- 講章優化教練
- 酷聖經教師

Supporting：

- 指令設計師
- 領導力教練

---

## 2. 門徒裝備套餐（Discipleship Formation Suite）

Tool Pool：

- 酷聖經教師
- 酷教會歷史導師
- 基督教要義智能書
- 每日靈修時光
- 靈修操練禮贊

Core Candidates：

- 酷聖經教師
- 每日靈修時光

Supporting：

- 教會歷史導師
- 基督教要義智能書
- 靈修操練禮贊

---

## 3. 教學套餐（Teaching & Curriculum Suite）

Tool Pool：

- AI 課程設計助教
- 酷聖經教師
- 酷教會歷史導師
- 基督教要義智能書
- 酷教會事工指令設計師

Core Candidates：

- AI 課程設計助教

Supporting：

- 酷聖經教師
- 教會歷史導師
- 指令設計師

---

## 4. 關懷與陪伴套餐（Care & Pastoral Support Suite）

Tool Pool：

- 酷聖經輔導
- 幸福樂齡顧問
- 與孩子一起成長

Core Candidates：

- 酷聖經輔導

Supporting：

- 幸福樂齡顧問
- 與孩子一起成長

---

## 5. 家庭與兒童成長套餐（Family Formation Suite）

Tool Pool：

- 與孩子一起成長
- STEAM 親子共學設計助理
- 酷 Vibe 動畫故事導演

Core Candidates：

- 與孩子一起成長

Supporting：

- STEAM 助理
- 動畫導演

---

## 6. 宣教與內容創作套餐（Mission & Creative Suite）

Tool Pool：

- 酷 Vibe 動畫故事導演
- 酷 Viber 編碼設計助理
- 酷教會事工指令設計師

Core Candidates：

- 動畫導演

Supporting：

- 編碼設計助理
- 指令設計師

---

## 7. 工具設計套餐（AI Tool Designer Suite）

Tool Pool：

- 酷 GPT 應用設計助理
- 酷教會事工指令設計師
- 酷 Vibe 動畫故事導演
- 酷 Viber 編碼設計助理

Core Candidates：

- GPT 應用設計助理

Supporting：

- 指令設計師
- 編碼助理

---

## Selection Rules（供 Engine 使用）

1. 必須從 Tool Pool 選擇
2. Core 必須來自 Core Candidates
3. Supporting 來自 Supporting 或 Pool
4. 不得選擇不在 Pool 的工具
5. 不得跨 Suite 選工具

---

## Summary

👉 Suite 決定工具集合  
👉 Engine 決定工具角色
