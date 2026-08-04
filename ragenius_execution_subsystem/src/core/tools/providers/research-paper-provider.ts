import type { ResearchPaperProviderConfig } from "../../../config/provider-config.js";
import { AppError } from "../../errors/app-error.js";

import { HttpClient } from "./http-client.js";

type SearchSource = "auto" | "arxiv" | "semantic-scholar";

type ResearchPaper = {
  title: string;
  link: string;
  year: number;
  authors: string[];
  summary: string;
  why_it_matters: string;
};

type SearchRequest = {
  topic: string;
  limit: number;
  source: SearchSource;
};

type SearchResult = {
  topic: string;
  source: "arxiv" | "semantic-scholar";
  papers: ResearchPaper[];
};

function decodeXmlEntities(value: string): string {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function extractXmlTag(block: string, tagName: string): string {
  const match = block.match(
    new RegExp(`<${tagName}[^>]*>([\\s\\S]*?)</${tagName}>`, "i")
  );
  return decodeXmlEntities((match?.[1] ?? "").replace(/\s+/g, " ").trim());
}

function extractXmlTags(block: string, tagName: string): string[] {
  return Array.from(
    block.matchAll(new RegExp(`<${tagName}[^>]*>([\\s\\S]*?)</${tagName}>`, "gi"))
  ).map((match) =>
    decodeXmlEntities((match[1] ?? "").replace(/\s+/g, " ").trim())
  );
}

function summarizeWhyItMatters(topic: string, source: string): string {
  return `Relevant to ${topic} based on ${source} search results.`;
}

function parseArxivFeed(
  xml: string,
  topic: string,
  source: string
): ResearchPaper[] {
  const entries = xml.split(/<entry>/i).slice(1);
  return entries
    .map((entry) => {
      const title = extractXmlTag(entry, "title");
      const link = extractXmlTag(entry, "id");
      const summary = extractXmlTag(entry, "summary");
      const published = extractXmlTag(entry, "published");
      const authors = extractXmlTags(entry, "name").filter(Boolean);
      const year = Number.parseInt(published.slice(0, 4), 10);
      if (!title || !link) {
        return null;
      }
      return {
        title,
        link,
        year: Number.isNaN(year) ? 0 : year,
        authors,
        summary,
        why_it_matters: summarizeWhyItMatters(topic, source)
      } satisfies ResearchPaper;
    })
    .filter((paper): paper is ResearchPaper => paper !== null);
}

function mapSemanticScholarPapers(
  payload: Record<string, unknown>,
  topic: string,
  source: string
): ResearchPaper[] {
  const data = Array.isArray(payload.data) ? payload.data : [];
  return data
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      const authors = Array.isArray(row.authors)
        ? row.authors
            .map((author) =>
              author && typeof author === "object"
                ? String(
                    (author as Record<string, unknown>).name ?? ""
                  ).trim()
                : ""
            )
            .filter(Boolean)
        : [];
      const title = String(row.title ?? "").trim();
      const link = String(row.url ?? "").trim();
      const summary = String(row.abstract ?? "").trim();
      const year =
        typeof row.year === "number"
          ? row.year
          : Number.parseInt(String(row.year ?? "0"), 10);
      if (!title || !link) {
        return null;
      }
      return {
        title,
        link,
        year: Number.isNaN(year) ? 0 : year,
        authors,
        summary,
        why_it_matters: summarizeWhyItMatters(topic, source)
      } satisfies ResearchPaper;
    })
    .filter((paper): paper is ResearchPaper => paper !== null);
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export class ResearchPaperProvider {
  constructor(
    private readonly config: ResearchPaperProviderConfig,
    private readonly httpClient = new HttpClient()
  ) {}

  async search(request: SearchRequest): Promise<SearchResult> {
    if (request.source === "arxiv") {
      return {
        topic: request.topic,
        source: "arxiv",
        papers: await this.searchArxiv(request.topic, request.limit)
      };
    }

    if (request.source === "semantic-scholar") {
      try {
        return {
          topic: request.topic,
          source: "semantic-scholar",
          papers: await this.searchSemanticScholar(request.topic, request.limit)
        };
      } catch {
        return {
          topic: request.topic,
          source: "arxiv",
          papers: await this.searchArxiv(request.topic, request.limit)
        };
      }
    }

    let arxivPapers: ResearchPaper[] = [];
    if (this.config.arxiv.enabled) {
      try {
        arxivPapers = await this.searchArxiv(request.topic, request.limit);
      } catch (_error) {
        arxivPapers = [];
      }
    }

    if (arxivPapers.length >= request.limit) {
      return {
        topic: request.topic,
        source: "arxiv",
        papers: arxivPapers
      };
    }

    if (!this.config.semanticScholar.enabled) {
      return {
        topic: request.topic,
        source: "arxiv",
        papers: arxivPapers
      };
    }

    try {
      const semanticPapers = await this.searchSemanticScholar(
        request.topic,
        request.limit
      );
      if (semanticPapers.length > arxivPapers.length) {
        return {
          topic: request.topic,
          source: "semantic-scholar",
          papers: semanticPapers
        };
      }
    } catch (_error) {
      // fall through to arXiv results
    }

    return {
      topic: request.topic,
      source: "arxiv",
      papers: arxivPapers
    };
  }

  private async searchArxiv(
    topic: string,
    limit: number
  ): Promise<ResearchPaper[]> {
    if (!this.config.arxiv.enabled) {
      return [];
    }

    const searchQuery = encodeURIComponent(`all:${topic}`);
    let response: Response;
    try {
      response = await this.httpClient.fetchWithPolicy(
        `https://export.arxiv.org/api/query?search_query=${searchQuery}&start=0&max_results=${limit}&sortBy=relevance&sortOrder=descending`,
        {
          headers: {
            Accept: "application/atom+xml",
            "User-Agent":
              "RAGenius-ExecutionSubsystem/0.1 (Builder-integrated research lookup)"
          },
          retryOnStatuses: this.config.arxiv.retryOn429 ? [429] : [],
          timeoutMs: this.config.arxiv.requestTimeoutMs,
          maxRetries: this.config.arxiv.maxRetries
        }
      );
    } catch (error) {
      if (isAbortError(error)) {
        throw new AppError({
          code: "ARXIV_LOOKUP_FAILED",
          message: "arXiv search request failed.",
          errorClass: "external_api",
          httpStatus: 502,
          details: { cause: "timeout" },
          recoverable: true,
          suggestedAction: "Retry later or use a different source."
        });
      }
      throw error;
    }

    if (!response.ok) {
      throw new AppError({
        code: "ARXIV_LOOKUP_FAILED",
        message: "arXiv search request failed.",
        errorClass: "external_api",
        httpStatus: 502,
        details: { status: response.status },
        recoverable: true,
        suggestedAction: "Retry later or use a different source."
      });
    }

    return parseArxivFeed(await response.text(), topic, "arxiv");
  }

  private async searchSemanticScholar(
    topic: string,
    limit: number
  ): Promise<ResearchPaper[]> {
    if (!this.config.semanticScholar.enabled) {
      return [];
    }

    const url = new URL("https://api.semanticscholar.org/graph/v1/paper/search");
    url.searchParams.set("query", topic);
    url.searchParams.set("limit", String(limit));
    url.searchParams.set("fields", "title,url,year,authors,abstract");

    const headers: Record<string, string> = {
      Accept: "application/json"
    };
    if (this.config.semanticScholar.apiKey) {
      headers["x-api-key"] = this.config.semanticScholar.apiKey;
    }

    let response: Response;
    try {
      response = await this.httpClient.fetchWithPolicy(url, {
        headers,
        timeoutMs: this.config.semanticScholar.requestTimeoutMs
      });
    } catch (error) {
      if (isAbortError(error)) {
        throw new AppError({
          code: "SEMANTIC_SCHOLAR_LOOKUP_FAILED",
          message: "Semantic Scholar search request failed.",
          errorClass: "external_api",
          httpStatus: 502,
          details: { cause: "timeout" },
          recoverable: true,
          suggestedAction: "Retry later or use a different source."
        });
      }
      throw error;
    }

    if (!response.ok) {
      throw new AppError({
        code: "SEMANTIC_SCHOLAR_LOOKUP_FAILED",
        message: "Semantic Scholar search request failed.",
        errorClass: "external_api",
        httpStatus: 502,
        details: { status: response.status },
        recoverable: true,
        suggestedAction: "Retry later or use a different source."
      });
    }

    return mapSemanticScholarPapers(
      (await response.json()) as Record<string, unknown>,
      topic,
      "semantic-scholar"
    );
  }
}
