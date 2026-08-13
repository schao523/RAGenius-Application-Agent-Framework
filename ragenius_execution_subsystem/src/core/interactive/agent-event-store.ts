import type {
  AgentExecutionEvent,
  ExecutionScope
} from "./interactive-agent-types.js";

export type AppendAgentEventInput = Omit<AgentExecutionEvent, "sequence">;

export interface ListAgentEventsInput extends ExecutionScope {
  afterSequence: number;
  limit: number;
}

export interface AgentEventStore {
  append(input: AppendAgentEventInput): Promise<AgentExecutionEvent>;
  list(input: ListAgentEventsInput): Promise<AgentExecutionEvent[]>;
}

export class InMemoryAgentEventStore implements AgentEventStore {
  private readonly events = new Map<string, AgentExecutionEvent[]>();
  private readonly providerRefs = new Map<string, AgentExecutionEvent>();

  async append(input: AppendAgentEventInput): Promise<AgentExecutionEvent> {
    if (input.providerEventRef) {
      const duplicate = this.providerRefs.get(providerKey(input, input.providerEventRef));
      if (duplicate) {
        return cloneEvent(duplicate);
      }
    }
    const records = this.events.get(input.executionId) ?? [];
    const event: AgentExecutionEvent = {
      ...input,
      payload: { ...input.payload },
      sequence: records.length + 1
    };
    records.push(event);
    this.events.set(input.executionId, records);
    if (event.providerEventRef) {
      this.providerRefs.set(providerKey(event, event.providerEventRef), event);
    }
    return cloneEvent(event);
  }

  async list(input: ListAgentEventsInput): Promise<AgentExecutionEvent[]> {
    return (this.events.get(input.executionId) ?? [])
      .filter(
        (event) => matchesScope(event, input) && event.sequence > input.afterSequence
      )
      .slice(0, input.limit)
      .map(cloneEvent);
  }
}

function matchesScope(record: ExecutionScope, scope: ExecutionScope): boolean {
  return (
    record.appId === scope.appId &&
    record.executionId === scope.executionId &&
    record.sessionId === scope.sessionId
  );
}

function providerKey(scope: ExecutionScope, providerEventRef: string): string {
  return `${scope.executionId}\u0000${providerEventRef}`;
}

function cloneEvent(event: AgentExecutionEvent): AgentExecutionEvent {
  return { ...event, payload: { ...event.payload } };
}
