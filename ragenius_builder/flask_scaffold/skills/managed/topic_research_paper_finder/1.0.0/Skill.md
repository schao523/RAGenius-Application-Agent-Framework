---
id: topic_research_paper_finder
name: topic-research-paper-finder
version: 1.0.0
description: Find and summarize top research papers for a user-defined topic using research_paper_search_tool.
required_tools:
  - research_paper_search_tool
required_permissions:
  - external_api.read
---

Topic Research Paper Finder

Use this skill when the user asks to find, discover, rank, compare, or summarize research papers for a specific topic.
Tool Contract

## Tool Contract

Call `research_paper_search_tool` using:
    {
      "topic": "string",
      "limit": 5,
      "source": "auto"
    }

Supported inputs:

* `topic` (required)

* `limit` (optional, range 1–10)

* `source` (optional: `auto`, `arxiv`, `semantic-scholar`)

Expected response:
    {
      "topic": "string",
      "source": "string",
      "papers": [
        {
          "title": "string",
          "link": "string",
          "year": "integer",
          "authors": ["string"],
          "summary": "string",
          "why_it_matters": "string"
        }
      ]
    }
Required Inputs
---------------

* topic

Optional Inputs
---------------

* limit (default: 5)

* source (default: auto)

Execution Steps
---------------

1. Extract `topic`, `limit`, and `source` from the user request.

2. Validate that `topic` exists.

3. If `topic` is missing, ask the user for clarification before proceeding.

4. Normalize inputs:
   
   * clamp `limit` between `1` and `10`
   
   * default `source` to `auto`

5. Call `research_paper_search_tool`.

6. Validate the returned response structure:
   
   * `topic`
   
   * `source`
   
   * `papers`

7. For each paper, verify required fields exist:
   
   * title
   
   * link
   
   * year
   
   * authors
   
   * summary
   
   * why_it_matters

8. Rank papers using:
   
   * relevance
   
   * recency (when useful)
   
   * source quality
   
   * paper significance if inferable

9. Generate structured summaries.

10. If the tool fails:
    
    * explain the failure
    
    * avoid fabricating results
    
    * suggest retrying with a narrower topic

11. Return formatted Markdown output.

Output Format
-------------

Top Research Papers: {topic}
============================

Source: `{source}`
Paper Summaries
---------------

### 1. {paper_title}

* Year: {year}

* Authors: {authors}

* Link: {link}

* Summary: {summary}

* Why it matters: {why_it_matters}

Cross-Paper Insights
--------------------

* Common themes

* Research trends

* Open questions

* Suggested reading order

Notes
-----

Mention if:

* no papers were found

* metadata is incomplete

* manual verification may be required

Safety Rules
------------

* Never invent papers or metadata.

* Never fabricate authors, years, or links.

* Clearly indicate incomplete results.

* Do not expose tool internals or credentials.

* Distinguish retrieved facts from generated synthesis.
