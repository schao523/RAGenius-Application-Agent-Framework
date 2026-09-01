# Testing Guide

## 目的

驗證 GPT 是否符合設計目標，並提供優化依據。

---

## 測試核心原則

1. 測試需對應應用場景  
2. 覆蓋不同使用情境  
3. 測試結果可用於優化  

---

## 測試方法

### 1. Test Cards

每個測試包含：

- 使用情境（Context）  
- 使用者輸入（Input）  
- 預期行為（Expected Behavior）  

---

### 2. 對話模擬

- 模擬真實使用者  
- 觀察回應  
- 記錄偏差  

---

### 3. 邊界測試

測試：

- 模糊輸入  
- 不完整資訊  
- 非預期問題  

---

# 🔥 Success Criteria（設計評估標準）

用於判斷 GPT 是否達到設計目標

---

## 核心五項

1. 準確性（Accuracy）  
   → 回答是否正確  

2. 相關性（Relevance）  
   → 是否貼合問題與情境  

3. 清晰度（Clarity）  
   → 是否易理解  

4. 互動性（Interaction Quality）  
   → 是否符合互動模式設計  
   → 是否有適當引導與等待  

5. 一致性（Consistency）  
   → 多次回應是否穩定  

---

## 進階評估（視需要）

6. 深度（Depth / Insight）  
   → 是否提供有價值的洞見  

7. 結構性（Structure）  
   → 是否有清楚邏輯與步驟  

8. 使用資源能力（Resource Usage）  
   → 是否正確使用提供的知識  

---

## 評估方式

可使用簡單標記：

- ✅ 符合  
- ⚠️ 部分符合  
- ❌ 不符合  

---

### 🔹 測試案例範例（Test Cards Examples）

以下提供可直接使用的測試案例：

---

### 1. 直接回答測試（Direct Answer）

- Context：使用者詢問事實性問題  
- Input：「詩篇 23 篇的背景是什麼？」  
- Expected Behavior：
  - 直接提供清楚答案  
  - 不進行過多引導或提問  

---

### 2. 引導模式測試（Guided Interaction）

- Context：使用者想進行靈修  
- Input：「我要靈修詩篇 23 篇」  
- Expected Behavior：
  - 先提出引導問題  
  - 再提供部分內容  
  - 保持互動節奏  

---

### 3. 完整流程測試（Workflow Execution）

- Context：使用者輸入經文  
- Input：「詩篇 23 篇」  
- Expected Behavior：
  - 問問題  
  - 等待使用者回應  
  - 提供補充  
  - 給應用建議  
  - 引導反思  

---

👉 可依不同 GPT 設計，擴充更多測試案例 



---

## 常見問題類型

- 回答過快（缺乏引導）  
- 跳步（未等待使用者）  
- 偏離主題  
- 未使用資源  
- 語氣不一致  

---

## 優化流程

1. 記錄問題  
2. 回到 Assistant  
3. 請求 Prompt Patch  
4. 更新 System Instructions  
5. 重新測試  

---

## 一句總結

👉 測試的目的不是找錯，而是讓 GPT 更接近設計目標


