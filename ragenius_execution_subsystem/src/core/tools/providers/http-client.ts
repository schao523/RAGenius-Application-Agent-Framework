export interface HttpRequestOptions {
  headers?: RequestInit["headers"];
  retryOnStatuses?: number[];
  timeoutMs: number;
  maxRetries?: number;
}

export class HttpClient {
  constructor(private readonly fetchImpl: typeof fetch = fetch) {}

  async fetchWithPolicy(
    input: string | URL,
    options: HttpRequestOptions
  ): Promise<Response> {
    const {
      headers,
      retryOnStatuses = [],
      timeoutMs,
      maxRetries = 0
    } = options;

    for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
      const response = await this.fetchOnce(input, {
        headers,
        timeoutMs
      });

      if (
        attempt === maxRetries ||
        !retryOnStatuses.includes(response.status)
      ) {
        return response;
      }

      const retryAfterHeader = response.headers.get("retry-after");
      const retryAfterSeconds = Number.parseInt(retryAfterHeader ?? "", 10);
      const waitMs = Number.isFinite(retryAfterSeconds)
        ? retryAfterSeconds * 1_000
        : 750;
      await new Promise((resolve) => setTimeout(resolve, waitMs));
    }

    throw new Error("unreachable");
  }

  private async fetchOnce(
    input: string | URL,
    options: { headers?: RequestInit["headers"]; timeoutMs: number }
  ): Promise<Response> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs);
    try {
      return await this.fetchImpl(input, {
        ...(options.headers ? { headers: options.headers } : {}),
        signal: controller.signal
      });
    } finally {
      clearTimeout(timeout);
    }
  }
}
