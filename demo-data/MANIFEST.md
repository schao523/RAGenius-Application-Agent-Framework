# RAGenius Demo Data Manifest

This folder contains immutable seed data for the public RAGenius demo.
Demo startup scripts should copy this data into writable runtime folders and regenerate machine-local paths.

## Included demo applications

| Application | App ID | Documents | Snapshot status | Purpose |
|---|---:|---:|---|---|
| 教會事工指令設計師  Church Ministry Prompt Designer | `053eb2ca-54e0-49bf-b7dd-604c9608489e` | 9 | ready | Prompt design workflow demo for church ministry content and structured prompt generation. |
| Bible Tutor 酷聖經教師  4.0 | `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | 13 | ready | RAG and guided Bible-study workflow demo with app-scoped resources. |
| 酷 GPT 應用設計助理 Pro  GPT Application Design Assistant | `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | 15 | ready | GPT application design workflow demo for Builder-authored application design support. |

## Provenance

- Bible PDFs are marked `public-domain`.
- Project-authored markdown and PDF resources are marked `project-authored`.
- No credentials, private user data, generated logs, mutable runtime DBs, or vector indexes are intentionally included.

## Document inventory

| Application ID | Filename | License | Redistribution | Seed path |
|---|---|---|---|---|
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | AI 工具套餐體系.pdf | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/AI 工具套餐體系.pdf` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | AI 工具套餐體系總覽清單.pdf | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/AI 工具套餐體系總覽清單.pdf` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | Optimization Strategy Library.md | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/Optimization Strategy Library.md` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | delimiter_rules.md | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/delimiter_rules.md` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | dynamic_prompt_optimizer.md | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/dynamic_prompt_optimizer.md` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | prompt_design_rules.md | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/prompt_design_rules.md` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | suite_tool_mapping.md | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/suite_tool_mapping.md` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | suite_type_mapping.md | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/suite_type_mapping.md` |
| `053eb2ca-54e0-49bf-b7dd-604c9608489e` | template_library.md | project-license | approved | `documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/template_library.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | Bible 新約聖經和合本.pdf | public-domain | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/Bible 新約聖經和合本.pdf` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | Bible 舊約聖經和合本.pdf | public-domain | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/Bible 舊約聖經和合本.pdf` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | answer_questions_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/answer_questions_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | apply_in_action_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/apply_in_action_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | examine_structure_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/examine_structure_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | formulate_questions_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/formulate_questions_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | identify_relationships_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/identify_relationships_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | identify_theme_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/identify_theme_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | list_specifics_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/list_specifics_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | observation_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/observation_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | summarize_meaning_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/summarize_meaning_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | write_principles_guide.md | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/write_principles_guide.md` |
| `2302c77b-3d82-4650-bd15-e0ff9c0faab7` | 合法處境補充材料.pdf | project-license | approved | `documents/2302c77b-3d82-4650-bd15-e0ff9c0faab7/合法處境補充材料.pdf` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | Human-in-the-Loop_Guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/Human-in-the-Loop_Guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | builder_guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/builder_guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | interaction_patterns_guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/interaction_patterns_guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | knowledge_module_template.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/knowledge_module_template.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | modular_design_guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/modular_design_guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | prompt_refactoring_patterns.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/prompt_refactoring_patterns.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | resource_binding_patterns.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/resource_binding_patterns.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | resource_evaluation_guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/resource_evaluation_guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | resource_types_guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/resource_types_guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | testing_guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/testing_guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | use_case_brainstorm_guide.md | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/use_case_brainstorm_guide.md` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | 分析與設計AI教牧助手.pdf | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/分析與設計AI教牧助手.pdf` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | 測試與優化AI教牧助手.pdf | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/測試與優化AI教牧助手.pdf` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | 配置與功能實現AI教牧助手.pdf | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/配置與功能實現AI教牧助手.pdf` |
| `dd494ba5-face-4eaf-95d1-a55cb9f80c78` | 酷聖經輔導.pdf | project-license | approved | `documents/dd494ba5-face-4eaf-95d1-a55cb9f80c78/酷聖經輔導.pdf` |
