import { createHash, randomBytes, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export type RequestInputScope = {
  app_id: string;
  execution_id: string;
  provider_session_key: string;
  session_id: string;
};

export type TrustedToolIdentity = {
  agent_id: string;
  provider_run_id: string;
  provider_session_key: string;
  tool_call_id: string;
};

type RequestOption = {
  description?: string;
  id: string;
  label: string;
};

type RequestState =
  | "pending"
  | "continuation_pending"
  | "resolved"
  | "expired"
  | "cancelled"
  | "interrupted";

type RequestResponse =
  | { kind: "selection"; option_ids: string[] }
  | { kind: "clarification"; text: string };

export type OpenClawInputRequest = RequestInputScope & {
  agent_id: string;
  allows_free_text: boolean;
  binding_nonce_hash: string;
  created_at_ms: number;
  expires_at_ms: number;
  options: RequestOption[];
  plugin_protocol_version: "1";
  provider_run_id: string;
  question: string;
  request_id: string;
  secret_input: false;
  tool_call_id: string;
};

type StoredRequest = {
  continuation_run_id: string | null;
  idempotency_key: string | null;
  request: OpenClawInputRequest;
  response: RequestResponse | null;
  state: RequestState;
};

type PersistedState = {
  process_id?: number;
  protocol_version: "1";
  requests: StoredRequest[];
  sessions?: Array<{
    nonce_hashes?: string[];
    scope: RequestInputScope;
    trusted_session_key: string;
  }>;
};

export class RequestInputRegistry {
  private readonly bindingNonces = new Map<string, string>();
  private readonly maxPending: number;
  private readonly now: () => number;
  private readonly processId: number;
  private readonly requests = new Map<string, StoredRequest>();
  private readonly sessionNonceHashes = new Map<string, string[]>();
  private readonly sessions = new Map<string, RequestInputScope>();
  private readonly statePath: string;
  private persistTail: Promise<void> = Promise.resolve();

  constructor(options: {
    maxPending?: number;
    now?: () => number;
    processId?: number;
    statePath: string;
  }) {
    this.maxPending = options.maxPending ?? 100;
    this.now = options.now ?? Date.now;
    this.processId = options.processId ?? process.pid;
    this.statePath = options.statePath;
  }

  async initialize(): Promise<void> {
    const parsed = await this.readState();
    if (!parsed) return;
    const interrupted = this.applyState(parsed, parsed.process_id !== this.processId);
    if (interrupted) await this.persist();
  }

  async refresh(): Promise<void> {
    const parsed = await this.readState();
    if (!parsed) return;
    const interrupted = this.applyState(parsed, parsed.process_id !== this.processId);
    if (interrupted) await this.persist();
  }

  bindSession(scope: RequestInputScope): void {
    validateScope(scope);
    this.sessions.set(scope.provider_session_key, { ...scope });
  }

  bindTrustedSessionKey(trustedSessionKey: string, scope: RequestInputScope): void {
    boundedText(trustedSessionKey, 1, 512, "trusted provider session key");
    validateScope(scope);
    this.sessions.set(trustedSessionKey, { ...scope });
  }

  async persistBindings(): Promise<void> {
    await this.persist();
  }

  async isTrustedSessionBound(trustedSessionKey: string): Promise<boolean> {
    if (!this.sessions.has(trustedSessionKey)) await this.refresh();
    return this.sessions.has(trustedSessionKey);
  }

  prepareBindingNonces(trustedSessionKeys: string[], count: number): string[] {
    if (!Number.isInteger(count) || count < 1 || count > 20) {
      throw new Error("Binding nonce count must be between 1 and 20.");
    }
    const nonces = Array.from({ length: count }, () => randomBytes(32).toString("base64url"));
    const hashes = nonces.map(hash);
    for (const trustedSessionKey of trustedSessionKeys) {
      if (!this.sessions.has(trustedSessionKey)) {
        throw new Error("Cannot prepare nonces for an unbound trusted session key.");
      }
      this.sessionNonceHashes.set(trustedSessionKey, [...hashes]);
    }
    return nonces;
  }

  async create(input: {
    allows_free_text: boolean;
    options?: RequestOption[];
    question: string;
    trusted: TrustedToolIdentity;
    ttl_ms?: number;
  }): Promise<{ binding_nonce: string; request: OpenClawInputRequest }> {
    let scope = this.sessions.get(input.trusted.provider_session_key);
    if (!scope) {
      await this.refresh();
      scope = this.sessions.get(input.trusted.provider_session_key);
    }
    if (!scope) throw new Error("Trusted provider session is not bound to a RAGenius scope.");
    validateTrusted(input.trusted);
    const question = boundedText(input.question, 1, 2_000, "question");
    const options = validateOptions(input.options ?? []);
    if (!input.allows_free_text && options.length === 0) {
      throw new Error("A request without free text requires at least one option.");
    }
    rejectSecretOrAuthorization([question, ...options.flatMap(optionText)]);
    const pending = [...this.requests.values()].filter((value) => value.state === "pending").length;
    if (pending >= this.maxPending) throw new Error("OpenClaw pending request limit exceeded.");
    const ttlMs = input.ttl_ms ?? 300_000;
    if (!Number.isInteger(ttlMs) || ttlMs < 1 || ttlMs > 300_000) {
      throw new Error("Request TTL must be between 1 and 300000 milliseconds.");
    }
    const preparedHashes = this.sessionNonceHashes.get(input.trusted.provider_session_key);
    const bindingNonce = preparedHashes?.length
      ? ""
      : randomBytes(32).toString("base64url");
    const bindingNonceHash = preparedHashes?.shift() ?? hash(bindingNonce);
    const now = this.now();
    const request: OpenClawInputRequest = {
      ...scope,
      agent_id: input.trusted.agent_id,
      allows_free_text: input.allows_free_text,
      binding_nonce_hash: bindingNonceHash,
      created_at_ms: now,
      expires_at_ms: now + ttlMs,
      options,
      plugin_protocol_version: "1",
      provider_run_id: input.trusted.provider_run_id,
      question,
      request_id: randomUUID(),
      secret_input: false,
      tool_call_id: input.trusted.tool_call_id
    };
    this.requests.set(request.request_id, {
      continuation_run_id: null,
      idempotency_key: null,
      request,
      response: null,
      state: "pending"
    });
    if (bindingNonce) this.bindingNonces.set(request.request_id, bindingNonce);
    await this.persist();
    return { binding_nonce: bindingNonce, request: cloneRequest(request) };
  }

  get(requestId: string): (StoredRequest & { request: OpenClawInputRequest }) | null {
    const stored = this.requests.get(requestId);
    return stored ? cloneStored(stored) : null;
  }

  getBindingNonce(requestId: string): string | null {
    return this.bindingNonces.get(requestId) ?? null;
  }

  list(scope: RequestInputScope): StoredRequest[] {
    return [...this.requests.values()]
      .filter((stored) => matchesScope(stored.request, scope))
      .map(cloneStored);
  }

  async clear(scope: RequestInputScope): Promise<number> {
    let removed = 0;
    let changed = false;
    for (const [requestId, stored] of this.requests) {
      if (!matchesScope(stored.request, scope)) continue;
      this.requests.delete(requestId);
      this.bindingNonces.delete(requestId);
      removed += 1;
      changed = true;
    }
    for (const [trustedSessionKey, boundScope] of this.sessions) {
      if (!matchesScope(boundScope, scope)) continue;
      this.sessions.delete(trustedSessionKey);
      this.sessionNonceHashes.delete(trustedSessionKey);
      changed = true;
    }
    if (changed) await this.persist();
    return removed;
  }

  async resolve(input: RequestInputScope & {
    binding_nonce: string;
    idempotency_key: string;
    provider_run_id: string;
    request_id: string;
    response: RequestResponse;
    tool_call_id: string;
  }): Promise<{
    continuation_run_id?: string;
    outcome: "continuation_required" | "replay" | "conflict" | "expired" | "cancelled" | "interrupted" | "not_found";
    response?: RequestResponse;
  }> {
    await this.refresh();
    const stored = this.match(input);
    if (!stored) return { outcome: "not_found" };
    if (stored.state === "expired" || stored.state === "cancelled" || stored.state === "interrupted") {
      return { outcome: stored.state };
    }
    if (stored.idempotency_key === input.idempotency_key) {
      if (!responsesEqual(stored.response, input.response)) return { outcome: "conflict" };
      if (stored.state === "continuation_pending" && stored.response) {
        return { outcome: "continuation_required", response: cloneResponse(stored.response) };
      }
      return {
        outcome: "replay",
        ...(stored.continuation_run_id
          ? { continuation_run_id: stored.continuation_run_id }
          : {})
      };
    }
    if (stored.state !== "pending" || stored.idempotency_key) return { outcome: "conflict" };
    if (stored.request.expires_at_ms <= this.now()) {
      stored.state = "expired";
      await this.persist();
      return { outcome: "expired" };
    }
    const response = validateResponse(stored.request, input.response);
    stored.idempotency_key = boundedText(input.idempotency_key, 1, 128, "idempotency key");
    stored.response = response;
    stored.state = "continuation_pending";
    await this.persist();
    return { outcome: "continuation_required", response: cloneResponse(response) };
  }

  async completeContinuation(
    requestId: string,
    idempotencyKey: string,
    continuationRunId: string
  ): Promise<{ outcome: "applied" | "replay" | "conflict"; continuation_run_id?: string }> {
    await this.refresh();
    const stored = this.requests.get(requestId);
    if (!stored || stored.idempotency_key !== idempotencyKey) return { outcome: "conflict" };
    if (stored.state === "resolved") {
      return {
        outcome: "replay",
        ...(stored.continuation_run_id
          ? { continuation_run_id: stored.continuation_run_id }
          : {})
      };
    }
    if (stored.state !== "continuation_pending") return { outcome: "conflict" };
    stored.continuation_run_id = boundedText(
      continuationRunId, 1, 256, "continuation run id"
    );
    stored.state = "resolved";
    await this.persist();
    return { outcome: "applied", continuation_run_id: stored.continuation_run_id };
  }

  async cancel(input: RequestInputScope & {
    binding_nonce: string;
    provider_run_id: string;
    reason: string;
    request_id: string;
    tool_call_id: string;
  }): Promise<{ outcome: "cancelled" | "conflict" | "not_found" }> {
    await this.refresh();
    const stored = this.match(input);
    if (!stored) return { outcome: "not_found" };
    if (stored.state === "cancelled") return { outcome: "cancelled" };
    if (stored.state !== "pending") return { outcome: "conflict" };
    stored.state = "cancelled";
    await this.persist();
    return { outcome: "cancelled" };
  }

  async expire(): Promise<{ expired: number }> {
    await this.refresh();
    const now = this.now();
    let expired = 0;
    for (const stored of this.requests.values()) {
      if (stored.state === "pending" && stored.request.expires_at_ms <= now) {
        stored.state = "expired";
        expired += 1;
      }
    }
    if (expired > 0) await this.persist();
    return { expired };
  }

  private match(input: RequestInputScope & {
    binding_nonce: string;
    provider_run_id: string;
    request_id: string;
    tool_call_id: string;
  }): StoredRequest | null {
    const stored = this.requests.get(input.request_id);
    if (!stored) return null;
    const request = stored.request;
    if (
      request.app_id !== input.app_id ||
      request.execution_id !== input.execution_id ||
      request.session_id !== input.session_id ||
      request.provider_session_key !== input.provider_session_key ||
      request.provider_run_id !== input.provider_run_id ||
      request.tool_call_id !== input.tool_call_id ||
      request.binding_nonce_hash !== hash(input.binding_nonce)
    ) return null;
    return stored;
  }

  private async persist(): Promise<void> {
    const pending = this.persistTail.then(() => this.writeState());
    this.persistTail = pending.catch(() => undefined);
    await pending;
  }

  private async writeState(): Promise<void> {
    await mkdir(dirname(this.statePath), { recursive: true });
    const temporaryPath = `${this.statePath}.${process.pid}.${randomUUID()}.tmp`;
    const state: PersistedState = {
      process_id: this.processId,
      protocol_version: "1",
      requests: [...this.requests.values()].map(cloneStored),
      sessions: [...this.sessions.entries()].map(([trustedSessionKey, scope]) => ({
        nonce_hashes: [...(this.sessionNonceHashes.get(trustedSessionKey) ?? [])],
        scope: { ...scope },
        trusted_session_key: trustedSessionKey
      }))
    };
    await writeFile(temporaryPath, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
    await rename(temporaryPath, this.statePath);
  }

  private applyState(parsed: PersistedState, interruptPending: boolean): boolean {
    if (parsed.protocol_version !== "1" || !Array.isArray(parsed.requests)) return false;
    this.requests.clear();
    this.sessions.clear();
    this.sessionNonceHashes.clear();
    for (const binding of parsed.sessions ?? []) {
      validateScope(binding.scope);
      this.sessions.set(
        boundedText(binding.trusted_session_key, 1, 512, "trusted provider session key"),
        { ...binding.scope }
      );
      this.sessionNonceHashes.set(
        binding.trusted_session_key,
        Array.isArray(binding.nonce_hashes) ? [...binding.nonce_hashes] : []
      );
    }
    let interrupted = false;
    for (const stored of parsed.requests) {
      const state = interruptPending && (
        stored.state === "pending" || stored.state === "continuation_pending"
      ) ? "interrupted" : stored.state;
      interrupted ||= state !== stored.state;
      this.requests.set(stored.request.request_id, {
        ...stored,
        request: cloneRequest(stored.request),
        response: stored.response ? cloneResponse(stored.response) : null,
        state
      });
    }
    for (const requestId of this.bindingNonces.keys()) {
      if (!this.requests.has(requestId)) this.bindingNonces.delete(requestId);
    }
    return interrupted;
  }

  private async readState(): Promise<PersistedState | null> {
    try {
      return JSON.parse(await readFile(this.statePath, "utf8")) as PersistedState;
    } catch (error) {
      if (isMissingFile(error)) return null;
      throw error;
    }
  }
}

function validateScope(scope: RequestInputScope): void {
  for (const [key, value] of Object.entries(scope)) boundedText(value, 1, 256, key);
}

function matchesScope(request: RequestInputScope, scope: RequestInputScope): boolean {
  return (
    request.app_id === scope.app_id &&
    request.execution_id === scope.execution_id &&
    request.session_id === scope.session_id &&
    request.provider_session_key === scope.provider_session_key
  );
}

function validateTrusted(value: TrustedToolIdentity): void {
  for (const [key, item] of Object.entries(value)) boundedText(item, 1, 256, key);
}

function validateOptions(options: RequestOption[]): RequestOption[] {
  if (!Array.isArray(options) || options.length > 20) throw new Error("Request options exceed the limit.");
  const ids = new Set<string>();
  return options.map((option) => {
    const id = boundedText(option.id, 1, 64, "option id");
    if (ids.has(id)) throw new Error("Request option ids must be unique.");
    ids.add(id);
    const normalized: RequestOption = {
      id,
      label: boundedText(option.label, 1, 200, "option label")
    };
    if (option.description !== undefined) {
      normalized.description = boundedText(option.description, 1, 500, "option description");
    }
    return normalized;
  });
}

function validateResponse(request: OpenClawInputRequest, response: RequestResponse): RequestResponse {
  if (response.kind === "selection") {
    if (!Array.isArray(response.option_ids) || response.option_ids.length !== 1) {
      throw new Error("A selection response requires exactly one option id.");
    }
    const optionId = boundedText(response.option_ids[0] ?? "", 1, 64, "selected option id");
    if (!request.options.some((option) => option.id === optionId)) {
      throw new Error("Selected option is not available.");
    }
    return { kind: "selection", option_ids: [optionId] };
  }
  if (response.kind === "clarification" && request.allows_free_text) {
    const text = boundedText(response.text, 1, 8_000, "clarification response");
    rejectSecretOrAuthorization([text]);
    return { kind: "clarification", text };
  }
  throw new Error("Response kind does not match the request.");
}

function rejectSecretOrAuthorization(values: string[]): void {
  const text = values.join(" ");
  if (/\b(password|passcode|otp|one[- ]time code|api[- ]?key|access token|cookie|credential|private key|secret)\b/i.test(text)) {
    throw new Error("Request-input cannot collect secret input.");
  }
  if (/\b(approve|authorize|permission|consent|publish|send|delete|purchase|external write|run command)\b/i.test(text)) {
    throw new Error("Request-input cannot request authorization.");
  }
}

function boundedText(value: unknown, minimum: number, maximum: number, label: string): string {
  if (typeof value !== "string") throw new Error(`${label} must be text.`);
  const normalized = value.trim();
  if (normalized.length < minimum || normalized.length > maximum) {
    throw new Error(`${label} must contain ${minimum} to ${maximum} characters.`);
  }
  return normalized;
}

function optionText(option: RequestOption): string[] {
  return [option.id, option.label, ...(option.description ? [option.description] : [])];
}

function hash(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function cloneRequest(request: OpenClawInputRequest): OpenClawInputRequest {
  return { ...request, options: request.options.map((option) => ({ ...option })) };
}

function cloneResponse(response: RequestResponse): RequestResponse {
  return response.kind === "selection"
    ? { kind: "selection", option_ids: [...response.option_ids] }
    : { ...response };
}

function cloneStored(stored: StoredRequest): StoredRequest {
  return {
    ...stored,
    request: cloneRequest(stored.request),
    response: stored.response ? cloneResponse(stored.response) : null
  };
}

function responsesEqual(left: RequestResponse | null, right: RequestResponse): boolean {
  return left !== null && JSON.stringify(left) === JSON.stringify(right);
}

function isMissingFile(error: unknown): boolean {
  return error instanceof Error && "code" in error && error.code === "ENOENT";
}
